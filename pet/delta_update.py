# -*- coding: utf-8 -*-
r"""文件级差分更新客户端：对账 → 组装 → 逐文件验证 → 交给既有替换管线。

与四层替换管线的关系：本模块只负责「把暂存目录组装成新版完整形态」，
组装完返回的 staged root 形状与 ``updater.stage_portable_update`` 的返回
完全一致（staging/wanzhou-pet），后续写脚本/脱离启动/备份回滚**原样复用**。
任何一步对不上就抛错，调用方回退全量包——**偏差零容忍，不做半吊子增量**。

差分 zip 形态（scripts/make_delta_zip.py 生成）：
    delta.json  {"from_version", "to_version", "from_files", "to_files"}
    <变化的文件按包内相对路径存放>

安全口径（与 updater.download_asset 同源）：
    - 差分 zip 先过 SHA256（下载层已验），组装时每个文件再对 to 清单哈希；
    - 本地与基线（from_files）逐文件对账，缺失/漂移即 LocalDriftError，
      调用方回退全量包——偏差零容忍；
    - 防越界：条目路径解出的绝对路径必须落在暂存目录内（zip-slip）。

性能口径：对账用线程池并行哈希（进度在主循环按完成顺序顺序累加，无线程
竞态）；未变化文件硬链接零拷贝（同卷瞬时、跨卷自动回退复制并验哈希）；
实际 IO ≈ 895MB 读（对账）+ 变化量写（差分包）+ 变化量写（组装），远小于
全量路径的 459MB 下载 + 895MB 解压。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger("pet.delta_update")

#: 单条目读入内存的上限（最大单文件是 PySide6 的 DLL，30MB 量级）
_MAX_MEMBER_BYTES = 64 * 1024 * 1024


class LocalDriftError(RuntimeError):
    """本地目录与差分基线不一致（被改过/版本不符）——调用方应回退全量包。"""


class DeltaIntegrityError(RuntimeError):
    """差分包内容与 to 清单不符（下载损坏/包构造错误）——回退全量包。"""


def _sha256_file(path: Path) -> tuple[int, str]:
    size = 0
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1 << 20)
            if not block:
                break
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def scan_dir(root: Path, *, workers: int = 8) -> dict[str, dict]:
    """扫描目录 → {相对路径: {"s": size, "h": sha256}}（正斜杠键，与清单同形态）。"""
    root = Path(root)
    rels: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            rels.append((Path(dirpath) / name).relative_to(root).as_posix())

    def _hash(rel: str) -> tuple[str, dict]:
        size, sha = _sha256_file(root / rel)
        return rel, {"s": size, "h": sha}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        entries = dict(pool.map(_hash, sorted(rels)))
    return entries


def _verify_bytes(data: bytes, entry: dict, rel: str) -> None:
    if len(data) != int(entry["s"]) or hashlib.sha256(data).hexdigest() != entry["h"]:
        raise DeltaIntegrityError(f"差分包内容与目标清单不符：{rel}")


def _place_unchanged(source: Path, dest: Path, entry: dict, rel: str) -> None:
    """未变化文件进暂存：硬链接优先（同卷零拷贝），跨卷/被禁回退复制并验哈希。"""
    if getattr(os, "link", None):
        try:
            os.link(source, dest)
            return
        except OSError:
            pass
    shutil.copyfile(source, dest)
    size, sha = _sha256_file(dest)
    if size != int(entry["s"]) or sha != entry["h"]:
        raise DeltaIntegrityError(f"组装后内容不符：{rel}")


def _carry_extra(source: Path, dest: Path) -> None:
    """清单外文件原样带入（运行时产物不因更新丢失）；差分若有同名条目以差分为准。"""
    if getattr(os, "link", None):
        try:
            os.link(source, dest)
            return
        except OSError:
            pass
    shutil.copyfile(source, dest)


def apply_delta(delta_zip: Path, program_dir: Path, staging_dir: Path,
                *, progress=None) -> Path:
    """按差分包把 program_dir 组装成新版本，返回暂存程序根目录。

    progress(current, total)：对账扫描与组装摆放在同一把「字节尺」上顺序
    累加（扫描完 = scan_total，随后组装段继续增长到总和），更新窗的 MB
    进度条直接复用。
    """
    delta_zip = Path(delta_zip)
    program_dir = Path(program_dir).resolve()
    staging_dir = Path(staging_dir).resolve()

    with zipfile.ZipFile(delta_zip) as zf:
        meta = json.loads(zf.read("delta.json").decode("utf-8"))
        from_map = {e["p"]: e for e in meta["from_files"]}
        to_files = meta["to_files"]
        to_map = {e["p"]: e for e in to_files}
        changed = {e["p"] for e in to_files
                   if from_map.get(e["p"], {}).get("h") != e["h"]}

        staging_root = staging_dir / "wanzhou-pet"
        # 防越界（zip-slip）：变化条目必须落在暂存根内
        for rel in changed:
            resolved = (staging_root / rel).resolve()
            if not str(resolved).startswith(str(staging_root.resolve()) + os.sep):
                raise DeltaIntegrityError(f"差分包包含越界路径：{rel}")

        # ---- 1. 对账：本地与基线（from_files）逐文件比对 ----
        local_rels: set[str] = set()
        for dirpath, _dirnames, filenames in os.walk(program_dir):
            for name in filenames:
                local_rels.add((Path(dirpath) / name)
                               .relative_to(program_dir).as_posix())
        missing = sorted(from_map.keys() - local_rels)
        if missing:
            raise LocalDriftError(f"基线文件缺失：{missing[:3]}…")

        scan_total = sum(int(e["s"]) for e in from_map.values())
        assemble_total = sum(int(e["s"]) for e in to_files)
        total = scan_total + assemble_total
        done = 0
        if progress:
            progress(0, total)

        def _check(rel: str) -> tuple[str, int, str]:
            size, sha = _sha256_file(program_dir / rel)
            return rel, size, sha

        with ThreadPoolExecutor(max_workers=8) as pool:
            for rel, size, sha in pool.map(_check, sorted(from_map.keys())):
                done += size
                entry = from_map[rel]
                if size != int(entry["s"]) or sha != entry["h"]:
                    raise LocalDriftError(f"基线文件内容漂移：{rel}")
                if progress:
                    progress(min(done, scan_total), total)
        logger.info("差分对账通过：%d 个基线文件与本地一致", len(from_map))

        # ---- 2. 组装 staging（先清场，与全量 stage 同纪律）----
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_root.mkdir(parents=True)

        for entry in to_files:
            rel, dest = entry["p"], staging_root / entry["p"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            if rel in changed:
                info = zf.getinfo(rel)
                if info.file_size > _MAX_MEMBER_BYTES:
                    raise DeltaIntegrityError(f"差分条目超限：{rel}")
                data = zf.read(rel)
                _verify_bytes(data, entry, rel)
                dest.write_bytes(data)
            else:
                # 未变化文件：对账已验过本地哈希（== from == to），硬链接即可；
                # 硬链接被禁/跨卷回退复制并当场验哈希。
                _place_unchanged(program_dir / rel, dest, entry, rel)
            done += int(entry["s"])
            if progress:
                progress(min(done, total), total)

        # ---- 3. 清单外文件原样带入（运行时产物不因更新丢失）----
        for rel in sorted(local_rels - to_map.keys()):
            if rel in changed:
                continue  # 差分里恰好带了同名条目，以差分为准
            _carry_extra(program_dir / rel, staging_root / rel)
        if progress:
            progress(total, total)

    logger.info("差分组装完成：%d 变化 / %d 总文件", len(changed), len(to_files))
    return staging_root


def stage_delta_update(delta_asset: dict, program_dir: str | os.PathLike,
                       config_dir: str | os.PathLike, *,
                       timeout: float = 60.0,
                       progress=None) -> Path:
    """下载差分包 → 校验 → 组装暂存目录；失败抛错，调用方回退全量。

    形状与 ``updater.stage_portable_update`` 对齐（下载进 updates/ 缓存、
    .part 原子落盘、SHA256 校验、staging 清场后组装、返回 staging 根目录），
    调用方无须感知差异。
    """
    from . import updater  # 延迟导入：避免模块环（updater 不反向依赖本模块）

    cache = updater.update_cache_dir(config_dir)
    archive = updater.download_asset(delta_asset, cache, timeout=timeout,
                                     progress=progress)
    staging = cache / "staging"
    return apply_delta(archive, program_dir, staging, progress=progress)
