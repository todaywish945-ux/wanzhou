# -*- coding: utf-8 -*-
"""「启动绝区零」子菜单回归：地址展示 / 未找到降级 / 手动指路入口。

建造器只读 pet.cfg 与探测链，不点真菜单动作（启动链路有独立回归）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="绝区零菜单仅 Windows")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakePet:
    """最小 pet 桩：只暴露 zzz builder 用到的面。"""

    def __init__(self, cfg=None):
        self._cfg = cfg
        self.calls: list[str] = []

    @property
    def cfg(self):
        if self._cfg is None:
            raise AttributeError("cfg 未注入")
        return self._cfg

    def on_launch_zzz(self):
        self.calls.append("launch")

    def on_pick_zzz_path(self):
        self.calls.append("pick")


def _build(pet):
    from PySide6.QtWidgets import QMenu

    from pet.context_menus.registry import _add_zzz_launcher
    menu = QMenu()
    _add_zzz_launcher(menu, pet)
    submenu = menu.actions()[0].menu()
    assert submenu is not None, "zzz_launcher 必须是带箭头的子菜单"
    return menu, submenu


def _texts(submenu):
    return [a.text() for a in submenu.actions()]


def test_submenu_shows_launch_path_and_pick(qapp, tmp_path, monkeypatch):
    """探测命中：启动 + 📍 地址（禁用）+ 手动指定 三件套。"""
    from pet import zzz_launcher
    exe = tmp_path / "ZenlessZoneZero.exe"
    exe.write_bytes(b"fake")
    monkeypatch.setattr(zzz_launcher, "discover_game", lambda cfg: (exe, "hyp"))
    pet = _FakePet(cfg={})
    menu, submenu = _build(pet)
    texts = _texts(submenu)
    assert any(t == "🎮 启动" for t in texts)
    assert any(t.startswith("📍") and str(exe) in t for t in texts), "地址必须展示给用户"
    assert any("手动指定路径" in t for t in texts)
    # 地址行只读：点了不该有任何动作
    path_act = next(a for a in submenu.actions() if a.text().startswith("📍"))
    assert not path_act.isEnabled()
    # 点「启动」走完整链路回调
    launch_act = next(a for a in submenu.actions() if a.text() == "🎮 启动")
    launch_act.trigger()
    assert pet.calls == ["launch"]
    menu.close()


def test_submenu_degrades_when_nothing_found(qapp, monkeypatch):
    """探测全落空：提示行（禁用）+ 手动指定仍在——指路就是这时候的出路。"""
    from pet import zzz_launcher
    monkeypatch.setattr(zzz_launcher, "discover_game", lambda cfg: (None, ""))
    pet = _FakePet(cfg={})
    menu, submenu = _build(pet)
    texts = _texts(submenu)
    assert any("还没找到游戏" in t for t in texts)
    assert any("手动指定路径" in t for t in texts), "找不到时更要有指路入口"
    assert not any(t == "🎮 启动" for t in texts)
    menu.close()


def test_submenu_survives_discovery_crash_and_missing_cfg(qapp, monkeypatch):
    """探测抛异常 / pet 没有 cfg：菜单必须照常弹出（降级为未找到态）。"""
    from pet import zzz_launcher

    def _boom(cfg):
        raise RuntimeError("探测炸了")

    monkeypatch.setattr(zzz_launcher, "discover_game", _boom)
    pet = _FakePet(cfg={})
    menu, submenu = _build(pet)
    assert any("还没找到游戏" in t for t in _texts(submenu))
    menu.close()


def test_pick_action_wires_to_on_pick_zzz_path(qapp, monkeypatch):
    from pet import zzz_launcher
    monkeypatch.setattr(zzz_launcher, "discover_game", lambda cfg: (None, ""))
    pet = _FakePet(cfg={})
    menu, submenu = _build(pet)
    pick_act = next(a for a in submenu.actions() if "手动指定" in a.text())
    pick_act.trigger()
    assert pet.calls == ["pick"]
    menu.close()
