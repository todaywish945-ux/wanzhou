# -*- coding: utf-8 -*-
"""三宠启动器：一次拉起角色 A/B/C 三个独立进程。

冻结 exe 不带参数 / 带 ``--launch-all`` 时走这里；源码 ``python -m pet --launch-all``
同样走这里（``pet/__main__.py`` 在导入 ``pet.app`` 之前分流）。三只仍是三个独立
进程，各自读 ``config-slot-N.json``，位置/缩放/设置互不干扰。

``--launch-all`` 这个标记也是开机自启命令的真值判据：旧命令末尾的 ``--slot 0``
只起 slot0 一只，必须能被 ``autostart.is_enabled()`` 识别并升级。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_ROLES = ((1, "A", "A"), (2, "B", "B"), (3, "C", "C"))


def build_commands() -> tuple[list[list[str]], str]:
    """返回 (三条子进程命令, 工作目录)，不实际启动。"""
    if getattr(sys, "frozen", False):
        base = [sys.executable]
        workdir = str(Path(sys.executable).resolve().parent)
    else:
        base = [sys.executable, "-m", "pet"]
        workdir = str(Path(__file__).resolve().parent.parent)
    commands = [
        base + ["--slot", str(slot), "--instance", instance, "--character", character]
        for slot, instance, character in _ROLES
    ]
    return commands, workdir


def launch_three() -> int:
    """起三个独立进程；启动器自己随即退出，不占着父进程。"""
    commands, workdir = build_commands()
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
