# -*- coding: utf-8 -*-
"""Custom first row for the playful modern-menu image action."""
from __future__ import annotations

import logging

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFontMetrics, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QMessageBox, QWidget, QWidgetAction

from ..fun_image_popup import open_wanzhou_window
from .shared import defer_menu_callback


class ClickAccessory(QWidget):
    def __init__(
        self, parent: QWidget, text: str = "请点击", color: str = "#777777",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("wanzhouClickAccessory")
        self._text = str(text or "请点击")[:20]
        self._color = QColor(color)
        self.setProperty("text", self._text)
        self.setFixedSize(54, 20)
        font = parent.font()
        pixel_size = font.pixelSize() if font.pixelSize() > 0 else 13
        font.setPixelSize(max(9, pixel_size - 2))
        self.setFont(font)

    def displayText(self) -> str:  # noqa: N802 - Qt-style diagnostic API
        return QFontMetrics(self.font()).elidedText(
            self._text, Qt.TextElideMode.ElideRight, 39,
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(
            QPen(
                self._color,
                1.25,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        pointer = QPainterPath()
        pointer.moveTo(2.5, 3.0)
        pointer.lineTo(10.5, 10.0)
        pointer.lineTo(7.0, 10.7)
        pointer.lineTo(9.2, 15.2)
        pointer.lineTo(6.8, 16.4)
        pointer.lineTo(4.7, 11.9)
        pointer.lineTo(2.5, 14.5)
        pointer.closeSubpath()
        painter.drawPath(pointer)
        painter.setFont(self.font())
        painter.drawText(QRectF(15, 0, 39, 20), Qt.AlignmentFlag.AlignVCenter, self.displayText())


class ElidedLabel(QLabel):
    def __init__(self, text: str, parent=None) -> None:
        self._full_text = str(text)
        super().__init__("", parent)

    def displayText(self) -> str:  # noqa: N802 - Qt-style diagnostic API
        return self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, max(1, self.width()),
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.setText(self.displayText())
        super().resizeEvent(event)

    def setFont(self, font) -> None:  # noqa: N802
        super().setFont(font)
        self.setText(self.displayText())


class WanzhouMenuEntry(QWidget):
    clicked = Signal()

    def __init__(self, menu: QMenu, config: dict | None = None) -> None:
        super().__init__(menu)
        self._config = dict(config or {})
        self._menu = menu
        self._hovered = False
        self.setObjectName("wanzhouMenuEntry")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setMinimumWidth(224)
        self.setFixedHeight(39)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        avatar = QLabel(self)
        avatar.setObjectName("wanzhouAvatar")
        avatar.setFixedSize(27, 27)
        avatar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # 彩蛋入口不再展示圆形头像：保留控件本身（供 hover 透传测试与兼容），
        # 但隐藏后 QHBoxLayout 不再为其分配空间，标题自然左移。
        avatar.hide()
        layout.addWidget(avatar)
        self.title_label = ElidedLabel(str(self._config.get("title") or "彩蛋"), self)
        self.title_label.setObjectName("wanzhouTitle")
        self.title_label.setFixedWidth(105)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.title_label.setFont(menu.font())
        appearance = menu.property("modernAppearance") or {}
        dark = bool(menu.property("modernDark"))
        foreground = str(
            appearance.get("dark_foreground" if dark else "light_foreground")
            or ("#f2e4cf" if dark else "#3a2f24")
        )
        self._hover_color = QColor(
            str(
                appearance.get("dark_hover" if dark else "light_hover")
                or ("#443338" if dark else "#f3e2c1")
            )
        )
        self.title_label.setStyleSheet(f"color: {foreground};")
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        self.click_accessory = ClickAccessory(
            self, str(self._config.get("hint") or "请点击"), foreground,
        )
        self.click_accessory.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.click_accessory)
        self.clicked.connect(self._activate)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(224, 39)

    def set_title(self, title: str) -> None:
        """Apply a Menu Layout Tree alias to the custom header widget."""
        self.title_label._full_text = str(title)
        self.title_label.setText(self.title_label.displayText())

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        # 菜单弹出时鼠标可能已在项上方（如顶行彩蛋项），此时没有 enter 事件，
        # 按光标位置合成初始 hover 状态。布局尚未激活导致 rect 为空时用
        # sizeHint 兜底，避免合成高亮静默丢失。
        rect = self.rect()
        if rect.isEmpty():
            rect = QRect(0, 0, self.sizeHint().width(), self.sizeHint().height())
        self._hovered = rect.contains(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        # Windows 上跨子窗口（头像/文字/提示）移动可能丢失 enter/leave，
        # 鼠标移动作为 hover 的兜底恢复
        self._hovered = True
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        # 鼠标移入 avatar/文字/提示等子 widget 时也会触发 leave，
        # 光标整体仍在项内则保持高亮
        self._hovered = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        if not self._hovered:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._hover_color)
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 9, 9)

    def _activate(self) -> None:
        config = dict(self._config)

        def open_window() -> None:
            try:
                open_wanzhou_window(config)
            except Exception as exc:
                logging.exception("打开彩蛋图片窗口失败")
                QMessageBox.warning(None, "彩蛋图片不可用", str(exc))

        # macOS 的原生 NSMenu 跟踪循环退出前不能可靠创建顶层窗口。
        # 与聊天、设置、退出动作一样，等 QMenu.exec() 返回后再执行。
        defer_menu_callback(self._menu, open_window)


def add_wanzhou_entry(menu: QMenu, config: dict | None = None) -> QWidgetAction:
    config = dict(config or {})
    action = QWidgetAction(menu)
    action.setText(str(config.get("title") or "彩蛋"))
    action.setDefaultWidget(WanzhouMenuEntry(menu, config))
    menu.addAction(action)
    return action
