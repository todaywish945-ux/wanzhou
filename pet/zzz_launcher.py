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

#: 内置默认游戏路径（开发者本机实测位置；其他用户的安装位置靠探测链兜底）
DEFAULT_ZZZ_EXE = r"D:\miHoYo Launcher\games\ZenlessZoneZero Game\ZenlessZoneZero.exe"

#: 配置键（config.py 已登记，空串＝走默认）
ZZZ_PATH_KEY = "zzz_game_path"

#: 游戏 exe 相对 InstallLocation 的候选位置（注册表给的往往是启动器目录）
_INSTALL_RELATIVE_CANDIDATES = (
    r"games\ZenlessZoneZero Game\ZenlessZoneZero.exe",
    r"ZenlessZoneZero Game\ZenlessZoneZero.exe",
    r"ZenlessZoneZero.exe",
)

if sys.platform == "win32":
    import winreg  # noqa: F401 - 探测链用


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


def _exe_from_install_location(location: str) -> Path | None:
    """启动器目录 → 逐个候选位置找游戏 exe。"""
    base = Path(str(location).strip().strip('"'))
    if not base.is_dir():
        return None
    for relative in _INSTALL_RELATIVE_CANDIDATES:
        candidate = base / relative
        if candidate.is_file():
            return candidate
    return None


def _registry_discover() -> Path | None:
    """注册表卸载键探测：米哈游启动器会写 DisplayName「绝区零」+ InstallLocation。"""
    if sys.platform != "win32":
        return None
    import winreg

    hives = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for root, hive in hives:
        try:
            key = winreg.OpenKey(root, hive)
        except OSError:
            continue
        with key:
            try:
                subkey_count, _, _ = winreg.QueryInfoKey(key)
            except OSError:
                continue
            for index in range(subkey_count):
                try:
                    sub_name = winreg.EnumKey(key, index)
                    sub = winreg.OpenKey(key, sub_name)
                except OSError:
                    continue
                with sub:
                    try:
                        display, _ = winreg.QueryValueEx(sub, "DisplayName")
                    except OSError:
                        continue
                    if "绝区零" not in str(display) \
                            and "zenless" not in str(display).lower():
                        continue
                    try:
                        location, _ = winreg.QueryValueEx(sub, "InstallLocation")
                    except OSError:
                        continue
                    exe = _exe_from_install_location(str(location))
                    if exe is not None:
                        return exe
    return None


def _resolve_shortcut(lnk: Path) -> Path | None:
    """解析 .lnk 目标（PowerShell COM，只在注册表未命中时兜底一次）。"""
    if sys.platform != "win32":
        return None
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
        f"'{lnk}'); Write-Output $s.TargetPath"
    )
    try:
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not output:
        return None
    target = Path(output.splitlines()[0].strip().strip('"'))
    if target.name.lower() == "zenlesszonezero.exe" and target.is_file():
        return target
    # 快捷方式常指向启动器 → 在其相邻目录按候选布局找游戏本体
    return _exe_from_install_location(str(target.parent))


def _shortcut_discover() -> Path | None:
    """桌面 / 开始菜单「绝区零」快捷方式解析。"""
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA")
    search_dirs = []
    if appdata:
        search_dirs.append(Path(appdata) / r"Microsoft\Windows\Start Menu\Programs")
    public = os.environ.get("PUBLIC")
    if public:
        search_dirs.append(Path(public) / r"Start Menu\Programs")
        search_dirs.append(Path(public) / "Desktop")
    desktop = os.environ.get("USERPROFILE")
    if desktop:
        search_dirs.append(Path(desktop) / "Desktop")
        search_dirs.append(Path(desktop) / "OneDrive" / "Desktop")
    seen: set[Path] = set()
    for directory in search_dirs:
        if not directory.is_dir():
            continue
        try:
            entries = list(directory.glob("*.lnk"))
        except OSError:
            continue
        for lnk in entries:
            if lnk in seen:
                continue
            seen.add(lnk)
            stem = lnk.stem.lower()
            if "绝区零" not in lnk.stem and "zenless" not in stem:
                continue
            exe = _resolve_shortcut(lnk)
            if exe is not None:
                return exe
    return None


def discover_game(configured: str | os.PathLike[str] | None = None
                  ) -> tuple[Path | None, str]:
    """自动探测游戏 exe。返回 ``(路径或 None, 来源)``。

    探测链：配置路径 → 注册表卸载键 → 桌面/开始菜单快捷方式 → 内置默认。
    """
    configured_path = resolve_game_path(configured)
    if str(configured or "").strip():
        # 显式配置是硬指定：存在即用；不存在不再回退探测（语义可诊断）。
        if configured_path.is_file():
            return configured_path, "config"
        return None, ""
    exe = _registry_discover()
    if exe is not None:
        return exe, "registry"
    exe = _shortcut_discover()
    if exe is not None:
        return exe, "shortcut"
    # 空配置时 configured_path 即内置默认（开发者本机场景）
    if not str(configured or "").strip() and configured_path.is_file():
        return configured_path, "default"
    return None, ""


def launch_exe(exe: Path) -> tuple[bool, str]:
    """启动指定游戏 exe。返回 ``(是否成功发起, 说明)``。"""
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


def launch_game(configured: str | os.PathLike[str] | None = None) -> tuple[bool, str]:
    """探测并启动游戏。返回 ``(是否成功发起, 说明)``。

    - 全探测链未命中 → ``(False, "未找到游戏：...")``，不抛异常；
    - 非 Windows → ``(False, "仅支持 Windows")``；
    - 启动失败 → ``(False, 错误摘要)``；
    - 成功 → ``(True, "")``。
    """
    exe, _source = discover_game(configured)
    if exe is None:
        return False, (f"未找到游戏：{resolve_game_path(configured)}"
                       "（装好绝区零后重试，或把 exe 路径填到 zzz_game_path）")
    return launch_exe(exe)
