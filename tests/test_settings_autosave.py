# -*- coding: utf-8 -*-
"""设置窗「边改边存」：改完不用点保存，也不用记得关窗前再确认一次。

用户反馈：设置里改了东西，直接退出就忘了保存。设置窗原本关窗（X / Esc）就会
整表落盘，但开着窗口期间所有改动只在控件草稿里——进程被强杀、或关掉的是整个
桌宠而不是设置窗时，草稿就没了。这里钉住新口径：控件改动后防抖自动落盘，
复用原有 ``_write_config``（配置分流、写锁、失败分类都不另起炉灶），关窗闸门
仍只写一次。
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _config(tmp_path):
    from pet.config import Config

    return Config(base=tmp_path)


def _dialog(tmp_path):
    from pet.modern_settings_dialog import ModernSettingsDialog

    dialog = ModernSettingsDialog(_config(tmp_path), include_ai=False)
    dialog.resize(800, 560)
    dialog.show()
    return dialog


def _status(dialog):
    from PySide6.QtWidgets import QLabel

    return dialog.findChild(QLabel, "settingsAutosaveStatus")


def _disk_value(tmp_path, key):
    path = _config(tmp_path).path
    return json.loads(path.read_text(encoding="utf-8")).get(key)


def _count_writes(dialog, calls) -> None:
    """在构造完成后替换写回入口：自动保存与关窗都只能走这一条。"""
    original = dialog._write_config

    def counted():
        calls.append(1)
        return original()

    dialog._write_config = counted


def test_control_change_is_saved_after_debounce_without_closing(tmp_path, app):
    """拨一下开关、停一下：磁盘上就是新值，窗口还开着。"""
    from PySide6.QtTest import QTest

    config = _config(tmp_path)
    dialog = _dialog(tmp_path)
    try:
        app.processEvents()
        target = not bool(config.get("on_top"))
        dialog.on_top_check.setChecked(target)
        QTest.qWait(900)  # 自动保存延时 700ms + 余量
        assert _disk_value(tmp_path, "on_top") is target
        assert _status(dialog).text().startswith("已自动保存")
        assert dialog.isVisible()
    finally:
        dialog.close()


def test_rapid_changes_write_once(tmp_path, app):
    """逐字/连拨只落一次盘：防抖定时器每次改动都重置。"""
    from PySide6.QtTest import QTest

    dialog = _dialog(tmp_path)
    calls: list[int] = []
    _count_writes(dialog, calls)
    try:
        app.processEvents()
        # 末值取非默认（on_top 出厂是 True）：Config.save 只写与基线不同的键，
        # 首尾都是默认值时盘上没这个键是合法的，不该拿它判"没保存"。
        for value in (True, False, True, False):
            dialog.on_top_check.setChecked(value)
            QTest.qWait(60)
        assert calls == [], "还没停手就落盘了（防抖没生效）"
        QTest.qWait(900)
        assert len(calls) == 1, f"连续 4 次改动应只写一次，实际 {len(calls)} 次"
        assert _disk_value(tmp_path, "on_top") is False
    finally:
        dialog.close()


def test_close_with_pending_autosave_writes_once(tmp_path, app):
    """改完立刻关窗：定时器让位给关闭闸门，同一批改动只写一次。"""
    dialog = _dialog(tmp_path)
    calls: list[int] = []
    _count_writes(dialog, calls)
    try:
        app.processEvents()
        dialog.on_top_check.setChecked(not bool(dialog.config.get("on_top")))
        dialog.close()
        app.processEvents()
        assert len(calls) == 1, f"关窗前后合计应只写一次，实际 {len(calls)} 次"
    finally:
        import shiboken6

        if shiboken6.isValid(dialog):
            dialog.close()


def test_opening_settings_does_not_save_by_itself(tmp_path, app):
    """菜单编排刷新会 emit changed 但布局没变，开窗不该白白写盘。"""
    dialog = _dialog(tmp_path)
    calls: list[int] = []
    _count_writes(dialog, calls)
    try:
        dialog.show()
        app.processEvents()
        assert calls == [], "刚打开设置就落盘了（把程序性刷新当成了用户改动）"
        assert _status(dialog).text() == "改动会自动保存"
    finally:
        dialog.close()


def test_autosave_failure_is_silent_but_visible(tmp_path, app, monkeypatch):
    """自动保存失败不弹框、不关窗，只把失败写到状态行；关窗闸门仍保留原逻辑。"""
    from PySide6.QtTest import QTest

    dialog = _dialog(tmp_path)
    real_write = dialog._write_config
    seen: list[int] = []

    def failing():
        seen.append(1)
        dialog._write_failure = object()
        return False

    monkeypatch.setattr(dialog, "_write_config", failing)
    try:
        app.processEvents()
        dialog.on_top_check.setChecked(not bool(dialog.config.get("on_top")))
        QTest.qWait(900)
        assert len(seen) == 1
        assert dialog.isVisible(), "自动保存失败不该把设置窗关掉"
        assert "失败" in _status(dialog).text()
        # 跳过关窗闸门（它失败时按原设计会留在窗口里），直接收口释放对话框
        monkeypatch.setattr(dialog, "_write_config", real_write)
        dialog._close_after_external_write()
    finally:
        import shiboken6

        if shiboken6.isValid(dialog):
            dialog.close()


def test_disk_conflict_retries_automatically(tmp_path, app, monkeypatch):
    """目录锁冲突报 disk：等一拍自动重试，成功后状态回到已保存。"""
    from PySide6.QtTest import QTest

    from pet.settings_slot_config import SaveFailure

    dialog = _dialog(tmp_path)
    real_write = dialog._write_config
    seen: list[int] = []

    def flaky():
        seen.append(1)
        if len(seen) == 1:
            dialog._write_failure = SaveFailure(kind="disk", status="lock-timeout")
            return False
        dialog._write_failure = None
        return True

    monkeypatch.setattr(dialog, "_write_config", flaky)
    try:
        app.processEvents()
        dialog.on_top_check.setChecked(not bool(dialog.config.get("on_top")))
        QTest.qWait(900)
        assert len(seen) == 1
        assert "重试" in _status(dialog).text()
        QTest.qWait(1800)
        assert len(seen) == 2, "disk 失败后应自动重试一次"
        assert _status(dialog).text().startswith("已自动保存")
    finally:
        monkeypatch.setattr(dialog, "_write_config", real_write)
        dialog.close()
