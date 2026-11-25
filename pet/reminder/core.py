# -*- coding: utf-8 -*-
"""提醒事项纯逻辑层：数据模型、到点判定、持久化编解码（零 Qt、零 IO）。

只做"给定当前时间，哪些提醒该响"的判定，不碰定时器、不碰界面、不碰配置——
这样能在无 GUI 环境里精确测试跨天/重复/去重等边界。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Iterable

# 三种提醒类型
TYPE_CLOCK = "clock"        # 每天/单次 指定时刻 HH:MM
TYPE_COUNTDOWN = "countdown"  # N 分钟后
TYPE_ONCE = "once"          # 指定日期时间 YYYY-MM-DD HH:MM
VALID_TYPES = frozenset({TYPE_CLOCK, TYPE_COUNTDOWN, TYPE_ONCE})

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_DATETIME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})$")
_MAX_TITLE = 120


@dataclass
class Reminder:
    """一条提醒。

    id       —— 稳定唯一 id（毫秒时间戳 + 随机尾）
    type     —— clock / countdown / once
    title    —— 提醒内容（气泡与语音念它）
    hour/minute —— clock 用；repeat=True 每天重复，False 单次当天
    seconds  —— countdown 用，剩余秒数（每次 tick 递减）
    at       —— once 用，"YYYY-MM-DD HH:MM"
    repeat   —— clock：每天重复
    enabled  —— 总开关（关掉但保留，方便再开）
    done     —— 已触发完成（触发后置 True，从活动列表移除但保留在盘上一段时间）
    last_fired —— clock 去重用，记录上次触发的日期 "YYYY-MM-DD"；once 记录 ISO 时刻
    created_at —— 创建时间（毫秒）
    """
    id: int
    type: str
    title: str = ""
    hour: int | None = None
    minute: int | None = None
    seconds: int = 0
    at: str = ""
    repeat: bool = False
    enabled: bool = True
    done: bool = False
    last_fired: str = ""
    created_at: int = 0

    def is_active(self) -> bool:
        return self.enabled and not self.done


_id_counter = 0


def _new_id() -> int:
    """毫秒时间戳 + 进程内单调计数，保证同毫秒连加也绝不碰撞。

    （早先用 3 位随机尾，200 次同毫秒生成实测会碰撞约 10%，已改计数器。）
    """
    global _id_counter
    _id_counter += 1
    base = int(time.time() * 1000) * 10000
    return base + (_id_counter % 10000)


def make_clock(hour: int, minute: int, title: str = "", *, repeat: bool = True) -> Reminder:
    return Reminder(
        id=_new_id(), type=TYPE_CLOCK, title=clean_title(title),
        hour=int(hour), minute=int(minute), repeat=bool(repeat),
        created_at=int(time.time() * 1000),
    )


def make_countdown(minutes: float, title: str = "") -> Reminder:
    seconds = max(1, int(round(float(minutes) * 60)))
    return Reminder(
        id=_new_id(), type=TYPE_COUNTDOWN, title=clean_title(title),
        seconds=seconds, created_at=int(time.time() * 1000),
    )


def make_once(at: str, title: str = "") -> Reminder:
    return Reminder(
        id=_new_id(), type=TYPE_ONCE, title=clean_title(title),
        at=normalize_datetime(at), created_at=int(time.time() * 1000),
    )


def clean_title(value: Any) -> str:
    """气泡与语音都要念，去掉换行/控制字符并限长。"""
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"[\x00-\x1f\x7f]", "", text).strip()
    return text[:_MAX_TITLE]


def normalize_datetime(value: str) -> str:
    """校验并规范 once 的时间字符串为 'YYYY-MM-DD HH:MM'，非法抛 ValueError。"""
    m = _DATETIME_RE.match(str(value or "").strip())
    if not m:
        raise ValueError("时间格式应为 YYYY-MM-DD HH:MM")
    y, mo, d, h, mi = (int(x) for x in m.groups())
    dt = datetime(y, mo, d, h, mi)  # 非法日期（如 2 月 30）会抛 ValueError
    return dt.strftime("%Y-%m-%d %H:%M")


def _event_key(kind: str, at: datetime) -> str:
    """去重键：同一分钟/同一天只触发一次。"""
    if kind == TYPE_CLOCK:
        return at.strftime("%Y-%m-%d")
    return at.strftime("%Y-%m-%d %H:%M")


def due_reminders(reminders: Iterable[Reminder], now: datetime | None = None) -> list[tuple[Reminder, str]]:
    """返回本拍到点的 ``(提醒, 默认文案)`` 列表；**不修改传入对象**。

    - clock：HH:MM 命中且当天未触发过（last_fired 去重）。repeat=False 触发即 done。
    - countdown：调用方每拍先把 seconds 减 1（见 tick_countdowns），这里只挑 seconds<=0。
    - once：当前时刻 >= at 且该分钟未触发过。过期很久的 once（比如关机错过）也只补一次。
    """
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    hhmm = f"{now.hour:02d}:{now.minute:02d}"
    due: list[tuple[Reminder, str]] = []
    for r in reminders:
        if not r.is_active():
            continue
        if r.type == TYPE_CLOCK:
            if r.hour is None or r.minute is None:
                continue
            if f"{r.hour:02d}:{r.minute:02d}" != hhmm:
                continue
            if r.last_fired == today:
                continue
            due.append((r, r.title or f"到 {hhmm} 啦，别忘了这件事"))
        elif r.type == TYPE_COUNTDOWN:
            if r.seconds > 0:
                continue
            due.append((r, r.title or "时间到，歇一下吧"))
        elif r.type == TYPE_ONCE:
            if not r.at:
                continue
            try:
                target = datetime.strptime(r.at, "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if now < target:
                continue
            key = _event_key(TYPE_ONCE, now)
            if r.last_fired == key:
                continue
            due.append((r, r.title or f"提醒你：{r.at} 到了"))
    return due


def tick_countdowns(reminders: Iterable[Reminder], seconds: int = 1) -> bool:
    """把所有活动倒计时的剩余秒数递减（下限 0）；返回是否有变化。"""
    changed = False
    for r in reminders:
        if r.type == TYPE_COUNTDOWN and r.is_active() and r.seconds > 0:
            r.seconds = max(0, r.seconds - max(0, int(seconds)))
            changed = True
    return changed


def mark_fired(reminder: Reminder, now: datetime | None = None) -> None:
    """触发后收口：重复闹钟记当天去重键；其余标记完成。"""
    now = now or datetime.now()
    if reminder.type == TYPE_CLOCK and reminder.repeat:
        reminder.last_fired = now.strftime("%Y-%m-%d")
    else:
        reminder.done = True
        if reminder.type == TYPE_ONCE:
            reminder.last_fired = now.strftime("%Y-%m-%d %H:%M")


def next_fire_text(reminder: Reminder) -> str:
    """管理窗口列表里显示"下次触发"的一行摘要。"""
    if reminder.type == TYPE_CLOCK:
        tag = "每天" if reminder.repeat else "单次"
        return f"⏰ {reminder.hour:02d}:{reminder.minute:02d} · {tag}"
    if reminder.type == TYPE_COUNTDOWN:
        mm, ss = divmod(max(0, reminder.seconds), 60)
        return f"⏳ 剩余 {mm:02d}:{ss:02d}"
    if reminder.type == TYPE_ONCE:
        return f"📅 {reminder.at}"
    return ""


def clean_reminders(items: Iterable[Any]) -> list[Reminder]:
    """从盘上数据清洗出合法提醒；脏数据整条丢弃，不让它污染调度。"""
    by_id: dict[int, Reminder] = {}
    for raw in items if isinstance(items, (list, tuple)) else ():
        try:
            if not isinstance(raw, dict):
                continue
            rid = int(raw.get("id") or 0)
            if rid <= 0:
                continue
            kind = str(raw.get("type") or "")
            if kind not in VALID_TYPES:
                continue
            r = Reminder(
                id=rid, type=kind, title=clean_title(raw.get("title")),
                hour=_opt_int(raw.get("hour")), minute=_opt_int(raw.get("minute")),
                seconds=max(0, int(raw.get("seconds") or 0)),
                at=str(raw.get("at") or ""), repeat=bool(raw.get("repeat")),
                enabled=bool(raw.get("enabled", True)), done=bool(raw.get("done")),
                last_fired=str(raw.get("last_fired") or ""),
                created_at=int(raw.get("created_at") or 0),
            )
            if kind == TYPE_CLOCK and (r.hour is None or r.minute is None
                                       or not (0 <= r.hour <= 23) or not (0 <= r.minute <= 59)):
                continue
            if kind == TYPE_ONCE:
                r.at = normalize_datetime(r.at)
            # 同 id 保留信息更完整的一条（title 非空 / created_at 更晚），
            # 避免盘上脏的半条先占位、把合法条目当重复丢掉。
            old = by_id.get(rid)
            if old is None or _completeness(r) > _completeness(old):
                by_id[rid] = r
        except (ValueError, TypeError, OverflowError):
            continue
    return list(by_id.values())


def _completeness(r: Reminder) -> tuple:
    """同 id 冲突时的取舍排序：有内容 > 有时间戳 > 有触发记录。"""
    return (bool(r.title), r.created_at, bool(r.last_fired))


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def encode_reminders(reminders: Iterable[Reminder]) -> list[dict]:
    """落盘形状：只保留已完成/已禁用的最近若干条，避免无限增长。"""
    active = [asdict(r) for r in reminders if r.is_active()]
    finished = [asdict(r) for r in reminders if not r.is_active()]
    return active + finished[-20:]


def decode_reminders(value: Any) -> list[Reminder]:
    return clean_reminders(value if isinstance(value, list) else [])
