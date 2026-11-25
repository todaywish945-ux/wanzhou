# -*- coding: utf-8 -*-
"""轻量「报时设置」对话框：从右键菜单进入，只管报时时间和基础播放项。

背景：原报时设置页 ``pet/voice/chime_settings.py`` 未随移植携带，导致底层
（``voice_chime_*`` 配置键 + chime_service 调度）完整可用，但用户没有任何
界面能设置"几点报时"。本对话框补上这个缺口，不重建整页，只收敛最常用的
报时节奏 / 自定义时间点 / 音量 / 气泡开关；音色等高级项仍可手改配置。

保存走 Config.set + save，再经 AppShell._sync_chime_service 让运行中的服务
立即重读配置（不重启）。
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from ..voice_chime import SCHEDULE_KEYS, SCHEDULE_LABELS, clean_custom_times

log = logging.getLogger(__name__)


class ChimeSettingsDialog(QDialog):
    """非模态报时设置窗；读写入口都是传入的 Config。"""

    def __init__(self, config, on_saved=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._on_saved = on_saved
        self.setWindowTitle("⏰ 报时设置")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(380, 300)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        info = QLabel("选择报时节奏；选「自定义时间点」可填多个时刻，到点自动报时。")
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)

        # 报时节奏
        self._schedule = QComboBox()
        for key in SCHEDULE_KEYS:
            self._schedule.addItem(SCHEDULE_LABELS.get(key, key), key)
        form.addRow("报时节奏", self._schedule)

        # 自定义时间点（仅 custom 模式生效）
        self._times = QLineEdit()
        self._times.setPlaceholderText("例如：09:00,12:30,18:00（逗号分隔）")
        form.addRow("时间点", self._times)

        # 音量
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setSingleStep(5)
        form.addRow("音量", self._volume)

        # 气泡开关
        self._show_bubble = QCheckBox("报时冒气泡")
        form.addRow("", self._show_bubble)

        root.addLayout(form)

        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.close)
        save = QPushButton("保存")
        save.setObjectName("accentButton")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self._load()

    def _load(self) -> None:
        cfg = self._config
        schedule = str(cfg.get("voice_chime_schedule", "hourly"))
        index = self._schedule.findData(schedule)
        self._schedule.setCurrentIndex(index if index >= 0 else 0)
        self._times.setText(str(cfg.get("voice_chime_custom_times", "")))
        try:
            volume = int(cfg.get("voice_chime_volume", 80))
        except (TypeError, ValueError):
            volume = 80
        self._volume.setValue(max(0, min(100, volume)))
        self._show_bubble.setChecked(bool(cfg.get("voice_chime_show_bubble", True)))
        self._on_schedule_changed()
        self._schedule.currentIndexChanged.connect(self._on_schedule_changed)
        self._times.textChanged.connect(self._on_times_changed)

    def _on_schedule_changed(self):
        is_custom = self._schedule.currentData() == "custom"
        self._times.setEnabled(is_custom)
        self._hint.setText(
            "自定义模式：填写的时间点必须显式开启报时才会响（右键「启用语音报时」）。"
            if is_custom else
            "选「自定义时间点」后可指定具体时刻；当前节奏无需填时间点。"
        )

    def _on_times_changed(self, text: str):
        cleaned = clean_custom_times(text)
        raw = [s for s in str(text).replace("，", ",").replace(";", ",").split(",") if s.strip()]
        if len(cleaned) != len(raw):
            self._hint.setText("有时间点格式不对（应为 HH:MM，24 小时制）；保存时会自动忽略。")
        else:
            self._on_schedule_changed()

    def _save(self) -> None:
        schedule = str(self._schedule.currentData() or "hourly")
        raw_times = str(self._times.text())
        times = clean_custom_times(raw_times)
        if schedule == "custom" and not times:
            self._hint.setText("自定义模式至少要填一个有效时间点（HH:MM）。")
            return
        self._config.set("voice_chime_schedule", schedule)
        self._config.set("voice_chime_custom_times", ",".join(sorted(times)))
        self._config.set("voice_chime_volume", self._volume.value())
        self._config.set("voice_chime_show_bubble", self._show_bubble.isChecked())
        self._config.save()
        if callable(self._on_saved):
            self._on_saved()
        self.close()
