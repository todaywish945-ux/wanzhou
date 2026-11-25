# -*- coding: utf-8 -*-
"""自动更新功能的 UI/进程接线回归。"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_settings_has_version_footer_and_update_page(tmp_path, monkeypatch):
    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config

    _qapp()
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    dialog = settings_mod.ModernSettingsDialog(Config(tmp_path), include_ai=False)
    try:
        labels = [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())]
        # 更新页已从设置侧栏移除（没有可用发布源），但 UpdatePage 对象保留给菜单入口。
        assert "更新" not in labels
        assert dialog.version_footer.objectName() == "settingsVersion"
        assert dialog.version_footer.text().startswith("版本 v")
        assert dialog.update_page.findChild(settings_mod.QPushButton, "checkUpdateButton") is not None
        assert dialog.update_page.findChild(settings_mod.QPushButton, "installUpdateButton") is not None
        assert dialog.select_page("更新") is False
    finally:
        dialog.close()


def test_settings_update_page_does_not_write_config(tmp_path, monkeypatch):
    from pet import updater
    from pet.config import Config
    from pet.update_settings import UpdatePage

    _qapp()
    config = Config(tmp_path)
    before = config.path.read_bytes() if config.path.exists() else None
    page = UpdatePage(config, include_chat=False)
    # 模拟版本必须比当前 __version__ 新（版本号会随发布上涨，写死必腐坏）
    from pet import __version__ as _cur
    _parts = [int(x) for x in _cur.split(".")]
    _parts[-1] += 1
    newer = ".".join(str(x) for x in _parts)
    release = {
        "version": newer,
        "notes": "notes",
        "assets": {},
        "asset_details": {},
        "html_url": "https://github.com/todaywish945-ux/wanzhou/releases",
    }
    page._on_check_finished(release)
    assert page.status_label.text().startswith(f"发现 v{newer}")
    after = config.path.read_bytes() if config.path.exists() else None
    assert after == before
    page.close()


def test_update_dialog_reuses_prefetched_release(tmp_path, monkeypatch):
    """菜单「检查更新」已经查过一次，更新窗直接显示结果、不再打网络。"""
    from pet import __version__ as _cur
    from pet.config import Config
    from pet.update_settings import UpdateDialog

    qapp = _qapp()
    check_calls = []
    monkeypatch.setattr(
        "pet.update_settings.UpdatePage.check_for_updates",
        lambda self: check_calls.append(True),
    )
    parts = [int(x) for x in _cur.split(".")]
    parts[-1] += 1
    newer = ".".join(str(x) for x in parts)
    release = {
        "version": newer,
        "notes": "新版本",
        "assets": {},
        "asset_details": {},
        "html_url": "https://github.com/todaywish945-ux/wanzhou/releases",
    }
    dialog = UpdateDialog(Config(tmp_path), release=release)
    try:
        assert check_calls == []
        assert dialog.page.status_label.text().startswith(f"发现 v{newer}")
        assert dialog.page.notes_label.text().startswith("新版本")
        qapp.processEvents()
        assert check_calls == []  # apply_release 不该触发二次检查
    finally:
        dialog.close()


def test_update_dialog_shows_baidu_link_and_code(tmp_path, monkeypatch):
    """开源版没有安装包时，更新窗必须把网盘链接和提取码一并给人。"""
    from pet import __version__ as _cur
    from pet.config import Config
    from pet.update_settings import UpdateDialog

    qapp = _qapp()
    opened = []
    monkeypatch.setattr(
        "pet.update_settings.QDesktopServices.openUrl",
        lambda url: opened.append(url.toString()),
    )
    parts = [int(x) for x in _cur.split(".")]
    parts[-1] += 1
    newer = ".".join(str(x) for x in parts)
    release = {
        "version": newer,
        "notes": "新版说明",
        "html_url": "https://github.com/todaywish945-ux/wanzhou/releases",
        "download_url": "https://pan.baidu.com/s/abc123",
        "download_code": "wz26",
        "assets": {},
        "asset_details": {},
    }
    dialog = UpdateDialog(Config(tmp_path), release=release)
    try:
        assert "https://pan.baidu.com/s/abc123" in dialog.page.notes_label.text()
        assert "提取码：wz26" in dialog.page.notes_label.text()
        assert dialog.page.install_button.isEnabled() is False
        dialog.page.open_download_page()
        qapp.processEvents()
        assert opened == ["https://pan.baidu.com/s/abc123"]
    finally:
        dialog.close()


def test_settings_process_page_deep_link_is_passed(tmp_path, monkeypatch):
    from pet.app import AppShell
    from pet.config import Config

    shell = AppShell.__new__(AppShell)
    shell.config = Config(tmp_path)
    shell._settings_process_running = lambda: False
    shell._settings_launch_pending = lambda: False
    shell._install_config_watcher = lambda: None
    shell._mark_settings_child = lambda active: None
    calls = []
    monkeypatch.setattr(
        shell,
        "_launch_settings_process",
        lambda instance=None, *, page=None: calls.append((instance, page)) or True,
    )
    instance = object()
    assert shell.open_settings_process(instance, page="更新") is True
    assert calls == [(instance, "更新")]
