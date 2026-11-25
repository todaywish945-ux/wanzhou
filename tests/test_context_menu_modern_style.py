# -*- coding: utf-8 -*-
"""modern 菜单样式的平台窗口标志回归。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMenu

app = QApplication.instance() or QApplication([])


def test_modern_menu_has_frameless_hint_on_windows():
    """Windows 下 modern 菜单必须带 FramelessWindowHint——否则 QPA 不挂
    WS_EX_LAYERED，圆角外的透明像素被当成不透明黑（四角黑边，PR #341 根因）。
    非 Windows 不置位（各平台原生弹窗行为不动）。"""
    from pet.context_menus.menu_styles.modern import apply_modern_menu_style

    menu = QMenu()
    apply_modern_menu_style(menu)
    has_flag = bool(menu.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert has_flag is (sys.platform == "win32")
    menu.deleteLater()


def test_legacy_neutral_grey_appearance_upgrades_to_dusk_palette():
    """老配置把中性灰默认值显式写进了角色配置；只改 DEFAULT 不会生效。

    读取时把「仍是旧默认值」的六档颜色升到暮灯配色，用户自选的非默认值保持原样。
    """
    from pet.config import _clean_menu_appearance

    legacy = {
        "light_background": "#ffffff",
        "light_foreground": "#171717",
        "light_hover": "#eeeeee",
        "dark_background": "#252525",
        "dark_foreground": "#f3f3f3",
        "dark_hover": "#3a3a3a",
    }
    cleaned = _clean_menu_appearance(legacy)
    assert cleaned["light_background"] == "#fffcf7"
    assert cleaned["light_foreground"] == "#3a2f24"
    assert cleaned["light_hover"] == "#f3e2c1"
    assert cleaned["dark_background"] == "#282329"
    assert cleaned["dark_foreground"] == "#f2e4cf"
    assert cleaned["dark_hover"] == "#443338"

    custom = _clean_menu_appearance({"dark_background": "#111213", "dark_hover": "#3a3a3a"})
    assert custom["dark_background"] == "#111213", "用户自选色不该被迁移覆盖"
    assert custom["dark_hover"] == "#443338", "仍是旧默认值的那一档照常升级"


def test_menu_icons_are_soft_filled_not_hollow_outlines():
    """图标换样：略粗描边 + 淡填充闭合图形，区别于参考项目的纯空心细线稿。"""
    from pet.context_menus.icons import vector_menu_icon
    from pet.context_menus.menu_styles.modern import apply_modern_menu_style

    menu = QMenu()
    apply_modern_menu_style(menu, {"theme": "light"})
    icon = vector_menu_icon(menu, "chat")
    image = icon.pixmap(18, 18).toImage()
    soft = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if 24 < image.pixelColor(x, y).alpha() < 200
    )
    assert soft >= 20, f"闭合图形没有淡填充（半透明像素只有 {soft} 个）"
    menu.close()
