# -*- coding: utf-8 -*-
"""「启动绝区零」：从桌宠右键菜单一键启动游戏客户端。

**纯逻辑模块**（无 Qt 依赖）：路径解析 + 启动。气泡反馈由调用方（window.py）负责，
这样本模块可以脱离 GUI 单测。

路径来源（按优先级）：
1. 配置键 ``zzz_game_path``（用户可改，空串＝用默认）；
2. 内置默认 ``D:/miHoYo Launcher/games/ZenlessZoneZero Game/ZenlessZoneZero.exe``。

启动方式：直接启动 exe 并指定工作目录（与一条龙 OpenGame 的做法一致——
绝区零的 exe 可直接启动，不必经米哈游启动器）。

**为什么用 `cmd /c start` 而不是 `os.startfile`**：`start /d <目录>` 能显式指定
工作目录，且启动的进程与桌宠解耦（桌宠退出不会带走游戏）。Windows 专用；
非 Windows 平台本功能不可用（游戏本身也没有对应客户端），`launch_zzz()` 返回失败。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

#: 内置默认游戏路径（本机实测位置）
DEFAULT_ZZZ_EXE = r"D:\miHoYo Launcher\games\ZenlessZoneZero Game\ZenlessZoneZero.exe"

#: 配置键（config.py 已登记，空串＝走默认）
ZZZ_PATH_KEY = "zzz_game_path"


def resolve_game_path(configured: str | os.PathLike[str] | None) -> Path:
    """解析游戏 exe 路径：配置优先，空值走默认；展开 ~ 与环境变量。"""
    raw = str(configured or "").strip()
    if not raw:
        raw = DEFAULT_ZZZ_EXE
    expanded = os.path.expandvars(os.path.expanduser(raw))
    return Path(expanded)


def is_game_available(configured: str | os.PathLike[str] | None = None) -> bool:
    """游戏 exe 是否存在（菜单可用性与点击前检查共用）。"""
    return resolve_game_path(configured).is_file()


def launch_game(configured: str | os.PathLike[str] | None = None) -> tuple[bool, str]:
    """启动游戏。返回 ``(是否成功发起, 说明)``。

    - 路径不存在 → ``(False, "未找到游戏：...")``，不抛异常；
    - 非 Windows → ``(False, "仅支持 Windows")``；
    - 启动失败 → ``(False, 错误摘要)``；
    - 成功 → ``(True, "")``。
    """
    exe = resolve_game_path(configured)
    if not exe.is_file():
        return False, f"未找到游戏：{exe}"
    if sys.platform != "win32":
        return False, "启动绝区零仅支持 Windows"

    game_dir = str(exe.parent)
    # 与一条龙一致：start /d 指定工作目录；& exit 让 cmd 立刻退出，不留窗口。
    command = f'cmd /c start "" /d "{game_dir}" "{exe.name}" & exit'
    flags = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0) | getattr(
        subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(command, creationflags=flags)
    except Exception as exc:  # noqa: BLE001 - 启动失败要变成气泡提示，不能崩桌宠
        return False, f"启动失败：{exc}"
    return True, ""
