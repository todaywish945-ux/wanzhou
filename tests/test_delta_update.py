# -*- coding: utf-8 -*-
r"""文件级差分更新：清单生成 / 差分打包 / 客户端对账组装 / 回退接线。

四层替换管线不动，本文件只钉「下载哪一半」：
    全量 zip（兜底，任何偏差都走它）
    delta zip（只装变化的文件 + 双份清单；本地漂移零容忍）
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PY = sys.executable


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_bundle(root: Path, *, mutate: str = "") -> None:
    """搭一个迷你便携包：exe + 一个几乎不变的 DLL + 一个会变的资源。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "wanzhou-pet.exe").write_bytes(b"MZ-1.06")
    (root / "_internal").mkdir(exist_ok=True)
    (root / "_internal" / "core.dll").write_bytes(b"DLL-stable")
    (root / "assets").mkdir(exist_ok=True)
    (root / "assets" / "pack.dat").write_bytes(b"ASSET-v1" + mutate.encode())


def _run_script(script: str, *args: str) -> None:
    result = subprocess.run([PY, str(SCRIPTS / script), *args],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def test_manifest_is_deterministic(tmp_path):
    """同一棵树两次生成的清单必须逐字节一致（差分对账的前提）。"""
    bundle = tmp_path / "b1"
    _make_bundle(bundle)
    out1, out2 = tmp_path / "m1.json", tmp_path / "m2.json"
    _run_script("make_file_manifest.py", "--bundle", str(bundle),
                "--version", "1.07", "--out", str(out1))
    _run_script("make_file_manifest.py", "--bundle", str(bundle),
                "--version", "1.07", "--out", str(out2))
    assert out1.read_bytes() == out2.read_bytes()
    manifest = json.loads(out1.read_text(encoding="utf-8"))
    assert manifest["version"] == "1.07"
    assert [e["p"] for e in manifest["files"]] == sorted(
        e["p"] for e in manifest["files"])
    assert "assets/pack.dat" in {e["p"] for e in manifest["files"]}


def test_delta_zip_packs_only_changed_and_added(tmp_path):
    """差分包只装哈希变化的文件与新增文件；被移除的文件不进包。"""
    v1dir, v2dir = tmp_path / "v1", tmp_path / "v2"
    _make_bundle(v1dir)
    _make_bundle(v2dir, mutate="-2")
    (v2dir / "_internal" / "new.mod").write_bytes(b"NEW-MODULE")
    (v1dir / "assets" / "pack.dat")  # 保留；v2 中仍存在
    m1, m2 = tmp_path / "m-1.06.json", tmp_path / "m-1.07.json"
    _run_script("make_file_manifest.py", "--bundle", str(v1dir),
                "--version", "1.06", "--out", str(m1))
    _run_script("make_file_manifest.py", "--bundle", str(v2dir),
                "--version", "1.07", "--out", str(m2))
    delta = tmp_path / "delta.zip"
    _run_script("make_delta_zip.py", "--from", str(m1), "--to", str(m2),
                "--bundle", str(v2dir), "--out", str(delta))

    with __import__("zipfile").ZipFile(delta) as zf:
        names = set(zf.namelist())
        meta = json.loads(zf.read("delta.json").decode("utf-8"))
    assert meta["from_version"] == "1.06" and meta["to_version"] == "1.07"
    assert names == {"delta.json", "assets/pack.dat", "_internal/new.mod"}
    # 未变化的 core.dll 不进包；from/to 清单完整内嵌（客户端离线对账用）
    assert "_internal/core.dll" not in names
    assert {e["p"] for e in meta["from_files"]} == {
        "wanzhou-pet.exe", "_internal/core.dll", "assets/pack.dat"}


def test_apply_delta_assembles_verifies_and_carries_extras(tmp_path):
    """无漂移：组装出与 to 清单逐文件一致的新目录，清单外运行时文件保留。"""
    v1dir, v2dir = tmp_path / "v1", tmp_path / "v2"
    _make_bundle(v1dir)
    _make_bundle(v2dir, mutate="-2")
    (v2dir / "_internal" / "new.mod").write_bytes(b"NEW-MODULE")
    m1, m2 = tmp_path / "m1.json", tmp_path / "m2.json"
    _run_script("make_file_manifest.py", "--bundle", str(v1dir),
                "--version", "1.06", "--out", str(m1))
    _run_script("make_file_manifest.py", "--bundle", str(v2dir),
                "--version", "1.07", "--out", str(m2))
    delta = tmp_path / "delta.zip"
    _run_script("make_delta_zip.py", "--from", str(m1), "--to", str(m2),
                "--bundle", str(v2dir), "--out", str(delta))

    # 模拟"正在运行的旧程序目录"：复制 v1 + 一个清单外运行时文件
    live = tmp_path / "live"
    shutil.copytree(v1dir, live)
    (live / "runtime-marker.txt").write_bytes(b"runtime")

    from pet.delta_update import apply_delta

    staged = apply_delta(delta, live, tmp_path / "updates" / "staging")
    assert staged.name == "wanzhou-pet"
    assert (staged / "assets" / "pack.dat").read_bytes() == b"ASSET-v1-2"
    assert (staged / "_internal" / "new.mod").read_bytes() == b"NEW-MODULE"
    assert (staged / "_internal" / "core.dll").read_bytes() == b"DLL-stable"
    assert (staged / "runtime-marker.txt").is_file(), "清单外文件必须保留"

    # 组装结果与 to 清单逐文件一致（含大小与哈希）
    from pet.delta_update import scan_dir
    to_manifest = json.loads(m2.read_text(encoding="utf-8"))
    scanned = scan_dir(staged)
    for entry in to_manifest["files"]:
        got = scanned.get(entry["p"])
        assert got is not None and got["h"] == entry["h"] and got["s"] == entry["s"], entry["p"]


def test_apply_delta_raises_on_drift(tmp_path):
    """本地被改过/文件缺失：对账必须失败（零容忍），调用方回退全量。"""
    from pet.delta_update import LocalDriftError, apply_delta

    v1dir, v2dir = tmp_path / "v1", tmp_path / "v2"
    _make_bundle(v1dir)
    _make_bundle(v2dir)
    m1, m2 = tmp_path / "m1.json", tmp_path / "m2.json"
    _run_script("make_file_manifest.py", "--bundle", str(v1dir),
                "--version", "1.06", "--out", str(m1))
    _run_script("make_file_manifest.py", "--bundle", str(v2dir),
                "--version", "1.07", "--out", str(m2))
    delta = tmp_path / "delta.zip"
    _run_script("make_delta_zip.py", "--from", str(m1), "--to", str(m2),
                "--bundle", str(v2dir), "--out", str(delta))

    live = tmp_path / "live"
    shutil.copytree(v1dir, live)
    (live / "_internal" / "core.dll").write_bytes(b"DLL-tampered")  # 漂移
    with pytest.raises(LocalDriftError):
        apply_delta(delta, live, tmp_path / "staging1")

    live2 = tmp_path / "live2"
    shutil.copytree(v1dir, live2)
    (live2 / "_internal" / "core.dll").unlink()  # 缺失
    with pytest.raises(LocalDriftError):
        apply_delta(delta, live2, tmp_path / "staging2")


def test_stage_update_falls_back_to_full_on_drift(tmp_path, monkeypatch):
    """接线层：差分失败必须回退全量 stage（增量是纯增益，全量是兜底）。"""
    from pet.config import Config
    from pet.update_settings import _stage_update

    calls = {"delta": 0, "full": 0}

    def _delta_broken(asset, program_dir, config_dir, *, progress=None):
        calls["delta"] += 1
        raise RuntimeError("本地漂移")

    from pet import delta_update
    monkeypatch.setattr(delta_update, "stage_delta_update", _delta_broken)

    cfg = Config(tmp_path)
    result = _stage_update(
        lambda: (calls.__setitem__("full", calls["full"] + 1), "full-root")[1],
        delta_asset={"from": "1.06", "to": "1.07", "urls": ["x"]},
        app_dir=tmp_path,  # 目录里没有 wanzhou-pet.exe → 前置门直接走全量
        config_dir=cfg.dir,
        progress=lambda c, t: None,
    )
    # app_dir 下没有 wanzhou-pet.exe → 差分入口的前置门直接判走全量
    assert result == "full-root" and calls == {"delta": 0, "full": 1}


def test_stage_update_uses_delta_when_version_matches(tmp_path, monkeypatch):
    """delta.from == 当前版本且程序目录合法 → 走差分，不碰全量。"""
    from pet import delta_update
    from pet import updater
    from pet.config import Config
    from pet.update_settings import _stage_update

    _qapp = None
    cfg = Config(tmp_path)
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    (exe_dir / "wanzhou-pet.exe").write_bytes(b"MZ")
    monkeypatch.setattr(updater, "APP_VERSION", "1.06")
    hits = {"delta": 0, "full": 0}

    def _delta_ok(asset, program_dir, config_dir, *, progress=None):
        hits["delta"] += 1
        return "delta-root"

    monkeypatch.setattr(delta_update, "stage_delta_update", _delta_ok)

    def _forbidden():
        hits["full"] += 1
        raise AssertionError("delta 可用时不得回退全量")

    result = _stage_update(
        _forbidden,
        delta_asset={"from": "1.06", "to": "1.07", "urls": ["x"]},
        app_dir=exe_dir, config_dir=cfg.dir,
        progress=lambda c, t: None,
    )
    assert result == "delta-root" and hits == {"delta": 1, "full": 0}
