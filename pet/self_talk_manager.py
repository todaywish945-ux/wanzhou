# -*- coding: utf-8 -*-
"""台词管理对话框——一个入口查看/修改所有角色的自言自语台词。

与 AI 记忆管理同款：对话框顶部一个角色下拉，切换即加载该角色的台词；保存到
全局台词库（``pet.self_talk_library``），因此打开任何一只桌宠的设置都能管理全部
角色，且不受「应用到其他桌宠」影响。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .pet_visibility import PET_IDS
from . import self_talk_library as lib


class SelfTalkManagerDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setObjectName("self-talk-manager-dialog")
        self.setWindowTitle("管理所有角色的台词")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        hint = QLabel(
            "在这里管理三只桌宠各自的自言自语台词。打开任何一只的设置都能查看和修改"
            "全部角色；台词独立保存，不会被「应用到其他桌宠」覆盖。切换角色后编辑、"
            "点「保存」即生效（无需重启）。每行一条，留空恢复内置台词。",
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

        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("self-talk-editor")
        self.editor.setMinimumHeight(200)
        root.addWidget(self.editor)

        footer = QHBoxLayout()
        self.copy_all_btn = QPushButton("把当前角色的台词应用到全部角色", self)
        self.copy_all_btn.setProperty("variant", "ghost")
        self.copy_all_btn.clicked.connect(self._copy_to_all)
        footer.addWidget(self.copy_all_btn)
        footer.addStretch(1)
        cancel_btn = QPushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)
        save_btn = QPushButton("保存", self)
        save_btn.setObjectName("self-talk-save-btn")
        save_btn.clicked.connect(self._save)
        footer.addWidget(save_btn)
        root.addLayout(footer)

        self._load_current()
        self._dirty = False
        self.editor.textChanged.connect(self._mark_dirty)

    # ------------------------------------------------------------------ 内部
    def _current_role(self) -> str:
        return str(self.role_combo.currentData() or "")

    def _editor_texts(self) -> list[str]:
        return [line.strip() for line in self.editor.toPlainText().splitlines() if line.strip()]

    def _load_current(self) -> None:
        role = self._current_role()
        if not role:
            return
        texts = lib.texts_for(getattr(self.config, "dir", ""), role)
        self.editor.blockSignals(True)
        self.editor.setPlainText("\n".join(texts))
        self.editor.blockSignals(False)
        self.setWindowTitle(f"管理台词 - {self.role_combo.currentText()}")
        self._dirty = False

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _on_role_changed(self, index: int) -> None:
        if self._dirty:
            # 切角色前自动保存当前编辑，避免丢失输入
            self._save_current()
        self._load_current()

    def _save_current(self) -> None:
        role = self._current_role()
        if not role:
            return
        try:
            lib.update_texts(getattr(self.config, "dir", ""), role, self._editor_texts())
        except Exception:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "保存失败", "台词未能保存，请检查配置目录权限后重试。")
            return
        self._dirty = False

    def _save(self) -> None:
        self._save_current()
        self.accept()

    def _copy_to_all(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        texts = self._editor_texts()
        if not texts:
            QMessageBox.information(self, "无内容", "当前编辑框为空，没有可复制的台词。")
            return
        answer = QMessageBox.question(
            self, "确认",
            f"把当前角色的 {len(texts)} 条台词复制到全部 {len(PET_IDS)} 只桌宠？"
            "各角色原本的台词会被覆盖。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            for cid in PET_IDS:
                lib.update_texts(getattr(self.config, "dir", ""), cid, texts)
        except Exception:
            QMessageBox.warning(self, "保存失败", "台词未能保存，请检查配置目录权限后重试。")
            return
        self._dirty = False
        QMessageBox.information(self, "完成", "台词已应用到全部角色。")
