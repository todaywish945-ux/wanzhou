# -*- coding: utf-8 -*-
"""「启动绝区零」的回归用例（纯逻辑层，不碰真游戏进程）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from pet import zzz_launcher


def _exe(tmp_path: Path) -> Path:
    """造一个假的 exe 文件供路径检查用。"""
    exe = tmp_path / "ZenlessZoneZero.exe"
    exe.write_bytes(b"fake")
    return exe


# ------------------------------------------------------------- 路径解析
def test_default_path_points_to_real_game() -> None:
    path = zzz_launcher.resolve_game_path(None)
    assert path.name == "ZenlessZoneZero.exe"
    assert "ZenlessZoneZero Game" in str(path)
    assert zzz_launcher.is_game_available(None)


def test_empty_configured_falls_back_to_default() -> None:
    assert zzz_launcher.resolve_game_path("") == zzz_launcher.resolve_game_path(None)
    assert zzz_launcher.resolve_game_path("   ") == zzz_launcher.resolve_game_path(None)


def test_custom_path_wins(tmp_path: Path) -> None:
    exe = _exe(tmp_path)
    assert zzz_launcher.resolve_game_path(str(exe)) == exe
    assert zzz_launcher.is_game_available(str(exe))


def test_tilde_and_env_are_expanded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZZZ_TEST_DIR", str(tmp_path))
    resolved = zzz_launcher.resolve_game_path("$ZZZ_TEST_DIR/ZenlessZoneZero.exe")
    assert resolved == tmp_path / "ZenlessZoneZero.exe"


# ------------------------------------------------------------- 启动行为
def test_launch_missing_exe_reports_stale_config(tmp_path: Path, monkeypatch) -> None:
    """配置路径失效且探测链全落空 → 给出「已失效」的可诊断文案。"""
    monkeypatch.setattr(zzz_launcher, "_hyp_config_discover", lambda: None)
    monkeypatch.setattr(zzz_launcher, "_registry_discover", lambda: None)
    monkeypatch.setattr(zzz_launcher, "_shortcut_discover", lambda: None)
    ok, message = zzz_launcher.launch_game(str(tmp_path / "missing.exe"))
    assert ok is False
    assert "已失效" in message
    assert "missing.exe" in message


def test_stale_configured_path_falls_back_to_registry(tmp_path: Path, monkeypatch) -> None:
    """游戏搬家后缓存路径失效 → 继续探测链（注册表重新命中），而不是硬失败。"""
    stale = tmp_path / "old-place" / "ZenlessZoneZero.exe"  # 不存在
    new_exe = tmp_path / "ZenlessZoneZero.exe"
    new_exe.write_bytes(b"fake")
    monkeypatch.setattr(zzz_launcher, "_hyp_config_discover", lambda: None)
    monkeypatch.setattr(zzz_launcher, "_registry_discover", lambda: new_exe)
    exe, source = zzz_launcher.discover_game(str(stale))
    assert exe == new_exe
    assert source == "registry"


# ------------------------------------------------------------- HYP 启动器记录
def _hyp_dat(tmp_path: Path, install_path: Path | None) -> Path:
    """造一个仿真的 gamedata.dat：二进制框架内嵌 JSON 记录。

    install_path=None 时只含别的游戏（崩三）记录——负例用。
    """
    records: list[bytes] = [
        b'[\x45\x00\x00\xff\xff\xff\x07\x06bh3_cn\xb5',  # 容器框架噪音
        ('{"gameBiz":"honkaiimpact3","installPath":"%s","isCreateShortcut":false}' %
            _json_escape("D:/Launcher/games/Honkai Impact 3rd Game")).encode("utf-8"),
    ]
    if install_path is not None:
        records.append(
            ('{"gameBiz":"nap_cn","installPath":"%s","isCreateShortcut":false}' %
                _json_escape(install_path)).encode("utf-8"))
    dat = tmp_path / "HYP" / "1_2" / "data"
    dat.mkdir(parents=True)
    out = dat / "gamedata.dat"
    out.write_bytes(b"\x00".join(records))
    return out


def _json_escape(path: Path) -> str:
    """路径 → JSON 字符串体（反斜杠双写），与启动器实际写法一致。"""
    return str(path).replace("\\", "\\\\")


@pytest.mark.skipif(sys.platform != "win32", reason="HYP 记录探测仅 Windows")
def test_hyp_config_discover_reads_launcher_record(tmp_path: Path, monkeypatch) -> None:
    """启动器 gamedata.dat 里的 installPath 能被提取并按 exe 存在性校验。"""
    game_dir = tmp_path / "games" / "ZenlessZoneZero Game"
    game_dir.mkdir(parents=True)
    exe = game_dir / "ZenlessZoneZero.exe"
    exe.write_bytes(b"fake")
    dat = _hyp_dat(tmp_path, game_dir)
    monkeypatch.setattr(zzz_launcher, "_HYP_DATA_GLOBS", (str(dat),))
    found = zzz_launcher._hyp_config_discover()
    assert found == exe, "installPath 指向游戏目录，候选 exe 应命中"
    # 只有崩三记录（ZZZ 记录缺位）时不得误命中：exe 校验挡掉异游戏路径
    monkeypatch.setattr(
        zzz_launcher, "_HYP_DATA_GLOBS",
        (str(_hyp_dat(tmp_path / "only-hi3", None)),))
    assert zzz_launcher._hyp_config_discover() is None, \
        "别的游戏的 installPath 不能被当成绝区零"


@pytest.mark.skipif(sys.platform != "win32", reason="HYP 记录探测仅 Windows")
def test_hyp_hit_precedes_registry_and_caches_source(tmp_path: Path, monkeypatch) -> None:
    """探测链顺序：HYP 记录优先于注册表；来源标记为 hyp。"""
    stale = tmp_path / "old-place" / "ZenlessZoneZero.exe"  # 不存在
    hyp_exe = tmp_path / "hyp" / "ZenlessZoneZero.exe"
    hyp_exe.parent.mkdir(parents=True)
    hyp_exe.write_bytes(b"fake")
    dat = _hyp_dat(tmp_path, hyp_exe.parent)
    monkeypatch.setattr(zzz_launcher, "_HYP_DATA_GLOBS", (str(dat),))
    monkeypatch.setattr(
        zzz_launcher, "_registry_discover",
        lambda: (_ for _ in ()).throw(AssertionError("注册表不应在 HYP 之后仍被查询")))
    exe, source = zzz_launcher.discover_game(str(stale))
    assert exe == hyp_exe and source == "hyp"


@pytest.mark.skipif(sys.platform != "win32", reason="HYP 记录探测仅 Windows")
def test_hyp_record_with_moved_game_does_not_hit(tmp_path: Path, monkeypatch) -> None:
    """启动器记录过期（游戏已搬走）不得命中：exe 存在性校验兜底。"""
    gone_dir = tmp_path / "games" / "ZenlessZoneZero Game"  # 不创建 exe
    dat = _hyp_dat(tmp_path, gone_dir)
    monkeypatch.setattr(zzz_launcher, "_HYP_DATA_GLOBS", (str(dat),))
    assert zzz_launcher._hyp_config_discover() is None


def test_valid_configured_path_still_wins(tmp_path: Path, monkeypatch) -> None:
    """配置路径存在时依旧最高优先，探测链不介入。"""
    exe = _exe(tmp_path)
    monkeypatch.setattr(
        zzz_launcher, "_registry_discover",
        lambda: (_ for _ in ()).throw(AssertionError("探测链不应被触发")))
    exe_found, source = zzz_launcher.discover_game(str(exe))
    assert exe_found == exe and source == "config"


def test_launch_calls_popen_with_start_and_workdir(tmp_path: Path, monkeypatch) -> None:
    """启动走 cmd start /d <目录>，且带 job 逃离标志（游戏不被桌宠退出带走）。"""
    exe = _exe(tmp_path)
    calls = []

    class _FakePopen:
        def __init__(self, command, **kwargs):
            calls.append((command, kwargs))

    monkeypatch.setattr(zzz_launcher.subprocess, "Popen", _FakePopen)
    ok, message = zzz_launcher.launch_game(str(exe))
    assert ok is True and message == ""
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert "cmd /c start" in command
    assert str(tmp_path) in command and exe.name in command
    assert kwargs["creationflags"] != 0


def test_launch_failure_is_reported_not_raised(tmp_path: Path, monkeypatch) -> None:
    """启动异常要变成气泡提示，不能把桌宠搞崩。"""
    exe = _exe(tmp_path)

    def _boom(*args, **kwargs):
        raise OSError("spawn failed")

    monkeypatch.setattr(zzz_launcher.subprocess, "Popen", _boom)
    ok, message = zzz_launcher.launch_game(str(exe))
    assert ok is False
    assert "spawn failed" in message


@pytest.mark.skipif(sys.platform != "win32", reason="Job/ShellExecute 语义仅 Windows")
def test_launch_retries_without_breakaway_on_access_denied(
        tmp_path: Path, monkeypatch) -> None:
    """宿主 Job 不容许 breakaway（WinError 5）时去掉标志重试，而不是直接报错。

    2026-11-28 实机：Win11 26200 把所有进程装进不容许 breakaway 的 Job，
    原实现无条件带 ``CREATE_BREAKAWAY_FROM_JOB`` → 气泡「启动失败：[WinError 5]」。
    """
    exe = _exe(tmp_path)
    breakaway = subprocess.CREATE_BREAKAWAY_FROM_JOB
    flags_seen: list[int] = []

    class _DenyBreakawayPopen:
        def __init__(self, command, **kwargs):
            flags_seen.append(kwargs.get("creationflags", 0))
            if kwargs.get("creationflags", 0) & breakaway:
                raise PermissionError(5, "拒绝访问")

    monkeypatch.setattr(zzz_launcher.subprocess, "Popen", _DenyBreakawayPopen)
    ok, message = zzz_launcher.launch_game(str(exe))
    assert ok is True and message == ""
    assert len(flags_seen) == 2, "必须先试 breakaway，被拒后去掉标志重试一次"
    assert flags_seen[0] & breakaway
    assert not flags_seen[1] & breakaway


@pytest.mark.skipif(sys.platform != "win32", reason="Job/ShellExecute 语义仅 Windows")
def test_launch_falls_back_to_shell_when_popen_always_denied(
        tmp_path: Path, monkeypatch) -> None:
    """两级 Popen 都被拒时走 ShellExecuteW 兜底；返回值 >32 视为成功。"""
    exe = _exe(tmp_path)

    def _deny(*args, **kwargs):
        raise PermissionError(5, "拒绝访问")

    monkeypatch.setattr(zzz_launcher.subprocess, "Popen", _deny)
    shell_calls: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        zzz_launcher, "_shell_launch",
        lambda target, game_dir: shell_calls.append((target, game_dir)) or 33)
    ok, message = zzz_launcher.launch_game(str(exe))
    assert ok is True and message == ""
    assert shell_calls == [(exe, str(tmp_path))]


@pytest.mark.skipif(sys.platform != "win32", reason="Job/ShellExecute 语义仅 Windows")
def test_launch_shell_fallback_failure_is_reported(tmp_path: Path, monkeypatch) -> None:
    """兜底也失败（ShellExecuteW 返回值 <=32）要给出可诊断的气泡文案。"""
    exe = _exe(tmp_path)
    monkeypatch.setattr(zzz_launcher.subprocess, "Popen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            PermissionError(5, "拒绝访问")))
    monkeypatch.setattr(zzz_launcher, "_shell_launch", lambda target, game_dir: 2)
    ok, message = zzz_launcher.launch_game(str(exe))
    assert ok is False
    assert "ShellExecuteW 返回 2" in message


# ------------------------------------------------------------- 指路对话框起始目录
def test_picker_start_dir_prefers_stale_config_dir(tmp_path: Path) -> None:
    """搬过家的场景：失效配置的父目录存在 → 从那里开始找（用户多半搬去附近）。"""
    stale_dir = tmp_path / "old-place"
    stale_dir.mkdir()
    stale = stale_dir / "ZenlessZoneZero.exe"  # 不存在的失效路径
    assert zzz_launcher.picker_start_dir(str(stale)) == str(stale_dir)


def test_picker_start_dir_falls_back_to_default_game_dir(tmp_path: Path) -> None:
    """空配置 → 内置默认路径的目录（同机重装场景）。"""
    start = zzz_launcher.picker_start_dir("")
    assert Path(start) == Path(zzz_launcher.DEFAULT_ZZZ_EXE).parent


def test_picker_start_dir_ultimately_home(tmp_path: Path, monkeypatch) -> None:
    """失效配置与默认目录都不存在 → 用户主目录兜底。"""
    monkeypatch.setattr(zzz_launcher, "DEFAULT_ZZZ_EXE",
                        str(tmp_path / "gone" / "ZenlessZoneZero.exe"))
    assert Path(zzz_launcher.picker_start_dir(str(tmp_path / "gone2" / "x.exe"))) == Path.home()


@pytest.mark.skipif(sys.platform != "win32", reason="绝区零仅 Windows")
def test_default_game_is_installed_on_this_machine() -> None:
    """本机实测：默认路径确实存在（换机部署时这条会提示要改默认路径）。"""
    assert zzz_launcher.is_game_available(None)
