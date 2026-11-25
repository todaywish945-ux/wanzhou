# -*- coding: utf-8 -*-
"""灵动岛「聊天」按钮：弹出角色选择菜单 → 打开对应角色的敲敲聊天窗。

背景（2026-11-24）：用户反馈旧的岛卡片「聊天」只作用于角色A（岛只在A进程），
且对话气泡只针对A、对 B/C 无效。按用户要求删除气泡与显隐按钮后，「聊天」改为
显式选角色 + 按角色打开/切换聊天窗（KKWebWindow 的会话按角色分 slot 隔离）。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from pet.app import AppShell
from pet.catalog import DEFAULT_CHARACTER


def _shell(tmp_path, *, enable_chat=True):
    shell = AppShell.__new__(AppShell)
    shell.config = SimpleNamespace(
        dir=tmp_path,
        get=lambda key, default=None: (
            "角色A" if key == "character" else default),
        character_display_name=lambda cid: f"显示名-{cid}",
    )
    shell.enable_chat = enable_chat
    shell.island = None
    shell.instance = SimpleNamespace(
        open_chat_with_character=lambda cid: shell.calls.append(cid))
    shell.calls: list[str] = []
    return shell


def test_chat_button_pops_role_menu_and_opens_selected(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMenu

    shell = _shell(tmp_path)
    chosen = ["角色B"]

    # 用假 QMenu 捕获三个角色条目并模拟点第二个（角色B）
    class FakeMenu:
        def __init__(self, *a, **k):
            self.actions: list = []

        def setTitle(self, _t):
            pass

        def addAction(self, label):
            # 假 triggered 信号：connect 存下回调，exec 时手动触发
            holder = {"cb": None, "label": label}
            holder["triggered"] = SimpleNamespace(
                connect=lambda cb, h=holder: h.__setitem__("cb", cb))
            self.actions.append(holder)
            return SimpleNamespace(
                triggered=holder["triggered"], label=label)

        def exec(self, _pos):
            # 触发第二个 action 的 triggered 回调（lambda _checked=False, cid=...）
            self.actions[1]["cb"](False)

    monkeypatch.setattr("PySide6.QtWidgets.QMenu", FakeMenu)
    shell._open_chat_from_island()
    assert shell.calls == ["角色B"], shell.calls


def test_chat_button_no_chat_build_does_nothing(tmp_path, monkeypatch):
    shell = _shell(tmp_path, enable_chat=False)
    shell._open_chat_from_island()
    assert shell.calls == []


def test_open_chat_with_character_rejects_invalid(tmp_path):
    from pet.app import PetInstance

    inst = PetInstance.__new__(PetInstance)
    inst.enable_chat = True
    inst.knock_chat_window = None
    # 非法角色应直接返回，不碰聊天窗构造
    inst.open_chat_with_character("不存在")
    assert getattr(inst, "knock_chat_window", None) is None


def test_island_chat_bubble_stays_disabled(tmp_path):
    """气泡已移除：可用性门恒 False（所有弹气泡路径自动失效）。"""
    shell = _shell(tmp_path)
    assert shell._island_chat_available() is False
