# -*- coding: utf-8 -*-
"""冻结 exe 的 __main__：双击一次拉起三只桌宠的启动器。

三只桌宠本来就是三个独立进程（slot 1/2/3 + 角色 A/B/C），所以这个 exe
有两种身份：
- 带 ``--slot`` 参数：它就是其中一只桌宠，直接进 pet.app.main；
- 不带参数：它是启动器，依次拉起三个自己，每个带不同的 slot/instance/character。

设置页 / OCR 工作端 / 卸载清理仍按专用参数在最前面分流，绝不先导入 pet.app。
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
    """起三个独立进程；启动器自己随即退出，不占着父进程。"""
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

    # 可测缝：设了 PET_LAUNCHER_DRY_RUN=1 就只打印命令，不真的起桌宠。
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
    # 开机自启写的是 --launch-all（见 pet/autostart.py）；没有 --slot 时
    # 同样走启动器，两种写法等价，兼容旧的自启命令。
    if "--slot" in sys.argv:
        sys.exit(main())
    sys.exit(launch_three())
