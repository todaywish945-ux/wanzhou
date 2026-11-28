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

**Job 与 `[WinError 5] 拒绝访问`（2026-11-28 实机定案）**：`launch_exe` 原本无条件
带 ``CREATE_BREAKAWAY_FROM_JOB``（逃离 Job，桌宠退出不带走游戏）。但宿主环境
可能把桌宠进程装进**不容许 breakaway 的 Job**（Win11 26200 实测：explorer/cmd/
桌宠全部 ``IsProcessInJob()=True``），此时 CreateProcess 在 cmd 都没起来时就直接
报 ``[WinError 5] 拒绝访问``——游戏根本没被尝试启动。所以降级链是：

1. 带 breakaway 启动（Job 允许时保持解耦语义）；
2. ``PermissionError`` → 去掉 breakaway 重试（游戏继承宿主 Job；实测宿主 Job 的
   句柄由仍在运行的系统组件持有，桌宠/启动器退出不会连带杀成员）；
3. 再 ``PermissionError`` → ``ShellExecuteW`` 兜底（经系统 shell 拉起，顺带兼容
   requireAdmin 清单的 exe）。
"""
from __future__ import annotations

import ctypes
import glob
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

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

#: HYP（HoYo Play 内核）的游戏安装记录：启动器把每个游戏的 installPath
#: 明文记在自己的持久化文件里，比注册表 InstallLocation 更精确（后者常只给
#: 启动器根目录）。国服数据在 %APPDATA%\miHoYo，国际服在 %APPDATA%\Cognosphere，
#: 子目录带启动器版本号（如 1_2），通配扫全部。
_HYP_DATA_GLOBS = (
    os.path.expandvars(r"%APPDATA%\miHoYo\HYP\*\data\gamedata.dat"),
    os.path.expandvars(r"%APPDATA%\Cognosphere\HYP\*\data\gamedata.dat"),
)

#: gamedata.dat 是带内部框架的二进制容器、内嵌 JSON 记录（无文档且随版本变），
#: 不解析容器，只按字节流提取 ``installPath``（JSON 转义的 ``\\`` 还原成 ``\``）。
_INSTALL_PATH_RE = re.compile(rb'"installPath"\s*:\s*"((?:[^"\\]|\\.)*)"')

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


def _hyp_config_discover() -> Path | None:
    """读启动器自己的游戏安装记录（HYP gamedata.dat），字节流容错提取。

    拿到的是启动器亲口记录的游戏安装目录（``installPath``，通常指向
    ``…\\games\\ZenlessZoneZero Game``），交 ``_exe_from_install_location``
    按 exe 是否真实存在校验——record 可能来自别的游戏（原神/崩铁同文件），
    或启动器还没来得及更新（游戏已搬走），都不能算命中。
    """
    if sys.platform != "win32":
        return None
    for pattern in _HYP_DATA_GLOBS:
        for dat in glob.glob(pattern):
            try:
                data = Path(dat).read_bytes()
            except OSError:
                continue
            for match in _INSTALL_PATH_RE.finditer(data):
                # JSON 转义还原（\\ → \）；路径含非 ASCII 时按原始 UTF-8 解码，
                # 不用 unicode_escape（会把它当 latin-1 弄乱中文目录名）。
                raw = match.group(1).replace(b"\\\\", b"\\")
                base = Path(raw.decode("utf-8", "ignore").strip())
                exe = _exe_from_install_location(str(base))
                if exe is not None:
                    return exe
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

    探测链：配置路径 → HYP 启动器安装记录 → 注册表卸载键 → 桌面/开始菜单
    快捷方式 → 内置默认。

    配置路径**存在**时仍最高优先（用户显式指定）；**失效**（游戏搬家、缓存
    过期）时降级为提示——继续走探测链而不是硬失败：window.py 会把探测命中
    的路径回写缓存，探测链恢复命中的那一刻配置自愈。全落空才报 None，由
    launch_game 的文案带上失效路径保留可诊断性。
    """
    configured_path = resolve_game_path(configured)
    if str(configured or "").strip() and configured_path.is_file():
        return configured_path, "config"
    exe = _hyp_config_discover()
    if exe is not None:
        return exe, "hyp"
    exe = _registry_discover()
    if exe is not None:
        return exe, "registry"
    exe = _shortcut_discover()
    if exe is not None:
        return exe, "shortcut"
    # 无配置时 configured_path 即内置默认（开发者本机场景）；有配置但失效时
    # 也允许默认兜底命中——总好过直接报"没找到"。
    if configured_path.is_file():
        return configured_path, "default"
    # 远程用户探测失败时，这里是他唯一可发现的诊断现场：留全尝试记录。
    logger.warning("绝区零探测链全落空：configured=%r（注册表/快捷方式/默认均未命中）",
                   str(configured or ""))
    return None, ""


def _shell_launch(exe: Path, game_dir: str) -> int:
    """ShellExecuteW 兜底启动；返回值 ``>32`` 即成功（shell 约定）。"""
    # SW_SHOWNORMAL = 1；lpDirectory 指定游戏目录为工作目录
    return int(ctypes.windll.shell32.ShellExecuteW(
        None, "open", str(exe), None, game_dir, 1))


def picker_start_dir(configured: str | os.PathLike[str] | None) -> str:
    """指路对话框的起始目录。

    用户把游戏搬走后多半搬到了原位置附近：优先失效配置的父目录，其次内置
    默认路径的目录（同机器重装场景），最后退回用户主目录。
    """
    candidate = resolve_game_path(configured)
    for directory in (candidate.parent, Path(DEFAULT_ZZZ_EXE).parent):
        if directory.is_dir():
            return str(directory)
    return str(Path.home())


def launch_exe(exe: Path) -> tuple[bool, str]:
    """启动指定游戏 exe。返回 ``(是否成功发起, 说明)``。"""
    if not exe.is_file():
        return False, f"未找到游戏：{exe}"
    if sys.platform != "win32":
        return False, "启动绝区零仅支持 Windows"

    game_dir = str(exe.parent)
    # 与一条龙一致：start /d 指定工作目录；& exit 让 cmd 立刻退出，不留窗口。
    command = f'cmd /c start "" /d "{game_dir}" "{exe.name}" & exit'
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    # 降级链见模块头注释：breakaway 被宿主 Job 拒绝（WinError 5）时逐级退让，
    # 只有非权限类错误才原样上报（重试不会更好）。
    try:
        subprocess.Popen(command, creationflags=no_window | breakaway)
        return True, ""
    except PermissionError as exc:
        denied = exc
    except OSError as exc:  # noqa: BLE001 - 启动失败要变成气泡提示，不能崩桌宠
        return False, f"启动失败：{exc}"
    try:
        logger.warning("启动游戏时 CREATE_BREAKAWAY_FROM_JOB 被宿主 Job 拒绝"
                       "（%s），去掉该标志重试（游戏随宿主 Job）", denied)
        subprocess.Popen(command, creationflags=no_window)
        return True, ""
    except PermissionError as exc:
        denied2 = exc
    except OSError as exc:  # noqa: BLE001
        return False, f"启动失败：{exc}"
    try:
        logger.warning("去掉 breakaway 仍被拒绝（%s），改走 ShellExecuteW 兜底",
                       denied2)
        rc = _shell_launch(exe, game_dir)
    except OSError as exc:  # noqa: BLE001
        return False, f"启动失败：{exc}"
    if rc > 32:
        return True, ""
    return False, f"启动失败：ShellExecuteW 返回 {rc}"


def launch_game(configured: str | os.PathLike[str] | None = None) -> tuple[bool, str]:
    """探测并启动游戏。返回 ``(是否成功发起, 说明)``。

    - 全探测链未命中 → ``(False, "未找到游戏：...")``，不抛异常；
    - 非 Windows → ``(False, "仅支持 Windows")``；
    - 启动失败 → ``(False, 错误摘要)``；
    - 成功 → ``(True, "")``。
    """
    exe, _source = discover_game(configured)
    if exe is None:
        configured_path = resolve_game_path(configured)
        if str(configured or "").strip():
            return False, (f"配置的路径已失效：{configured_path}"
                           "（游戏搬家后请把新 exe 路径填到 zzz_game_path）")
        return False, (f"未找到游戏：{configured_path}"
                       "（装好绝区零后重试，或把 exe 路径填到 zzz_game_path）")
    return launch_exe(exe)
