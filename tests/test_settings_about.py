"""「作者账号」分区已从「更新」页移除；这里守住删除结果与被复用的通用机制。"""
from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from pet.config import Config
from pet.context_menus.icons import THEMED_ICON_REQUEST
from pet.modern_settings_dialog import ModernSettingsDialog
from pet.settings_widgets import refresh_settings_icons

app = QApplication.instance() or QApplication([])

# 作者账号曾经的四个 handle：删除后设置窗任何角落都不该再出现。
FORMER_HANDLES = ("@張墨林", "@快乐小咸鱼a", "@Eager", "@MerZlin")


def test_surviving_settings_icon_still_takes_the_settings_surface_theme():
    """主题重画机制仍覆盖现存消费者（作者按钮和保存按钮都删了，改钉搜索框图标）。

    原来这条用例借作者按钮验证「入口记请求、refresh_settings_icons 按宿主主题
    重画」；现存消费者是搜索框的 leading action，走 QLineEdit 那条重画分支。
    深浅不在控件里钉死：宿主当时什么主题就重画成什么墨色。
    """
    dialog = ModernSettingsDialog(Config(base=None), include_ai=True)
    try:
        dialog.show()
        app.processEvents()
        search = dialog.search_edit
        assert search.property(THEMED_ICON_REQUEST), "搜索框没有登记主题重画请求"
        assert search.actions(), "搜索框缺少 leading 图标 action"
        dialog.setProperty("settingsDark", True)
        refresh_settings_icons(dialog)
        image = search.actions()[0].icon().pixmap(24, 24).toImage()
        pixels = [image.pixelColor(x, y) for y in range(image.height()) for x in range(image.width())]
        assert any(color.alpha() > 200 and color.lightness() > 180 for color in pixels)
    finally:
        dialog.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("include_ai", [True, False])
def test_author_accounts_are_gone_from_the_updates_page(tmp_path, monkeypatch, include_ai):
    """作者账号分区（四个 handle / 复制按钮 / GitHub 跳转）整块不在更新页。

    更新页已从侧栏移除，但 UpdatePage 对象仍保留给菜单入口；直接检查该对象即可。
    """
    cfg = Config(base=tmp_path)
    dialog = ModernSettingsDialog(cfg, include_ai=include_ai)
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    try:
        dialog.show()
        app.processEvents()
        labels = [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())]
        assert "更新" not in labels
        assert "关于" not in labels
        app.processEvents()
        page = dialog.update_page
        before = copy.deepcopy(cfg.data)
        texts = [label.text() for label in page.findChildren(QLabel)]
        assert all(handle not in text for handle in FORMER_HANDLES for text in texts)
        assert not any(label.text() == "作者账号" for label in page.findChildren(QLabel))
        names = [button.accessibleName() for button in page.findChildren(QPushButton)]
        assert not any("账号" in name or "GitHub 主页" in name for name in names)
        assert opened == []
        assert cfg.data == before
    finally:
        dialog.deleteLater()
        app.processEvents()
