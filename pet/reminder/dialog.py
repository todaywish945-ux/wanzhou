# -*- coding: utf-8 -*-
"""提醒事项管理窗口：闹钟 / 倒计时 / 单次指定时刻的增删改查。

视觉沿用本项目小窗语言（12px 圆角、13px 正文、跟随系统明暗），不发明新样式。
数据全部走 ReminderService，本窗口只做输入与展示。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QTimeEdit,
    QVBoxLayout, QWidget,
)

from .core import (
    Reminder, TYPE_CLOCK, TYPE_COUNTDOWN, TYPE_ONCE,
    make_clock, make_countdown, make_once, next_fire_text,
)

log = logging.getLogger(__name__)


class ReminderDialog(QDialog):
    """非模态提醒管理窗；进程级单例，由 AppShell 持有。"""

    def __init__(self, service, shell=None, parent=None):
        super().__init__(parent)
        self._service = service
        self._shell = shell
        self.setWindowTitle("⏰ 提醒事项")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(460, 560)
        self._rows: dict[int, tuple[QFrame, QLabel]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        hint = QLabel("到点由桌宠冒气泡并语音提醒；关掉窗口提醒仍在，到点照常响。")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addWidget(self._build_input())

        list_label = QLabel("进行中的提醒")
        list_label.setProperty("role", "label")
        root.addWidget(list_label)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        scroll.setWidget(self._list_host)
        root.addWidget(scroll, 1)

        self.refresh()
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh_countdowns)
        self._tick.start(1000)

    def _card(self) -> QWidget:
        card = QWidget()
        card.setProperty("card", True)
        return card

    def _build_input(self) -> QWidget:
        card = self._card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # 类型切换
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("类型："))
        self._type_combo = QComboBox()
        self._type_combo.addItem("闹钟（每天重复）", TYPE_CLOCK)
        self._type_combo.addItem("倒计时（N 分钟后）", TYPE_COUNTDOWN)
        self._type_combo.addItem("单次（指定日期时间）", TYPE_ONCE)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_row.addWidget(self._type_combo, 1)
        lay.addLayout(type_row)

        # 时间输入（三种各自一个控件，按类型显示/隐藏）
        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setTime(self._time_edit.time().currentTime())
        self._minutes_spin = QSpinBox()
        self._minutes_spin.setRange(1, 1440)
        self._minutes_spin.setValue(10)
        self._minutes_spin.setSuffix(" 分钟后")
        self._once_edit = QDateTimeEdit()
        self._once_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._once_edit.setCalendarPopup(True)
        self._once_edit.setDateTime(self._once_edit.dateTime().currentDateTime())

        self._when_row = QHBoxLayout()
        self._when_row.addWidget(QLabel("时间："))
        for widget in (self._time_edit, self._minutes_spin, self._once_edit):
            self._when_row.addWidget(widget)
        lay.addLayout(self._when_row)

        # 内容 + 重复开关
        name_row = QHBoxLayout()
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("提醒内容（可选，如：吃药 / 开会）")
        name_row.addWidget(self._title_edit, 1)
        self._repeat_check = QCheckBox("每天重复")
        self._repeat_check.setChecked(True)
        name_row.addWidget(self._repeat_check)
        lay.addLayout(name_row)

        add_row = QHBoxLayout()
        add_row.addStretch(1)
        self._add_btn = QPushButton("＋ 添加提醒")
        self._add_btn.setObjectName("accentButton")
        self._add_btn.clicked.connect(self._add)
        add_row.addWidget(self._add_btn)
        lay.addLayout(add_row)

        self._on_type_changed()
        return card

    def _current_type(self) -> str:
        return str(self._type_combo.currentData() or TYPE_CLOCK)

    def _on_type_changed(self):
        kind = self._current_type()
        self._time_edit.setVisible(kind == TYPE_CLOCK)
        self._minutes_spin.setVisible(kind == TYPE_COUNTDOWN)
        self._once_edit.setVisible(kind == TYPE_ONCE)
        self._repeat_check.setVisible(kind == TYPE_CLOCK)
        # 找到"时间："标签一并隐藏（倒计时用分钟数，不需要"时间"字样）
        for i in range(self._when_row.count()):
            w = self._when_row.itemAt(i).widget()
            if isinstance(w, QLabel):
                w.setText("时间：" if kind != TYPE_COUNTDOWN else "延时：")

    def _add(self):
        title = self._title_edit.text().strip()
        kind = self._current_type()
        try:
            if kind == TYPE_CLOCK:
                t = self._time_edit.time()
                r = make_clock(t.hour(), t.minute(), title,
                               repeat=self._repeat_check.isChecked())
            elif kind == TYPE_COUNTDOWN:
                r = make_countdown(self._minutes_spin.value(), title)
            else:
                at = self._once_edit.dateTime().toString("yyyy-MM-dd HH:mm")
                r = make_once(at, title)
        except ValueError as exc:
            self._title_edit.setPlaceholderText(f"时间不合法：{exc}")
            return
        self._service.add(r)
        self._title_edit.clear()
        self.refresh()

    def refresh(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._rows.clear()

        active = [r for r in self._service.reminders if r.is_active()]
        if not active:
            empty = QLabel("还没有提醒，上面添加一个吧～")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_layout.addWidget(empty)
        for r in active:
            self._list_layout.addWidget(self._make_row(r))
        self._list_layout.addStretch(1)

    def _make_row(self, r: Reminder) -> QWidget:
        row = QFrame()
        row.setProperty("card", True)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 8, 10, 8)
        row_layout.setSpacing(8)

        label = QLabel(f"{next_fire_text(r)}　{r.title}")
        label.setWordWrap(True)
        row_layout.addWidget(label, 1)
        self._rows[r.id] = (row, label)

        toggle = QPushButton("停用" if r.enabled else "启用")
        toggle.clicked.connect(lambda _=False, rid=r.id, on=not r.enabled:
                               (self._service.toggle(rid, on), self.refresh()))
        row_layout.addWidget(toggle)

        delete = QPushButton("删除")
        delete.clicked.connect(lambda _=False, rid=r.id:
                               (self._service.remove(rid), self.refresh()))
        row_layout.addWidget(delete)
        return row

    def _refresh_countdowns(self):
        for r in self._service.reminders:
            if r.type == TYPE_COUNTDOWN and r.id in self._rows:
                _, label = self._rows[r.id]
                label.setText(f"{next_fire_text(r)}　{r.title}")

    def closeEvent(self, event):
        if self._shell is not None and getattr(self._shell, "reminder_dialog", None) is self:
            self._shell.reminder_dialog = None
        super().closeEvent(event)
