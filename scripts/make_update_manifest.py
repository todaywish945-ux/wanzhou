# -*- coding: utf-8 -*-
r"""发版小工具：给 GitHub Release 便携包写好 update.json。

用法（在仓库根执行）::

    python scripts/make_update_manifest.py --version 1.03 ^
        --notes "修复骗子酒馆与绝区零启动" ^
        --download-url "https://github.com/todaywish945-ux/wanzhou/releases/download/v1.03/wanzhou-1.03-portable.zip" ^
        --archive dist/wanzhou-1.03-portable.zip

`--archive` 指向 build_onedir.ps1 产出的便携 zip，脚本读它的 size / SHA-256
写进 assets（客户端据此启用「下载并安装」一键更新）。本项目 download_code 留空，
不用提取码；不再挂百度网盘，也不再打源码包。

脚本只改 update.json 的 version / notes / html_url / download_url /
download_code / assets 六个字段，其余说明字段原样保留。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

REPO = "todaywish945-ux/wanzhou"

# 打源码包时明确排除的东西：历史备份、缓存、日志、产物本身和开发目录。
# **venv 必须随包**：启动 bat 直接引用 %~dp0venv\Scripts\pythonw.exe，
# 排掉它等于用户解压后点「一键启动全部」什么都出不来。
_EXCLUDE_DIRS = {
    ".git", ".workbuddy", ".pytest_cache", "__pycache__", ".scratch",
    "dist", "build", "_参考",
}
_EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    parts = set(rel.parts)
    if parts & _EXCLUDE_DIRS:
        return True
    name = path.name
    if name.startswith(".backup_") or name.startswith("."):
        return True
    return name.endswith(_EXCLUDE_SUFFIXES)


def _pack_source(root: Path, version: str) -> Path:
    dist = root / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    target = dist / f"wanzhou-{version}-source.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as bundle:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or _should_skip(path, root):
                continue
            bundle.write(path, Path("挽昼桌宠") / path.relative_to(root))
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="新版本号，如 1.01（可带 v）")
    parser.add_argument("--notes", default="", help="版本说明（与 --notes-file 二选一）")
    parser.add_argument("--notes-file", type=Path, help="版本说明文件（UTF-8）")
    parser.add_argument("--download-url", required=True,
                        help="百度网盘分享链接（用户点「打开下载页」会开它）")
    parser.add_argument("--download-code", default="", help="网盘提取码，没有就留空")
    parser.add_argument("--archive", type=Path,
                        help="现成源码 zip；不给就用 --pack-source 现场打一个")
    parser.add_argument("--delta", type=Path,
                        help="文件级差分包（wanzhou-<版本>-delta-from-<上一版>.zip）；"
                             "提供 --delta-from 时写入 update.json 的 delta 字段")
    parser.add_argument("--delta-from", type=str,
                        help="差分基线版本（用户当前最可能的版本，如 1.06）")
    parser.add_argument("--pack-source", action="store_true",
                        help="从仓库根打源码 zip 到 dist/")
    parser.add_argument("--repo", default=REPO, help="发布仓库，默认 %(default)s")
    parser.add_argument(
        "--manifest", type=Path,
        default=Path(__file__).resolve().parents[1] / "update.json",
        help="要写的 update.json，默认仓库根目录那份",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = parser.parse_args(argv)

    version = str(args.version).strip().lstrip("vV")
    if not re.fullmatch(r"\d+(\.\d+)*", version):
        parser.error(f"版本号只能是数字点分格式，收到 {args.version!r}")
    notes = (
        args.notes_file.read_text(encoding="utf-8").strip()
        if args.notes_file else str(args.notes).strip()
    )
    if not notes:
        parser.error("版本说明不能为空（--notes 或 --notes-file）")

    download_url = str(args.download_url).strip()
    if not download_url.startswith("https://"):
        parser.error("网盘链接必须是 https:// 开头")

    root = Path(__file__).resolve().parents[1]
    archive = args.archive or (_pack_source(root, version) if args.pack_source else None)
    assets = {}
    if archive is not None:
        if not archive.is_file():
            parser.error(f"源码包不存在：{archive}")
        assets[archive.name] = {
            "fileName": archive.name,
            "urls": [download_url],
            "size": archive.stat().st_size,
            "sha256": _sha256(archive),
            "platform": "windows",
            "kind": "portable",
        }

    if bool(args.delta) != bool(args.delta_from):
        parser.error("--delta 与 --delta-from 必须成对提供")
    delta_payload = None
    if args.delta is not None:
        if not args.delta.is_file():
            parser.error(f"差分包不存在：{args.delta}")
        delta_from = str(args.delta_from).strip().lstrip("vV")
        if not re.fullmatch(r"\d+(\.\d+)*", delta_from):
            parser.error(f"差分基线版本号非法：{args.delta_from!r}")
        delta_payload = {
            "from": delta_from,
            "to": version,
            "fileName": args.delta.name,
            "urls": [download_url.replace(
                f"/releases/download/v{version}/", f"/releases/download/v{version}/")],
            "size": args.delta.stat().st_size,
            "sha256": _sha256(args.delta),
        }

    manifest = args.manifest
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            parser.error(f"现有 update.json 读不出来：{exc}")
        if not isinstance(data, dict):
            parser.error("现有 update.json 顶层必须是对象")
    else:
        data = {}
    data["version"] = version
    data["html_url"] = f"https://github.com/{args.repo}/releases"
    if delta_payload is not None:
        # 差分资产的镜像阶梯与全量包同源（download_url 是 gh-proxy 包装直链；
        # 客户端 download_asset 会逐条尝试）。from 必须等于客户端当前版本，
        # 否则客户端忽略 delta 走全量——版本数学在 pet/delta_update.py。
        data["delta"] = delta_payload
    data["download_url"] = download_url
    data["download_code"] = str(args.download_code).strip()
    data["notes"] = notes
    data["assets"] = assets
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    if args.dry_run:
        sys.stdout.write(rendered)
    else:
        manifest.write_text(rendered, encoding="utf-8")
        suffix = "（压缩包已算好 size / sha256）" if archive else "（未附压缩包）"
        print(f"已写入 {manifest}（version={version}）{suffix}。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
