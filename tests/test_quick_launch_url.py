# -*- coding: utf-8 -*-
"""快捷启动「添加网址」测试：菜单项、编辑器落点、打开 URL。"""
from __future__ import annotations


def test_add_menu_has_url_action():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.settings_widgets import QuickLaunchEditor

    editor = QuickLaunchEditor([], None)
    labels = [a.text() for a in editor.add_menu.actions()]
    assert "添加网址…" in labels
    assert "选择应用…" in labels
    assert editor.add_url_action is not None


def test_add_app_url_kind_keeps_name_and_path():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.settings_widgets import QuickLaunchEditor

    editor = QuickLaunchEditor([], None)
    editor.add_app({"name": "B站", "path": "https://www.bilibili.com", "kind": "url"})
    assert editor.apps() == [
        {"name": "B站", "path": "https://www.bilibili.com", "kind": "url"}
    ]


def test_launch_url_uses_default_browser(monkeypatch):
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.context_menus import quick_launch

    opened: list[str] = []
    monkeypatch.setattr(
        quick_launch.QDesktopServices, "openUrl",
        staticmethod(lambda url: opened.append(url.toString()) or True),
    )

    assert quick_launch.launch_quick_app(
        {"name": "B站", "path": "https://www.bilibili.com", "kind": "url"}
    ) is True
    assert opened == ["https://www.bilibili.com"]


def test_launch_url_adds_https_scheme(monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.context_menus import quick_launch

    opened: list[str] = []
    monkeypatch.setattr(
        quick_launch.QDesktopServices, "openUrl",
        staticmethod(lambda url: opened.append(url.toString()) or True),
    )
    quick_launch.launch_quick_app({"name": "x", "path": "www.example.com", "kind": "url"})
    assert opened == ["https://www.example.com"]


def test_launch_url_empty_is_noop(monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.context_menus import quick_launch

    monkeypatch.setattr(
        quick_launch.QDesktopServices, "openUrl",
        staticmethod(lambda url: (_ for _ in ()).throw(AssertionError("不该调用"))),
    )
    assert quick_launch.launch_quick_app({"name": "x", "path": "", "kind": "url"}) is False


def test_legacy_application_kind_with_url_path_opens_browser(monkeypatch):
    """旧设置进程把网址以 application 存盘：点按仍应走浏览器而非 os.startfile。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.context_menus import quick_launch

    opened: list[str] = []
    monkeypatch.setattr(
        quick_launch.QDesktopServices, "openUrl",
        staticmethod(lambda url: opened.append(url.toString()) or True),
    )
    # 若误走 os.startfile，这里会被 monkeypatch 的 openUrl 捕获不到 → 断言失败
    assert quick_launch.launch_quick_app(
        {"name": "bilibili", "path": "https://www.bilibili.com/", "kind": "application"}
    ) is True
    assert opened == ["https://www.bilibili.com/"]


def test_looks_like_url_guard():
    from pet.context_menus.quick_launch import _looks_like_url

    assert _looks_like_url("https://www.bilibili.com/")
    assert _looks_like_url("HTTP://example.com")
    assert _looks_like_url("www.example.com")
    assert not _looks_like_url(r"C:/Program Files/app.exe")
    assert not _looks_like_url("notepad.exe")
    assert not _looks_like_url("")


def test_default_browser_opens_blank_without_network(monkeypatch):
    """「默认浏览器」项打开 about:blank——零网络请求，不会再转圈。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.context_menus import quick_launch

    opened: list[str] = []
    monkeypatch.setattr(
        quick_launch.QDesktopServices, "openUrl",
        staticmethod(lambda url: opened.append(url.toString()) or True),
    )
    assert quick_launch.launch_quick_app(
        {"name": "默认浏览器", "path": "", "kind": "default_browser"}
    ) is True
    assert opened == ["about:blank"]
    assert not any("google" in u for u in opened)
