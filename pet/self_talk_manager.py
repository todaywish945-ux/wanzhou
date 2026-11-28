# -*- coding: utf-8 -*-
"""台词管理对话框——固定台词的勾选播报面板。

台词池是**固定的**（``self_talk_library``：台词音频全部由作者预先训练/录制，
项目暂无实时合成能力，改文字必然配上不对的声音）。本对话框不再提供文本编辑：
每句固定台词一个勾选项，取消勾选的句子不再播报（``self_talk_disabled.json``），
默认全部勾选。顶部角色下拉切换角色，各自独立勾选；「把当前勾选应用到全部角色」
把这只的勾选状态复制给其余角色。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from .config import DEFAULT_SELF_TALK_TEXTS_BY_ROLE
from .pet_visibility import PET_IDS
from . import self_talk_library as lib

logger = logging.getLogger("dsh-pet-standalone")


class SelfTalkManagerDialog(QDialog):
    def __init__(self, config, parent=None, on_saved=None):
        super().__init__(parent)
        self.config = config
        # 勾选变化后的回调（可选）：设置页用它接「重新预缓存台词语音」。
        # 台词池固定、音频预录，勾选只影响"名单里有没有这句"，已有缓存无害；
        # 回调保留给未来的合成能力接线，对话框关闭时触发一次。
        self._on_saved = on_saved
        self.setObjectName("self-talk-manager-dialog")
        self.setWindowTitle("管理所有角色的台词")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        hint = QLabel(
            "台词由作者配音，暂不支持修改文字。每句台词可勾选是否播报："
            "取消勾选后这句话不再说出口，默认全部播报。切换角色可分别设置，"
            "不会被「应用到其他桌宠」覆盖。",
            self,
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        # 角色下拉（与记忆管理同款：显示名来自 config，id 作 userData）
        top = QHBoxLayout()
        top.addWidget(QLabel("编辑谁的台词：", self))
        self.role_combo = QComboBox(self)
        self.role_combo.setObjectName("self-talk-role-combo")
        for cid in PET_IDS:
            try:
                name = config.character_display_name(cid)
            except Exception:
                name = cid
            self.role_combo.addItem(name, cid)
        # 默认选中打开设置页的这只宠的角色
        try:
            current = str(config.get("character") or "")
        except Exception:
            current = ""
        idx = self.role_combo.findData(current)
        if idx >= 0:
            self.role_combo.setCurrentIndex(idx)
        self.role_combo.currentIndexChanged.connect(self._on_role_changed)
        top.addWidget(self.role_combo)
        top.addStretch(1)
        root.addLayout(top)

        self.line_list = QListWidget(self)
        self.line_list.setObjectName("self-talk-line-list")
        self.line_list.setWordWrap(True)
        self.line_list.setMinimumHeight(220)
        root.addWidget(self.line_list)

        footer = QHBoxLayout()
        self.reset_btn = QPushButton("恢复全部播报", self)
        self.reset_btn.setProperty("variant", "ghost")
        self.reset_btn.clicked.connect(self._reset_all_checked)
        footer.addWidget(self.reset_btn)
        footer.addStretch(1)
        done_btn = QPushButton("完成", self)
        done_btn.setObjectName("self-talk-done-btn")
        done_btn.clicked.connect(self.accept)
        footer.addWidget(done_btn)
        root.addLayout(footer)

        self.line_list.itemChanged.connect(self._on_item_changed)
        self._load_current()

    # ------------------------------------------------------------------ 内部
    def _current_role(self) -> str:
        return str(self.role_combo.currentData() or "")

    def _disabled_texts(self) -> list[str]:
        """当前列表里未勾选的台词 = 取消播报集合。"""
        return [item.text() for item in _iter_items(self.line_list)
                if item.checkState() != Qt.Checked]

    def _load_current(self) -> None:
        """按固定台词池 + 已存勾选状态重建列表；程序性勾选不触发保存。"""
        role = self._current_role()
        if not role:
            return
        fixed = list(DEFAULT_SELF_TALK_TEXTS_BY_ROLE.get(role, []))
        disabled = set(lib.disabled_texts_for(getattr(self.config, "dir", ""), role))
        self.line_list.blockSignals(True)
        self.line_list.clear()
        for text in fixed:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if text in disabled else Qt.Checked)
            self.line_list.addItem(item)
        self.line_list.blockSignals(False)
        self.setWindowTitle(f"管理台词 - {self.role_combo.currentText()}")

    def _on_item_changed(self, item) -> None:
        """勾选即存：重算未勾选集合落盘。程序性变更由 blockSignals 挡住。"""
        role = self._current_role()
        if not role:
            return
        try:
            lib.set_disabled_texts(getattr(self.config, "dir", ""), role,
                                   self._disabled_texts())
        except Exception:
            logger.warning("台词勾选保存失败", exc_info=True)

    def _on_role_changed(self, index: int) -> None:
        # 勾选即时落盘，切角色不需要先保存
        self._load_current()

    def _reset_all_checked(self) -> None:
        """清空本角色的取消勾选记录 = 全部恢复播报。

        三角固定池文本互不相同，没有"把勾选复制给其他角色"的合理语义；
        这里只重置当前角色，其他角色不动。
        """
        role = self._current_role()
        if not role:
            return
        try:
            lib.set_disabled_texts(getattr(self.config, "dir", ""), role, [])
        except Exception:
            logger.warning("台词勾选重置失败", exc_info=True)
            return
        self._load_current()

    def _notify_saved(self) -> None:
        callback = self._on_saved
        if not callable(callback):
            return
        try:
            callback()
        except Exception:
            logger.warning("台词勾选后的预缓存回调失败（不影响台词本身）", exc_info=True)

    def accept(self) -> None:
        self._notify_saved()
        super().accept()

    def reject(self) -> None:
        # 关闭（含 Esc）同样通知：勾选是即时落盘的，关闭只是触发一次回调
        self._notify_saved()
        super().reject()


def _iter_items(list_widget):
    return (list_widget.item(i) for i in range(list_widget.count()))
