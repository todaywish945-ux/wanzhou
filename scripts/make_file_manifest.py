# -*- coding: utf-8 -*-
r"""生成便携包的逐文件清单（文件级差分更新的真源）。

用法：
    python scripts/make_file_manifest.py --bundle dist/wanzhou-pet \
        --version 1.07 --out manifests/manifest-1.07.json

清单形态（键路径一律正斜杠、相对包根、按路径排序——同包必同清单）：
    {"version": "1.07", "files": [{"p": "wanzhou-pet.exe", "s": 123, "h": "sha256"}, ...]}

短键省体积：3700 文件 × 长键名会让清单膨胀近一倍。清单入库到 manifests/
（文本、可 diff），下一个版本的差分包拿它当基线。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # noqa: E402  供 --dump 后续脚本复用 catalog 等模块（当前未用，占位）


def hash_file(path: Path, chunk: int = 1 << 20) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def build_manifest(bundle: Path, version: str, workers: int = 8) -> dict:
    """扫描包目录 → 清单 dict。路径相对包根、正斜杠、按路径排序（确定性）。"""
    files = []
    for dirpath, _dirnames, filenames in os.walk(bundle):
        for name in filenames:
            full = Path(dirpath) / name
            rel = full.relative_to(bundle).as_posix()
            files.append(rel)
    files.sort()

    def _entry(rel: str) -> dict:
        size, sha = hash_file(bundle / rel)
        return {"p": rel, "s": size, "h": sha}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        entries = list(pool.map(_entry, files))
    return {"version": version, "files": entries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True, help="便携包目录（dist/wanzhou-pet）")
    parser.add_argument("--version", required=True, help="该包对应的版本号（如 1.07）")
    parser.add_argument("--out", type=Path, required=True, help="清单输出路径（manifests/manifest-<版本>.json）")
    args = parser.parse_args()

    bundle = args.bundle.resolve()
    if not (bundle / "wanzhou-pet.exe").is_file():
        raise SystemExit(f"不是便携包目录（缺 wanzhou-pet.exe）: {bundle}")

    manifest = build_manifest(bundle, args.version.strip().lstrip("vV"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    total = sum(e["s"] for e in manifest["files"])
    print(f"清单已写入 {args.out}：{len(manifest['files'])} 文件，{total / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
