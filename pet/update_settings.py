# -*- coding: utf-8 -*-
"""Modern settings page for online updates."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from . import __version__, updater


class UpdatePage(QWidget):
    """检查、下载并安装更新；不写入 Config，避免把一次性命令变成设置项。"""

    check_finished = Signal(object)
    download_finished = Signal(object)
    download_progress = Signal(int, int)

    def __init__(self, config, *, include_chat: bool = True, parent=None):
        super().__init__(parent)
        self.config = config
        self.include_chat = bool(include_chat)
        self.release: dict | None = None
        self._busy = False
        self._build_ui()
        self.check_finished.connect(self._on_check_finished)
        self.download_finished.connect(self._on_download_finished)
        self.download_progress.connect(self._on_download_progress)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        intro = QLabel(
            f"当前版本 v{__version__}。更新检查优先读取仓库 update.json（CDN 多镜像），"
            "取不到时才回退 GitHub Releases。",
            self,
        )
        intro.setWordWrap(True)
        intro.setObjectName("updateIntro")
        layout.addWidget(intro)

        status_card = QFrame(self)
        status_card.setObjectName("updateStatusCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(8)
        self.version_label = QLabel(f"当前版本  v{__version__}", status_card)
        self.version_label.setObjectName("updateCurrentVersion")
        self.status_label = QLabel("尚未检查更新", status_card)
        self.status_label.setObjectName("updateStatus")
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.version_label)
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_card)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.check_button = QPushButton("检查更新", self)
        self.check_button.setObjectName("checkUpdateButton")
        self.check_button.clicked.connect(self.check_for_updates)
        self.install_button = QPushButton("下载并安装", self)
        self.install_button.setObjectName("installUpdateButton")
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.download_and_install)
        self.manual_button = QPushButton("打开下载页", self)
        self.manual_button.setObjectName("manualUpdateButton")
        self.manual_button.setEnabled(False)
        self.manual_button.clicked.connect(self.open_download_page)
        action_row.addWidget(self.check_button)
        action_row.addWidget(self.install_button)
        action_row.addWidget(self.manual_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.progress = QProgressBar(self)
        self.progress.setObjectName("updateProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.hide()
        layout.addWidget(self.progress)

        notes_card = QFrame(self)
        notes_card.setObjectName("updateNotesCard")
        notes_layout = QVBoxLayout(notes_card)
        notes_layout.setContentsMargins(16, 14, 16, 14)
        notes_layout.setSpacing(6)
        notes_title = QLabel("新版本说明", notes_card)
        notes_title.setObjectName("updateNotesTitle")
        self.notes_label = QLabel("检查到新版本后，这里会显示版本说明。", notes_card)
        self.notes_label.setObjectName("updateNotes")
        self.notes_label.setWordWrap(True)
        self.notes_label.setTextInteractionFlags(
            self.notes_label.textInteractionFlags()
            | Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.notes_label.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        notes_layout.addWidget(notes_title)
        notes_layout.addWidget(self.notes_label)
        layout.addWidget(notes_card)
        layout.addStretch(1)

    def apply_release(self, result) -> None:
        """把外部（右键菜单 / 自动检查）已取到的版本结果灌进面板。

        避免用户点一次「检查更新」就打两次网络：壳层拿到的 result 直接复用；
        传 None 则说明没查到，走失败文案。
        """
        self._on_check_finished(result)

    def check_for_updates(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._set_state("正在检查更新…", checking=True)

        def worker() -> None:
            try:
                result = updater.latest_release()
            except Exception as exc:  # noqa: BLE001
                logging.exception("设置页检查更新失败")
                result = exc
            self.check_finished.emit(result)

        threading.Thread(target=worker, daemon=True, name="pet-settings-update-check").start()

    def _on_check_finished(self, result) -> None:
        self._busy = False
        if isinstance(result, Exception) or result is None:
            self.release = None
            self._set_state("无法连接更新服务，请检查网络后重试。", checking=False)
            self.manual_button.setEnabled(True)
            return
        self.release = result
        tag = str(result.get("version") or "")
        self.manual_button.setEnabled(bool(result.get("html_url")))
        if not updater.is_newer(tag):
            self.install_button.setEnabled(False)
            self._set_state(f"已经是最新版本（v{__version__}）。", checking=False)
            self.notes_label.setText("当前没有可用更新。")
            return
        # 便携包优先：有带 sha256 的 zip 就能一键更新（下载→校验→独立脚本替换
        # 目录→重启三只）；没有再退回 Inno Setup 安装包。两者都不满足才禁用。
        asset = updater.select_portable_archive(result) or updater.select_windows_installer(
            result, include_chat=self.include_chat)
        notes = str(result.get("notes") or "暂无版本说明。")
        # 开源版没有安装包时，下载入口就是网盘直链；提取码必须跟着说明走，
        # 否则用户点了「打开下载页」还得回到别处找码。
        download_url = str(result.get("download_url") or result.get("html_url") or "")
        if download_url:
            download_line = f"下载：{download_url}"
            code = str(result.get("download_code") or "").strip()
            if code:
                download_line += f"  提取码：{code}"
            notes = f"{notes}\n\n{download_line}"
        self.notes_label.setText(notes)
        integrity_ready = bool(asset and asset.get("size") is not None and asset.get("sha256"))
        self.install_button.setEnabled(integrity_ready and updater.can_auto_install())
        portable = bool(asset and str(asset.get('name', '')).lower().endswith('.zip'))
        if asset is None:
            state = f"发现 v{tag}，但没有找到可校验的更新包，请打开下载页手动更新。"
        elif not integrity_ready:
            state = f"发现 v{tag}，但更新包缺少完整性校验信息，请打开下载页手动更新。"
        elif not updater.can_auto_install():
            state = f"发现 v{tag}。当前运行方式不支持自动更新，请打开下载页手动更新。"
        elif portable:
            state = f"发现新版本 v{tag}，点「下载并安装」会校验压缩包、自动替换并重启三只桌宠。"
        else:
            state = f"发现新版本 v{tag}，点「下载并安装」后会校验文件并启动安装程序。"
        self._set_state(state, checking=False)

    def download_and_install(self) -> None:
        if self._busy or self.release is None:
            return
        # 与启用路径同口径：便携 zip（带 size/sha256）优先，其次 Inno Setup。
        # 之前这里只查安装包，便携包发布形态下按钮亮着、点了却报
        # 「没有可用的 Windows 安装包」（v1.03→v1.04 一键更新实测翻车）。
        asset = updater.select_portable_archive(self.release) or updater.select_windows_installer(
            self.release, include_chat=self.include_chat)
        if asset is None:
            self._set_state("没有可用的更新包，请打开下载页。", checking=False)
            return
        self._busy = True
        self.check_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self._set_state("正在下载更新…", checking=False)

        portable = bool(str(asset.get('name', '')).lower().endswith('.zip'))

        def worker() -> None:
            try:
                if portable:
                    # 下载 + 校验 + 解压到暂存目录；不碰正在运行的程序目录。
                    result = updater.stage_portable_update(
                        asset, self.config.dir,
                        progress=lambda current, total: self.download_progress.emit(current, total or 0),
                    )
                else:
                    result = updater.download_asset(
                        asset,
                        updater.update_cache_dir(self.config.dir),
                        progress=lambda current, total: self.download_progress.emit(current, total or 0),
                    )
                self.download_finished.emit(result)
            except Exception as exc:  # noqa: BLE001
                logging.exception("下载更新失败")
                self.download_finished.emit(exc)

        threading.Thread(target=worker, daemon=True, name="pet-settings-update-download").start()

    def _on_download_progress(self, current: int, total: int) -> None:
        if total > 0:
            self.progress.setValue(min(100, int(current * 100 / total)))
            self.progress.setFormat(f"{current / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB")
        else:
            self.progress.setFormat(f"已下载 {current / 1024 / 1024:.1f} MB")

    def _on_download_finished(self, result) -> None:
        self._busy = False
        self.check_button.setEnabled(True)
        if isinstance(result, Exception):
            self.install_button.setEnabled(True)
            self._set_state(f"下载或校验失败：{result}", checking=False)
            return
        try:
            if str(result.name).lower().endswith('.zip') and result.parent.name == 'staging':
                # 便携包：写独立脚本（不在程序目录里），脚本等桌宠退出后替换目录。
                import sys
                app_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else None
                if app_dir is None or not (app_dir / 'wanzhou-pet.exe').is_file():
                    raise RuntimeError('当前不是冻结便携版，无法自动替换程序目录')
                script = updater.write_portable_update_script(
                    result, app_dir, config_dir=self.config.dir)
                updater.start_portable_update(script)
                message = "更新已准备好：桌宠将自动关闭、替换文件并重新启动。"
            else:
                updater.start_installer(result)
                message = "安装器已启动，按提示完成安装即可（桌宠会被自动关闭）。"
        except Exception as exc:  # noqa: BLE001
            self.install_button.setEnabled(True)
            self._set_state(f"无法启动更新：{exc}", checking=False)
            return
        self._set_state(message, checking=False)
        self.install_button.setEnabled(False)
        self.window().close()

    def open_download_page(self) -> None:
        release = self.release or {}
        url = str(release.get("download_url") or release.get("html_url") or updater.REPO_URL)
        QDesktopServices.openUrl(QUrl(url))

    def _set_state(self, text: str, *, checking: bool) -> None:
        self.status_label.setText(text)
        self.check_button.setEnabled(not checking and not self._busy)


class UpdateDialog(QDialog):
    """独立更新窗：设置侧栏没有「更新」域，菜单/通知都落到这里。

    2026-11-23 侧栏的更新页被摘掉（当时没有发布源），但 ``_UpdateBridge``
    仍会把用户送去 ``open_settings(initial_page="更新")`` ——那是条死路。
    这里给命令一个不依赖侧栏的落点：拿到 release 就直接显示结果，没拿到
    则打开后自动查一次。
    """

    def __init__(self, config, *, include_chat: bool = True, release=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("挽昼桌宠 · 检查更新")
        self.setMinimumWidth(460)
        try:
            from .application_icon import load_application_icon

            self.setWindowIcon(load_application_icon())
        except Exception:  # noqa: BLE001 - 图标缺失不该挡住更新窗
            logging.debug('更新窗图标加载失败', exc_info=True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        self.page = UpdatePage(config, include_chat=include_chat, parent=self)
        outer.addWidget(self.page)
        if release is not None:
            self.page.apply_release(release)
        else:
            QTimer.singleShot(0, self.page.check_for_updates)


__all__ = ["UpdateDialog", "UpdatePage"]
