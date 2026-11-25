# -*- coding: utf-8 -*-
"""右键「作者信息」弹窗：作者抖音账号 + 一张作者照片。

只读展示，不写 Config、不联网。内容照搬作者的另一款桌宠（小蕾米AI助理）的
「作者信息」，照片随本项目一起打包：``assets/author_info/author.jpg``。

弹窗拆成 ``build_author_dialog``（可测 seam）与 ``show_author_info``（弹起），
后者只负责窗口生命周期，便于 offscreen 测试不真的走 exec()。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget,
)

AUTHOR_TEXT = "抖音：每天都要保持嘴角上扬啊\n抖音号：4614574078d"
AUTHOR_HANDLE = "4614574078d"
AUTHOR_PHOTO = "assets/author_info/author.jpg"
_PHOTO_SIZE = 200


def author_photo_path() -> Path:
    """作者照片路径：源码树与 PyInstaller _internal 下都在 assets/ 里。"""
    from .fun_image_popup import bundled_assets_root

    return bundled_assets_root() / "author_info" / "author.jpg"


def build_author_dialog(parent: QWidget | None = None) -> QDialog:
    """构造作者信息弹窗（不 exec）。文案与照片都从本模块常量取。"""
    dialog = QDialog(parent)
    dialog.setWindowTitle("作者信息")
    dialog.setObjectName("authorInfoDialog")
    dialog.setMinimumWidth(320)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 18, 20, 16)
    layout.setSpacing(12)

    photo_label = QLabel(dialog)
    photo_label.setObjectName("authorPhoto")
    photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pixmap = QPixmap(str(author_photo_path()))
    if not pixmap.isNull():
        photo_label.setPixmap(
            pixmap.scaled(
                _PHOTO_SIZE, _PHOTO_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    else:
        photo_label.setText("（作者照片不可用）")
        photo_label.setProperty("authorPhotoMissing", True)
    layout.addWidget(photo_label)

    text_label = QLabel(AUTHOR_TEXT, dialog)
    text_label.setObjectName("authorText")
    text_label.setWordWrap(True)
    text_label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    text_label.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    layout.addWidget(text_label)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
    buttons.setObjectName("authorInfoButtons")
    buttons.rejected.connect(dialog.reject)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)
    return dialog


def show_author_info(parent: QWidget | None = None) -> QDialog:
    """弹起作者信息；返回同一个 dialog 实例，方便调用方按需检查。"""
    dialog = build_author_dialog(parent)
    dialog.exec()
    return dialog
