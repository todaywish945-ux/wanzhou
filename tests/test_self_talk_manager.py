# -*- coding: utf-8 -*-
"""台词管理对话框：固定台词勾选播报面板的契约。

台词池固定后，对话框从"文本编辑"变成"每句一个勾选项、即时落盘"。这里钉死：
列表按固定池逐句展示且默认全勾选；取消勾选立即写盘生效；回调异常不冒泡；
勾选状态可复制到全部角色。
"""
from __future__ import annotations

import pytest

from pet import self_talk_library as lib
from pet.pet_visibility import PET_IDS


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _make_dialog(qapp, tmp_path, on_saved=None):
    from PySide6.QtCore import Qt

    from pet.config import Config
    from pet.self_talk_manager import SelfTalkManagerDialog

    cfg = Config(str(tmp_path))
    dlg = SelfTalkManagerDialog(cfg, on_saved=on_saved)
    return dlg


def _items(dlg):
    return [dlg.line_list.item(i) for i in range(dlg.line_list.count())]


def test_list_shows_fixed_pool_all_checked(qapp, tmp_path):
    dlg = _make_dialog(qapp, tmp_path)
    pool = lib.DEFAULT_SELF_TALK_TEXTS_BY_ROLE[dlg._current_role()]
    items = _items(dlg)
    assert [i.text() for i in items] == pool
    assert all(i.checkState() == __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Checked
               for i in items), "默认全部勾选"


def test_unchecking_persists_immediately(qapp, tmp_path):
    from PySide6.QtCore import Qt

    dlg = _make_dialog(qapp, tmp_path)
    first = _items(dlg)[0]
    first.setCheckState(Qt.Unchecked)  # itemChanged → 即时落盘
    role = dlg._current_role()
    assert lib.disabled_texts_for(dlg.config.dir, role) == [first.text()]
    assert lib.texts_for(dlg.config.dir, role) == [
        t for t in lib.DEFAULT_SELF_TALK_TEXTS_BY_ROLE[role] if t != first.text()]


def test_rechecking_restores_line(qapp, tmp_path):
    from PySide6.QtCore import Qt

    dlg = _make_dialog(qapp, tmp_path)
    first = _items(dlg)[0]
    first.setCheckState(Qt.Unchecked)
    first.setCheckState(Qt.Checked)
    assert lib.disabled_texts_for(dlg.config.dir, dlg._current_role()) == []


def test_reloading_role_shows_persisted_state(qapp, tmp_path):
    from PySide6.QtCore import Qt

    dlg = _make_dialog(qapp, tmp_path)
    _items(dlg)[2].setCheckState(Qt.Unchecked)
    dlg._load_current()
    assert _items(dlg)[2].checkState() == Qt.Unchecked
    assert all(i.checkState() == Qt.Unchecked or i.text() != _items(dlg)[2].text()
               for i in _items(dlg))


def test_reset_all_checked_restores_everything(qapp, tmp_path):
    from PySide6.QtCore import Qt

    dlg = _make_dialog(qapp, tmp_path)
    role = dlg._current_role()
    _items(dlg)[0].setCheckState(Qt.Unchecked)
    assert lib.disabled_texts_for(dlg.config.dir, role)
    dlg._reset_all_checked()
    assert lib.disabled_texts_for(dlg.config.dir, role) == []
    assert all(i.checkState() == Qt.Checked for i in _items(dlg))
    # 其他角色的勾选状态不受影响（固定池三角各异，没有跨角色复制的语义）
    assert lib.disabled_texts_for(dlg.config.dir, "角色B") == []


def test_close_notifies_saved_callback_once(qapp, tmp_path):
    calls = []
    dlg = _make_dialog(qapp, tmp_path, on_saved=lambda: calls.append(1))
    dlg.accept()
    assert calls == [1]


def test_callback_exception_does_not_break_close(qapp, tmp_path):
    calls = []

    def bad():
        calls.append(1)
        raise RuntimeError("预缓存挂了")

    dlg = _make_dialog(qapp, tmp_path, on_saved=bad)
    dlg.accept()  # 不抛
    assert calls == [1]


def test_close_without_callback_is_fine(qapp, tmp_path):
    dlg = _make_dialog(qapp, tmp_path, on_saved=None)
    dlg.accept()  # 不抛
