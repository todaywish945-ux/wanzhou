# -*- coding: utf-8 -*-
"""冻结 exe 的 __main__：不带 AI 对话的三宠启动器。

与 :mod:`packaging.pet_entry` 同构；唯一差别是子进程的正常启动走
``main(enable_chat=False)``。PyInstaller 侧另用 ``--exclude-module pet.chat``
把模块真正排除出包。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pet.qt_plugin_sanitizer import sanitize_plugin_path

sanitize_plugin_path()

if "--uninstall-cleanup" in sys.argv:
    from pet.runtime_cleanup import mark_frozen_runtime_dir

    mark_frozen_runtime_dir()
    from pet.uninstall_cleanup import main as uninstall_cleanup_main

    sys.exit(uninstall_cleanup_main())

if "--ocr-worker" in sys.argv:
    from pet.__main__ import _run_ocr_worker

    sys.exit(_run_ocr_worker())

if "--settings" in sys.argv:
    from pet.__main__ import _run_settings

    sys.exit(_run_settings())

from pet.app import main

_ROLES = ((1, "A", "A"), (2, "B", "B"), (3, "C", "C"))


def launch_three() -> int:
    if getattr(sys, "frozen", False):
        base = [sys.executable]
        workdir = str(Path(sys.executable).resolve().parent)
    else:
        base = [sys.executable, "-m", "pet"]
        workdir = str(Path(__file__).resolve().parents[1])

    commands = [
        base + ["--slot", str(slot), "--instance", instance, "--character", character]
        for slot, instance, character in _ROLES
    ]
    if os.environ.get("PET_LAUNCHER_DRY_RUN") == "1":
        for command in commands:
            print(json.dumps(command, ensure_ascii=False))
        return 0

    flags = 0
    if sys.platform == "win32":
        flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    for command in commands:
        subprocess.Popen(command, cwd=workdir, close_fds=True, creationflags=flags)
    return 0


if __name__ == "__main__":
    if "--slot" in sys.argv:
        sys.exit(main(enable_chat=False))
    sys.exit(launch_three())
