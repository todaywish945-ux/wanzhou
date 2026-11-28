# -*- coding: utf-8 -*-
"""骗子酒馆牌局联动（挽昼桌宠移植版，协议沿用旧版单文件 pet.py）。

轮询 ``%APPDATA%/wanzhou-pet/联动事件.json``（源码开发期兼容仓库根旧位置）：``ts`` 大于上次时间戳即有一批新事件。
事件字段（只处理 ``char`` 等于本窗角色的第一条）：

- ``emotion``：表情名（= 素材文件名，如「生气」）→ :meth:`switch_clip` 播放，
  播完由窗口动画链自动回待机（无需旧版的定时恢复计时器）；
- ``move``：``{x, y, scale?}`` 牌局入座 → 移动并可选缩放（脚底锚定）；
- ``release``：散场 → 回到配置记忆的位置与缩放；
- ``speak``：牌局播报文本 → 交给本角色的语音通道朗读。

事件文件缺失/损坏/未更新一律静默跳过，绝不影响桌宠本体。
"""
from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

from . import catalog
from . import window_placement

log = logging.getLogger("pet.game_link")

_EVENT_FILENAME = "联动事件.json"
#: 源码开发期的旧位置（仓库根）：打包形态不存在，仅作兼容回退（测试可打桩）。
_LEGACY_EVENT_FILE = Path(__file__).resolve().parent.parent / _EVENT_FILENAME


def preferred_event_file() -> Path:
    """联动事件文件路径（读侧唯一入口，骗子酒馆写侧与此同源）。

    首选 ``%APPDATA%/wanzhou-pet/``（打包形态两边都写得到）；源码开发期旧
    位置（仓库根）有文件就回退兼容。两处都没有时仍返回 APPDATA 候选——
    调用方照常 open 失败静默，语义与“没有事件”一致。
    """
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    candidate = base / "wanzhou-pet" / _EVENT_FILENAME
    if candidate.is_file():
        return candidate
    return _LEGACY_EVENT_FILE if _LEGACY_EVENT_FILE.is_file() else candidate


class GameLink(QObject):
    """轮询牌局事件文件，驱动本窗角色入座 / 表情 / 散场回位。"""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self._ts = 0.0
        self._restore_state = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(1000)

    def _event_file(self) -> Path:
        return preferred_event_file()

    def _poll(self) -> None:
        try:
            with open(self._event_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            ts = float(data.get("ts", 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return
        # NaN 既不是有限数也不满足 <=，旧代码会把它当新事件每秒重放一次。
        if not math.isfinite(ts) or ts <= self._ts:
            return
        self._ts = ts
        character = str(self._win.cfg.get("character", ""))
        events = data.get("events", [])
        if not isinstance(events, list):
            return
        for ev in events:
            if not isinstance(ev, dict) or str(ev.get("char", "")) != character:
                continue
            self._apply(ev)
            break

    def _cancel_edge_probe(self) -> None:
        edge = getattr(self._win, "_edge_probe", None)
        if edge is None:
            return
        edge.cancel("game_link_seat", restore=False)
        sync_mask = getattr(self._win, "_sync_mask", None)
        if callable(sync_mask):
            # 无缩放时也要立即清掉旋转姿态留下的命中轮廓。
            sync_mask()

    def _apply(self, ev: dict) -> None:
        win = self._win
        move = ev.get("move")
        if isinstance(move, dict) or ev.get("release"):
            self._cancel_edge_probe()
        if isinstance(move, dict):
            if self._restore_state is None:
                self._restore_state = (win.x(), win.y(), float(win.scale))
            try:
                win.move(int(move.get("x", win.x())), int(move.get("y", win.y())))
            except (TypeError, ValueError):
                log.debug("联动 move 事件坐标非法: %r", move, exc_info=True)
            scale = move.get("scale")
            if scale:
                try:
                    scale_value = float(scale)
                    if not math.isfinite(scale_value) or scale_value <= 0:
                        raise ValueError("scale 必须是有限正数")
                    win.change_scale(scale_value, persist=False)
                except (TypeError, ValueError):
                    log.debug("联动 move 事件缩放非法: %r", scale)
        if ev.get("release"):
            if self._restore_state is not None:
                x, y, scale = self._restore_state
                self._restore_state = None
                win.change_scale(scale, persist=False)
                win.move(x, y)
                win._save_position()
            else:
                # 散场：读配置记忆的位置与缩放回原位
                window_placement.restore_position(win)
                win.change_scale(float(win.cfg.get("scale", catalog.DEFAULT_SCALE)),
                                 persist=False)
        emotion = ev.get("emotion")
        if emotion:
            win.switch_clip(str(emotion))
        speak = ev.get("speak")
        if isinstance(speak, str) and speak.strip():
            callback = getattr(win, "on_self_talk_speak", None)
            if callable(callback):
                try:
                    callback(speak.strip())
                except Exception:
                    log.exception("牌局语音播报失败")
