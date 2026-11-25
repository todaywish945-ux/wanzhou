# -*- coding: utf-8 -*-
"""构建前门禁：源码里不允许出现看起来像真密钥的字面量。

扫描仓库源码与随包资源（排除 venv、测试、备份、构建产物），命中就非零退出，
避免把 Key 编译进 exe 或提交到公开仓库。

注意：只防「硬编码在文件里的字面量」。已经存进 Windows 凭据管理器 /
%APPDATA% 的 Key 本来就不在仓库里，也不随包走。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 真 Key 的形态：sk- 后跟至少 24 位字母数字（Qt 的 sk-box-image-* 这类
# CSS 标识符含连字符且短，不会命中）。
PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{24,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{24,}"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret|access[_-]?token)\b\s*[:=]\s*"
        r"['\"][^'\"]{16,}['\"]"
    ),
)
SKIP_DIRS = {
    ".git", ".workbuddy", ".pytest_cache", "__pycache__", ".scratch",
    "venv", ".venv", "dist", "build", "tests", "_参考", "_tools",
}
SKIP_PREFIXES = (".backup_",)


def _should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    for part in rel.parts[:-1]:
        if part in SKIP_DIRS or part.startswith(SKIP_PREFIXES):
            return True
    return path.name.startswith(SKIP_PREFIXES)


def main() -> int:
    hits: list[str] = []
    scanned = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or _should_skip(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern in PATTERNS:
                if pattern.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:120]}")
                    break

    print(f"密钥扫描：{scanned} 个文本文件，命中 {len(hits)} 处")
    for hit in hits[:50]:
        print("  " + hit)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
