# -*- coding: utf-8 -*-
"""位置记忆守卫：自动走动/抛掷/牌局会话中的位置是临时态，退出时不得覆盖用户锚点。

回归（v1.05 前哨）：app 层退出收口曾无条件 save_position，绕过了 window 层
「不保存随机终点」守则（_request_quit / closeEvent 各自注释里的口径）——
退出瞬间宠物正在自主散步时，散步半路的位置被写成家位置，用户实测
「重启之后桌宠的位置变了」。守卫谓词 position_is_transient() 钉在这里。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from pet.config import Config


def _qapp():
    return QApplication.instance() or QApplication([])


def _window(tmp_path):
    from tests.pet_window_fakes import FakeLibrary

    from pet.window import PetWindow

    _qapp()
    cfg = Config(tmp_path)
    cfg.set("auto_hide_fullscreen", False)
    cfg.set("collision_enabled", False)
    win = PetWindow(FakeLibrary(), cfg)
    return win


def test_idle_window_position_is_anchored(tmp_path):
    """待机静置：位置可正常保存（拖拽/缩放/回右下角的默认通路不受影响）。"""
    win = _window(tmp_path)
    try:
        assert win.position_is_transient() is False
    finally:
        win.close()


def test_autonomous_walk_is_transient(tmp_path):
    """自动走动中：位置是临时态，退出保存必须跳过。"""
    win = _window(tmp_path)
    try:
        win._move_plan = {"anim": "walk", "target_x": 100}
        assert win.position_is_transient() is True
    finally:
        win.close()


def test_throw_physics_is_transient(tmp_path):
    """抛掷物理中：落点是随机终点，退出保存必须跳过。"""
    win = _window(tmp_path)
    try:
        win._physics_mode = "throw"
        assert win.position_is_transient() is True
    finally:
        win.close()


def test_game_link_seat_is_transient(tmp_path):
    """骗子酒馆入座会话中（未散场）：座位位置不得覆盖家位置。

    牌局正常散场会恢复 _restore_state 并显式 _save_position（守卫不拦截）；
    游戏 crash/强杀/牌局期间退出时，靠本守卫避免座位坐标固化成家位置。
    """
    win = _window(tmp_path)
    try:
        win._game_link = SimpleNamespace(_restore_state=None)
        assert win.position_is_transient() is False
        win._game_link = SimpleNamespace(_restore_state=(120, 240, 0.8))
        assert win.position_is_transient() is True
    finally:
        win.close()
