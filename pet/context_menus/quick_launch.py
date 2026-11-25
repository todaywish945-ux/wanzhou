# -*- coding: utf-8 -*-
"""Configurable application shortcuts used only by the modern menu."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QFileInfo, QRectF, QProcess, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QFileIconProvider, QMenu

from ..config import DEFAULT_QUICK_LAUNCH_APPS
from .icons import vector_menu_icon
from .shared import add_submenu, connect_action


def configured_quick_apps(config) -> list[dict]:
    value = config.get("quick_launch_apps", DEFAULT_QUICK_LAUNCH_APPS)
    return [dict(item) for item in value if isinstance(item, dict)]


# 首次 QFileIconProvider 取应用图标可能较慢；按 (kind, path) 缓存结果
_QUICK_ICON_CACHE: dict[tuple[str, str], QIcon] = {}


def quick_app_icon(menu: QMenu, item: dict) -> QIcon:
    kind = str(item.get("kind") or "")
    path = str(item.get("path") or "")
    cache_key = (kind, path)
    cached = _QUICK_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if kind in ("default_browser", "url") or _looks_like_url(path):
        icon = vector_menu_icon(menu, "web")
    else:
        icon = QFileIconProvider().icon(QFileInfo(path)) if path else QIcon()
        icon = fitted_application_icon(icon, 18, menu) if not icon.isNull() else vector_menu_icon(menu, "application")
    _QUICK_ICON_CACHE[cache_key] = icon
    return icon


def fitted_application_icon(icon: QIcon, size: int, widget) -> QIcon:
    """Crop provider padding and fill the requested logical icon canvas."""
    if icon.isNull():
        return icon
    dpr = max(1.0, widget.devicePixelRatioF())
    source_size = max(32, round(size * dpr * 2))
    source = icon.pixmap(source_size, source_size)
    source.setDevicePixelRatio(1.0)
    bounds = QRegion(source.mask()).boundingRect()
    if bounds.isEmpty():
        return icon
    canvas = QPixmap(max(1, round(size * dpr)), max(1, round(size * dpr)))
    canvas.setDevicePixelRatio(dpr)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(
        QRectF(0.5, 0.5, size - 1.0, size - 1.0),
        source,
        QRectF(bounds),
    )
    painter.end()
    return QIcon(canvas)


def _looks_like_url(value: str) -> bool:
    """path 是否是网址（含旧数据里以 application 存的网址）。

    只认 http(s):// 与 www. 开头，避免把本地文件名误判成网址。
    """
    lowered = value.strip().lower()
    return lowered.startswith(("http://", "https://", "www."))


def launch_quick_app(item: dict) -> bool:
    if item.get("kind") == "default_browser":
        # 打开浏览器主页/新标签：about:blank 零网络请求，任何浏览器都秒开。
        # 旧版写死 google.com，国内网络连不上会一直转圈（用户反馈）。
        return bool(QDesktopServices.openUrl(QUrl("about:blank")))
    raw = str(item.get("path") or "").strip()
    # 网址统一走浏览器：kind 为 url，或旧版把网址塞进 application 的 path 里
    #（旧设置进程没有「添加网址…」，用户填的网址以 application 存盘——若按本地
    #  路径走 os.path.abspath 会变成 "<cwd>/https:/xxx"，os.startfile 静默失败＝点了没反应）。
    # 判据：显式 http(s)://，或没协议的 "www." 开头。
    if item.get("kind") == "url" or _looks_like_url(raw):
        if not raw:
            return False
        qurl = QUrl(raw)
        if not qurl.isValid() or not qurl.scheme():
            qurl = QUrl("https://" + raw)
        return bool(QDesktopServices.openUrl(qurl))
    path = os.path.abspath(os.path.expanduser(raw))
    if not path:
        return False
    if sys.platform == "darwin":
        return bool(QProcess.startDetached("open", [path]))
    if sys.platform == "win32":
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        except OSError:
            return False
    if os.path.isdir(path):
        return bool(QProcess.startDetached("xdg-open", [path]))
    return bool(QProcess.startDetached(path, []))


def add_quick_launch_menu(menu: QMenu, config) -> QMenu:
    apps = configured_quick_apps(config)
    submenu = add_submenu(menu, "快捷启动", "application")
    if not apps:
        placeholder = submenu.addAction("尚未配置快捷项")
        placeholder.setEnabled(False)
        return submenu
    for item in apps:
        action = submenu.addAction(quick_app_icon(submenu, item), str(item.get("name") or "应用"))
        action.setProperty("closeOnTrigger", True)
        connect_action(action, lambda item=dict(item): launch_quick_app(item))
    return submenu
