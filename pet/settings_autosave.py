# -*- coding: utf-8 -*-
"""设置窗「边改边存」：控件改动后防抖调用宿主已有的 ``_write_config()``。

设计边界（改动前先读这段，别在这里加第二条写盘路径）：

* **只复用宿主的整表写回**：自动保存不自己 ``config.set`` / ``config.save``，
  也不碰 ``settings_close_flow`` 的失败闸门；写盘、失败分类、代次防覆盖、
  每宠/全局分流，全部沿用 ``ModernSettingsDialog._write_config()``。
* **不弹框**：自动保存失败只在侧栏状态标签与 tooltip 里如实呈现；
  关窗时仍由原有闸门重试并按既有逻辑询问「继续编辑 / 放弃改动」。
* **不提前做开机自启**：``_apply_autostart()`` 仍只在关闭闸门里调用。
* **关窗前取消待触发的定时器**：``_save_before_close()`` 会调 :meth:`stop`，
  关闭路径的整表写回是那一次改动的唯一落盘点，不会写两遍。
* **逐字输入要防抖**：``QLineEdit`` / ``QPlainTextEdit`` 每敲一个字都发信号，
  定时器重置；停顿 ``AUTOSAVE_DELAY_MS`` 之后才落盘，避免目录锁与配置 watcher 风暴。

接线范围：构造末尾（全部行就位后）扫一遍对话框里的设置控件，按控件类型接
「值确实变了」的信号。复合控件（音效包、快捷启动、菜单编排）另接自定义
``changed`` 信号。``SettingsTabContainer`` 的切页信号不是偏好改动，不接。
"""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
)

from . import settings_close_flow
from .settings_menu_layout_editor import MenuLayoutEditor
from .settings_widgets import (
    ClickSoundPackPicker,
    ModernSelect,
    QuickLaunchEditor,
)

#: 停止操作后多久落盘。600ms 足够吃掉连续敲键/拨动开关，又不至于让用户觉得"没存"。
AUTOSAVE_DELAY_MS = 700

_IDLE_TEXT = "改动会自动保存"
_PENDING_TEXT = "准备保存…"
_FAILED_TEXT = "自动保存失败，关窗时会重试"

#: 侧栏只有一行位置，失败原因按类别给一句人话；完整对象仍放进 tooltip。
_FAILURE_TEXT = {
    settings_close_flow.SAVE_FAILURE_DISK: "自动保存失败：磁盘写入冲突",
    settings_close_flow.SAVE_FAILURE_STALE: "自动保存失败：设置已在别处更新",
    settings_close_flow.SAVE_FAILURE_PROFILE: "自动保存失败：宠物档案不可信",
    settings_close_flow.SAVE_FAILURE_LAYOUT: "自动保存失败：菜单布局无效",
    settings_close_flow.SAVE_FAILURE_AUTOSTART: "自动保存失败：开机自启写入失败",
    settings_close_flow.SAVE_FAILURE_UNKNOWN: "自动保存失败：未知错误",
}

#: 写盘冲突多数是别的进程正持有目录锁（三只宠 + 设置进程同时写），
#: 这类失败值得等一拍自动重试；代次/档案/布局失败必须交给人处理，不重试。
_RETRY_DELAY_MS = 1500
_RETRY_LIMIT = 2


class AutoSaveController(QObject):
    """挂在设置对话框上的防抖控制器；``stop()`` 供关闭闸门收口。"""

    def __init__(self, dialog, *, delay_ms: int = AUTOSAVE_DELAY_MS):
        super().__init__(dialog)
        self.dialog = dialog
        self._delay_ms = max(0, int(delay_ms))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self._delay_ms)
        self._timer.timeout.connect(self.flush)
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.setInterval(_RETRY_DELAY_MS)
        self._retry_timer.timeout.connect(self._retry_flush)
        self._retry_left = _RETRY_LIMIT
        self._connected: set = set()
        self._menu_layout_baseline: dict[int, dict] = {}
        self._dirty = False
        self._flushing = False
        self._status_label = self._install_status_label()
        self._connect_controls()

    # ------------------------------------------------------------------ 接线
    def _connect_once(self, widget, signal) -> None:
        """同一控件的同一信号只接一次；Qt 会在控件销毁时自动断开。"""
        key = (id(widget), str(signal))
        if key in self._connected:
            return
        self._connected.add(key)
        signal.connect(self.schedule)

    def _connect_controls(self) -> None:
        dialog = self.dialog
        for widget in dialog.findChildren(QAbstractButton):
            # ToggleSwitch / QCheckBox / QRadioButton 都在这里；普通 QPushButton
            # 不可 checkable，toggled 永远不会发，接了也是零成本。
            self._connect_once(widget, widget.toggled)
        for widget in dialog.findChildren(ModernSelect):
            self._connect_once(widget, widget.currentIndexChanged)
        for widget in dialog.findChildren(QComboBox):
            self._connect_once(widget, widget.currentIndexChanged)
        for widget in dialog.findChildren(QSpinBox):
            self._connect_once(widget, widget.valueChanged)
        for widget in dialog.findChildren(QDoubleSpinBox):
            self._connect_once(widget, widget.valueChanged)
        for widget in dialog.findChildren(QLineEdit):
            self._connect_once(widget, widget.textChanged)
        for widget in dialog.findChildren(QPlainTextEdit):
            self._connect_once(widget, widget.textChanged)
        for widget in dialog.findChildren(QTextEdit):
            self._connect_once(widget, widget.textChanged)
        for widget in dialog.findChildren(QKeySequenceEdit):
            self._connect_once(widget, widget.keySequenceChanged)
        # 复合控件：列表拖拽 / 取色 / 文件选择等不一定经过上面任一信号。
        for cls, signal_name in (
            (ClickSoundPackPicker, "changed"),
            (QuickLaunchEditor, "changed"),
        ):
            for widget in dialog.findChildren(cls):
                self._connect_once(widget, getattr(widget, signal_name))
        # 菜单编排的 changed 也会被 set_enabled_actions() 这类"布局没变"的刷新触发
        # （_on_changed 无条件 emit）。只在 value() 真的变了时才算用户改动，否则
        # 一开设置窗就会白白写一次盘。
        for widget in dialog.findChildren(MenuLayoutEditor):
            key = (id(widget), "menu-layout-value")
            if key in self._connected:
                continue
            self._connected.add(key)
            self._menu_layout_baseline[id(widget)] = widget.value()
            widget.changed.connect(
                lambda *_args, editor=widget: self._on_menu_layout_changed(editor))

    def _on_menu_layout_changed(self, editor) -> None:
        try:
            current = editor.value()
        except RuntimeError:  # 旧页 deleteLater 后 Qt 对象已死
            return
        if current == self._menu_layout_baseline.get(id(editor)):
            return
        self._menu_layout_baseline[id(editor)] = current
        self.schedule()

    # ------------------------------------------------------------------ 状态
    def _install_status_label(self):
        """在侧栏版本号上方塞一行短状态；横向撑满列，不参与侧栏宽度计算。"""
        dialog = self.dialog
        pane = dialog.findChild(QFrame, "sidebarPane") or dialog
        label = QLabel(pane)
        label.setObjectName("settingsAutosaveStatus")
        label.setText(_IDLE_TEXT)
        label.setWordWrap(True)
        # Expanding：settings_widgets.sidebar_content_width 会跳过撑满列的控件，
        # 否则这行字会把 200px 侧栏顶宽，破坏字体缩放的像素契约。
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label.setToolTip("改动会在停止操作后自动写入配置；关窗也会保存。")
        layout = pane.layout()
        footer = getattr(dialog, "version_footer", None)
        index = layout.indexOf(footer) if layout is not None and footer is not None else -1
        if layout is not None and index >= 0:
            layout.insertWidget(index, label)
        elif layout is not None:
            layout.addWidget(label)
        return label

    def _set_status(self, text: str, detail: str | None = None) -> None:
        label = self._status_label
        if label is None:
            return
        label.setText(text)
        label.setToolTip(detail or "改动会在停止操作后自动写入配置；关窗也会保存。")

    # ------------------------------------------------------------------ 触发
    def schedule(self, *_args) -> None:
        """任一设置控件的值变了：重置防抖定时器（保存过程中的程序性改动不算）。"""
        if self._flushing or getattr(self.dialog, "_close_decided", False):
            return
        self._dirty = True
        self._timer.start(self._delay_ms)
        self._set_status(_PENDING_TEXT)

    def _retry_flush(self) -> None:
        """写盘冲突的后备重试：只重试同一批草稿，不重启防抖窗口。"""
        if getattr(self.dialog, "_close_decided", False):
            return
        self._dirty = True
        self.flush()

    def flush(self) -> None:
        """把控件草稿交给宿主整表落盘；失败不弹框，只留状态与失败类别。"""
        if self._flushing or not self._dirty:
            return
        self._flushing = True
        ok = False
        try:
            ok = bool(self.dialog._write_config())
        except Exception:
            logging.exception("设置自动保存失败")
        finally:
            self._flushing = False
            self._dirty = False
        if ok:
            self._retry_left = _RETRY_LIMIT
            self._set_status(f"已自动保存 {datetime.now():%H:%M}")
            return
        failure = getattr(self.dialog, "_write_failure", None)
        detail = f"自动保存失败：{failure}" if failure else "自动保存失败，关窗时会重试"
        kind = getattr(failure, "kind", "")
        text = _FAILURE_TEXT.get(kind, _FAILED_TEXT)
        if kind == settings_close_flow.SAVE_FAILURE_DISK and self._retry_left > 0:
            # 目录锁被另一个进程短暂占用是最常见的 disk 失败；等一拍再试，
            # 不弹框打断输入。代次/档案失败不重试——那需要用户重新打开设置。
            self._retry_left -= 1
            self._retry_timer.start(_RETRY_DELAY_MS)
            text = "自动保存失败：磁盘冲突，正在重试…"
        self._set_status(text, detail)

    def stop(self) -> None:
        """关闭闸门调用：丢弃待触发的定时器，草稿仍由关窗的整表写回落盘。"""
        self._timer.stop()
        self._retry_timer.stop()
        self._dirty = False


def install(dialog, *, delay_ms: int = AUTOSAVE_DELAY_MS) -> AutoSaveController:
    """给设置对话框装上自动保存，返回控制器（供测试/关闭闸门收口）。"""
    controller = AutoSaveController(dialog, delay_ms=delay_ms)
    dialog._settings_autosave = controller
    return controller
