# -*- coding: utf-8 -*-
"""「启动绝区零」的回归用例（纯逻辑层，不碰真游戏进程）。"""
from __future__ import annotations

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
def test_launch_missing_exe_returns_failure(tmp_path: Path) -> None:
    ok, message = zzz_launcher.launch_game(str(tmp_path / "missing.exe"))
    assert ok is False
    assert "未找到游戏" in message


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


@pytest.mark.skipif(sys.platform != "win32", reason="绝区零仅 Windows")
def test_default_game_is_installed_on_this_machine() -> None:
    """本机实测：默认路径确实存在（换机部署时这条会提示要改默认路径）。"""
    assert zzz_launcher.is_game_available(None)
