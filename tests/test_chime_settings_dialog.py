# -*- coding: utf-8 -*-
"""轻量报时设置对话框：时间点写入与同步回调测试。"""
from __future__ import annotations


def test_dialog_loads_existing_config(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.config import Config
    from pet.voice.chime_settings_dialog import ChimeSettingsDialog

    cfg = Config(str(tmp_path))
    cfg.set("voice_chime_schedule", "custom")
    cfg.set("voice_chime_custom_times", "09:00,18:30")
    cfg.set("voice_chime_volume", 55)
    dlg = ChimeSettingsDialog(cfg)
    assert dlg._schedule.currentData() == "custom"
    assert dlg._times.text() == "09:00,18:30"
    assert dlg._volume.value() == 55
    assert dlg._times.isEnabled()  # custom 模式才启用时间点输入


def test_dialog_saves_cleaned_times_and_calls_sync(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.config import Config
    from pet.voice.chime_settings_dialog import ChimeSettingsDialog

    cfg = Config(str(tmp_path))
    saved: list[int] = []
    dlg = ChimeSettingsDialog(cfg, on_saved=lambda: saved.append(1))
    dlg._schedule.setCurrentIndex(dlg._schedule.findData("custom"))
    dlg._times.setText(" 09:00, 18:30 , 坏值 ")
    dlg._volume.setValue(70)
    dlg._show_bubble.setChecked(False)
    dlg._save()
    assert cfg.get("voice_chime_schedule") == "custom"
    assert cfg.get("voice_chime_custom_times") == "09:00,18:30"  # 脏值被清洗
    assert cfg.get("voice_chime_volume") == 70
    assert cfg.get("voice_chime_show_bubble") is False
    assert saved == [1]


def test_custom_requires_at_least_one_time(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.config import Config
    from pet.voice.chime_settings_dialog import ChimeSettingsDialog

    cfg = Config(str(tmp_path))
    dlg = ChimeSettingsDialog(cfg)
    dlg._schedule.setCurrentIndex(dlg._schedule.findData("custom"))
    dlg._times.setText("")
    dlg._save()
    assert "至少" in dlg._hint.text()
    assert cfg.get("voice_chime_schedule") != "custom"  # 没写回
