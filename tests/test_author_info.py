# -*- coding: utf-8 -*-
"""右键「作者信息」：作者抖音文案 + 照片 + 菜单入口的回归测试。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QMenu

from pet.author_info import (
    AUTHOR_HANDLE,
    AUTHOR_PHOTO,
    AUTHOR_TEXT,
    author_photo_path,
    build_author_dialog,
)
from pet.context_menus.registry import MENU_ACTIONS

app = QApplication.instance() or QApplication([])


def test_author_dialog_shows_handle_and_scaled_photo():
    assert AUTHOR_HANDLE == "4614574078d"
    assert author_photo_path().is_file(), f"作者照片没打包进去：{author_photo_path()}"
    dialog = build_author_dialog()
    try:
        assert dialog.windowTitle() == "作者信息"
        text = dialog.findChild(QLabel, "authorText")
        assert text is not None and AUTHOR_HANDLE in text.text()
        assert "嘴角上扬" in text.text()
        photo = dialog.findChild(QLabel, "authorPhoto")
        assert photo is not None and not photo.pixmap().isNull()
        assert photo.pixmap().width() <= 200 and photo.pixmap().height() <= 200
        assert AUTHOR_PHOTO.endswith("author.jpg")
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_author_info_action_is_registered_and_rendered():
    class Config:
        def get(self, key, default=None):
            return default

    class Pet:
        cfg = Config()

    assert "author_info" in MENU_ACTIONS.ids
    assert MENU_ACTIONS.label("author_info") == "作者信息"
    assert "author_info" in MENU_ACTIONS.available_ids(Pet())
    menu = QMenu()
    try:
        MENU_ACTIONS.populate(
            menu, Pet(), [{"type": "action", "id": "author_info", "visible": True}]
        )
        actions = [action for action in menu.actions() if not action.isSeparator()]
        assert [action.text() for action in actions] == ["作者信息"]
    finally:
        menu.deleteLater()
        app.processEvents()


def test_author_dialog_without_photo_still_shows_handle(monkeypatch):
    """照片缺失时文案仍在：不能因为一张图让整个入口变成空白窗口。"""
    monkeypatch.setattr(
        "pet.author_info.author_photo_path", lambda: author_photo_path().parent / "missing.jpg"
    )
    dialog = build_author_dialog()
    try:
        photo = dialog.findChild(QLabel, "authorPhoto")
        assert photo is not None and bool(photo.property("authorPhotoMissing"))
        text = dialog.findChild(QLabel, "authorText")
        assert text is not None and AUTHOR_HANDLE in text.text()
    finally:
        dialog.deleteLater()
        app.processEvents()
