# -*- coding: utf-8 -*-
"""提醒事项 Qt 管理器：每秒 tick，到点走桌宠气泡 + 语音播报。

挂在 AppShell（进程级单例，多窗共用一套定时器，避免每宠一个重复响）。
配置存在 ``config['reminders']`` —— 复用本项目的 Config，多开隔离/写锁/迁移
全部免费，不再像小蕾米那样单独写一个 JSON 文件。

气泡/语音的取用都走 shell 的动态属性（``shell.win`` / ``ensure_audio_channel``），
角色热切换重建窗口后无需重绑。
"""
from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QObject, QTimer

from ..config import Config
from .core import (
    Reminder,
    decode_reminders,
    due_reminders,
    encode_reminders,
    mark_fired,
    tick_countdowns,
)

log = logging.getLogger(__name__)

CONFIG_KEY = "reminders"
TICK_MS = 1000


class ReminderService(QObject):
    """提醒调度器：每秒递减倒计时、判定到点、触发气泡与语音。"""

    def __init__(self, shell, config: Config | None = None, *, tick_ms: int = TICK_MS):
        # 真实宿主 AppShell 是 QObject，挂为父对象随其析构；测试替身可能不是
        # QObject，此时不传 parent（QTimer 仍以 self 为父，生命周期自洽）。
        parent = shell if isinstance(shell, QObject) else None
        super().__init__(parent)
        self._shell = shell
        self._cfg = config if config is not None else getattr(shell, "config", None)
        self.reminders: list[Reminder] = decode_reminders(
            self._cfg.get(CONFIG_KEY, []) if self._cfg is not None else []
        )
        self._timer = QTimer(self)
        self._timer.setObjectName("reminderTick")
        self._timer.timeout.connect(self.tick)
        self._timer.start(tick_ms)

    # ------------------------------------------------------------------ 持久化
    def save(self) -> bool:
        if self._cfg is None:
            return False
        self._cfg.set(CONFIG_KEY, encode_reminders(self.reminders))
        return bool(self._cfg.save())

    def reload(self) -> None:
        if self._cfg is None:
            return
        self.reminders = decode_reminders(self._cfg.get(CONFIG_KEY, []))

    # ------------------------------------------------------------------ 增删改
    def add(self, reminder: Reminder) -> Reminder:
        self.reminders.append(reminder)
        self.save()
        return reminder

    def remove(self, reminder_id: int) -> bool:
        before = len(self.reminders)
        self.reminders = [r for r in self.reminders if r.id != int(reminder_id)]
        changed = len(self.reminders) != before
        if changed:
            self.save()
        return changed

    def toggle(self, reminder_id: int, enabled: bool) -> bool:
        for r in self.reminders:
            if r.id == int(reminder_id):
                r.enabled = bool(enabled)
                if enabled:
                    r.done = False  # 再开一次：已完成的允许重激活
                self.save()
                return True
        return False

    def clear_finished(self) -> int:
        before = len(self.reminders)
        self.reminders = [r for r in self.reminders if r.is_active()]
        removed = before - len(self.reminders)
        if removed:
            self.save()
        return removed

    # ------------------------------------------------------------------ 调度
    def tick(self, *, now: datetime | None = None) -> list[Reminder]:
        """一拍：递减倒计时 → 找到期项 → 标记并触发。返回本拍响了的提醒。"""
        now = now or datetime.now()
        changed = tick_countdowns(self.reminders)
        fired: list[Reminder] = []
        for reminder, fallback in due_reminders(self.reminders, now):
            mark_fired(reminder, now)
            changed = True
            fired.append(reminder)
            self._notify(reminder, fallback)
        if changed:
            self.save()
        return fired

    def _notify(self, reminder: Reminder, fallback: str) -> None:
        """到点提醒：桌宠气泡 + 提示音 + 语音；桌宠隐藏时气泡改走系统通知。

        落点判据与现有语音报时一致：桌宠可见走气泡，隐藏则气泡锚不到桌宠，
        改发系统通知（右下角）。灵动岛不走——岛对话气泡已被整体移除
        （``_island_chat_available`` 恒 False），岛只改摘要文字要用户点开才
        看得到，等于没提醒。提示音 + 语音两种情况都触发。
        """
        text = (reminder.title or fallback).strip()
        prefix = {"clock": "⏰ 提醒", "countdown": "⏳ 时间到", "once": "📅 提醒"}.get(
            reminder.type, "提醒")
        bubble = f"{prefix}：{text}"

        # 1) 文字落点：桌宠可见走气泡；隐藏改发系统通知（不依赖窗口可见）。
        win = getattr(self._shell, "win", None)
        visible = False
        if win is not None:
            try:
                is_visible = getattr(win, "isVisible", None)
                visible = bool(is_visible()) if callable(is_visible) else True
            except Exception:
                visible = True  # 判不了就当可见，走气泡（不误伤通知路径）

        if visible and win is not None and callable(getattr(win, "show_bubble", None)):
            try:
                win.show_bubble(bubble, duration_ms=6000)
            except Exception:
                log.exception("提醒气泡展示失败（改发系统通知）")
                visible = False

        if not visible:
            self._notify_hidden(text, prefix)

        # 2) 提示音：先"叮"一声引起注意，再播内容。免打扰时跳过（与语音同口径）。
        self._play_chime()

        # 3) 语音播报：复用报时服务的音频通道，和整点报时共用、不可能叠音。
        try:
            channel_getter = getattr(self._shell, "ensure_audio_channel", None)
            channel = channel_getter() if callable(channel_getter) else None
            if channel is not None and callable(getattr(channel, "speak", None)):
                channel.speak(text, log_tag="提醒事项")  # respect_quiet 默认 True
        except Exception:
            log.exception("提醒语音播报失败（文字照常）")

    def _play_chime(self) -> None:
        """到点提示音：一声系统提示音，让用户还没看那一块也能察觉。

        走 winsound（Windows 系统音，零资源依赖）；免打扰时不响，与语音播报
        同口径——用户既然选了静音，就不该被一声"叮"破例。
        """
        import sys
        if sys.platform != "win32":
            return
        # 免打扰（含全屏等效）：与报时/语音同一判据。
        try:
            from .. import window_alerts
            win = getattr(self._shell, "win", None)
            if win is not None and window_alerts.quiet_blocked(win):
                return
        except Exception:
            pass  # 判据不可用时不拦（提示音是轻提醒，宁可响也别漏）
        try:
            import winsound
            winsound.PlaySound("SystemAsterisk",
                               winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            log.debug("提醒提示音播放失败（文字/语音照常）", exc_info=True)

    def _notify_hidden(self, text: str, title: str) -> None:
        """桌宠隐藏时的文字落点：系统通知（右下角）。

        灵动岛不走：岛对话气泡已整体移除（``_island_chat_available`` 恒 False），
        只剩改摘要文字，要用户主动点开岛才看得到——那不是提醒。系统通知与
        现有语音报时隐藏时的改道通知同一入口，稳定可见。
        """
        notify = getattr(self._shell, "system_notify", None)
        if callable(notify):
            try:
                notify(title, text)
            except Exception:
                log.exception("提醒事项系统通知失败")

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start(TICK_MS)

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def shutdown(self) -> None:
        """退出收口：停表 + 落盘（倒计时进度不丢）。"""
        self.stop()
        try:
            self.save()
        except Exception:
            log.exception("提醒事项退出落盘失败")
