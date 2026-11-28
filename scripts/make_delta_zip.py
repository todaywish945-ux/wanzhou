# -*- coding: utf-8 -*-
r"""生成相邻版本的差分包（只装变化的文件 + 双份清单）。

用法：
    python scripts/make_delta_zip.py \
        --from manifests/manifest-1.06.json --to manifests/manifest-1.07.json \
        --bundle dist/wanzhou-pet --out dist/wanzhou-1.07-delta-from-1.06.zip

差分 zip 形态：
    delta.json     {"from_version", "to_version",
                    "from_files": [...基线清单...], "to_files": [...目标清单...]}
    <变化的文件按包内相对路径原位存放>

客户端（pet/delta_update.py）的契约：本地目录与 from_files 逐文件一致 →
按 to_files 组装暂存目录（变化文件取自差分包，未变化文件硬链接/复制本地）
→ 组装时逐文件校验 to 清单哈希。本地漂移即抛 LocalDriftError，调用方回退
全量包——**任何偏差都不做半吊子增量**。

被移除的文件（from 有 to 无）不需要进差分包：组装只按 to_files 摆放，
未列出的文件自然不会出现在暂存目录里。
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "version" not in data or "files" not in data:
        raise SystemExit(f"清单形态不对（缺 version/files）: {path}")
    return data


def diff_files(from_files: list[dict], to_files: list[dict]) -> list[str]:
    """变化集 = 哈希不同 + 新增。被移除的文件不进差分（组装按 to 清单摆放）。"""
    from_map = {e["p"]: e["h"] for e in from_files}
    changed = []
    for entry in to_files:
        if from_map.get(entry["p"]) != entry["h"]:
            changed.append(entry["p"])
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="from_manifest", type=Path, required=True)
    parser.add_argument("--to", dest="to_manifest", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True, help="**新版本**的包目录（差分文件从这里取）")
    parser.add_argument("--out", type=Path, required=True, help="差分 zip 输出路径")
    args = parser.parse_args()

    frm = load_manifest(args.from_manifest)
    to = load_manifest(args.to_manifest)
    if frm["version"] == to["version"]:
        raise SystemExit("from/to 清单版本相同，差分无意义")
    bundle = args.bundle.resolve()
    exe_entry = next((e for e in to["files"] if e["p"] == "wanzhou-pet.exe"), None)
    if exe_entry is None or not (bundle / "wanzhou-pet.exe").is_file():
        raise SystemExit("--bundle 必须指向 --to 清单对应的便携包目录")

    changed = diff_files(frm["files"], to["files"])
    to_map = {e["p"]: e for e in to["files"]}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr("delta.json", json.dumps({
            "from_version": frm["version"],
            "to_version": to["version"],
            "from_files": frm["files"],
            "to_files": to["files"],
        }, ensure_ascii=False, separators=(",", ":")))
        for rel in changed:
            source = bundle / rel
            if not source.is_file():
                raise SystemExit(f"新包里找不到差分文件：{rel}（bundle 与 --to 清单不一致？）")
            if __import__("hashlib").sha256(source.read_bytes()).hexdigest() != to_map[rel]["h"]:
                raise SystemExit(f"差分文件哈希与 to 清单不符：{rel}")
            zf.write(source, rel)

    size = args.out.stat().st_size
    print(f"差分包已写入 {args.out}：{frm['version']} → {to['version']}，"
          f"{len(changed)}/{len(to['files'])} 文件，{size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
