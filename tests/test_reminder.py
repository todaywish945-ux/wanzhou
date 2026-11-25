# -*- coding: utf-8 -*-
"""提醒事项（闹钟/倒计时/单次）纯逻辑与服务调度测试。"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from pet.reminder.core import (
    TYPE_CLOCK, TYPE_COUNTDOWN, TYPE_ONCE,
    Reminder, clean_reminders, decode_reminders, due_reminders,
    encode_reminders, make_clock, make_countdown, make_once,
    mark_fired, next_fire_text, tick_countdowns,
)

NOW = datetime(2026, 11, 24, 9, 30)


# ------------------------------------------------------------------ 数据模型
def test_make_helpers_set_types_and_clean_title():
    assert make_clock(9, 30, "  开会\n ").type == TYPE_CLOCK
    assert make_clock(9, 30, "开会").title == "开会"
    assert make_clock(9, 30, "  ").title == ""
    assert make_countdown(1.5, "泡面").seconds == 90
    assert make_countdown(0).seconds == 1
    assert make_once("2026-11-25 08:00", "看牙").at == "2026-11-25 08:00"


def test_make_once_rejects_bad_datetime():
    with pytest.raises(ValueError):
        make_once("不是时间")
    with pytest.raises(ValueError):  # 2 月 30 不存在
        make_once("2026-02-30 09:00")


def test_ids_are_unique_even_in_same_millisecond(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 1700000000.123)
    ids = {make_clock(9, 0).id for _ in range(200)}
    assert len(ids) == 200


# ------------------------------------------------------------------ 到点判定
def test_clock_fires_at_minute_and_dedupes_same_day():
    r = make_clock(9, 30, "吃药", repeat=True)
    assert len(due_reminders([r], NOW)) == 1
    r.last_fired = "2026-11-24"
    assert due_reminders([r], NOW) == []


def test_daily_repeat_marks_last_fired_not_done():
    r = make_clock(9, 30, "吃药", repeat=True)
    mark_fired(r, NOW)
    assert r.last_fired == "2026-11-24"
    assert not r.done
    assert r.is_active()


def test_one_shot_clock_marks_done():
    r = make_clock(9, 30, "交报告", repeat=False)
    mark_fired(r, NOW)
    assert r.done
    assert not r.is_active()


def test_clock_wrong_minute_does_not_fire():
    r = make_clock(9, 31, "还没到")
    assert due_reminders([r], NOW) == []


def test_countdown_decrements_and_fires_once():
    r = make_countdown(1, "泡面")
    assert due_reminders([r], NOW) == []
    assert tick_countdowns([r], 59) is True
    assert r.seconds == 1
    assert due_reminders([r], NOW) == []
    tick_countdowns([r], 1)
    assert r.seconds == 0
    assert len(due_reminders([r], NOW)) == 1
    mark_fired(r, NOW)
    assert r.done


def test_countdown_never_goes_negative():
    r = make_countdown(1, "x")
    tick_countdowns([r], 999)
    assert r.seconds == 0


def test_once_fires_at_or_after_target_but_only_once():
    r = make_once("2026-11-24 09:30", "看牙医")
    assert len(due_reminders([r], NOW)) == 1
    mark_fired(r, NOW)
    assert due_reminders([r], NOW) == []
    # 过期很久也只补一次
    r2 = make_once("2026-11-01 08:00", "过期")
    assert len(due_reminders([r2], NOW)) == 1


def test_once_in_future_does_not_fire():
    r = make_once("2026-11-24 09:31", "还没到")
    assert due_reminders([r], NOW) == []


def test_disabled_and_done_never_fire():
    r1 = make_clock(9, 30, "x")
    r1.enabled = False
    r2 = make_clock(9, 30, "y")
    r2.done = True
    assert due_reminders([r1, r2], NOW) == []


def test_next_fire_text():
    assert "09:30" in next_fire_text(make_clock(9, 30, "x"))
    assert "剩余" in next_fire_text(make_countdown(2, "x"))
    assert "2026-11-25" in next_fire_text(make_once("2026-11-25 08:00", "x"))


# ------------------------------------------------------------------ 持久化
def test_encode_decode_roundtrip():
    items = [make_clock(9, 30, "吃药", repeat=True),
             make_countdown(5, "泡面"),
             make_once("2026-11-25 08:00", "看牙")]
    encoded = encode_reminders(items)
    assert isinstance(json.loads(json.dumps(encoded)), list)
    back = decode_reminders(encoded)
    assert [r.title for r in back] == ["吃药", "泡面", "看牙"]


def test_clean_reminders_drops_garbage():
    good = make_clock(9, 30, "ok")
    dirty = [
        "not a dict",
        {"id": -1, "type": "clock", "hour": 9, "minute": 30},
        {"id": 999, "type": "unknown"},
        {"id": 1000, "type": "clock", "hour": 99, "minute": 30},
        {"id": good.id, "type": "clock", "hour": 9, "minute": 30},  # 重复 id
        {"id": 2000, "type": "once", "at": "bad"},
    ]
    out = clean_reminders(dirty + [encode_reminders([good])[0]])
    assert len(out) == 1
    assert out[0].title == "ok"


# ------------------------------------------------------------------ 服务层
def test_service_tick_fires_bubble_and_speech(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.config import Config
    from pet.reminder.service import ReminderService

    calls: list[tuple] = []

    class FakeWin:
        def show_bubble(self, text, duration_ms=0):
            calls.append(("bubble", text))

    class FakeChannel:
        def speak(self, text, log_tag=""):
            calls.append(("speak", text, log_tag))

    class FakeShell:
        def __init__(self):
            self.config = Config(str(tmp_path))
            self.win = FakeWin()
            self._ch = FakeChannel()

        def ensure_audio_channel(self):
            return self._ch

    shell = FakeShell()
    svc = ReminderService(shell, tick_ms=100000)
    svc.add(make_clock(9, 30, "吃药", repeat=True))
    svc.add(make_countdown(1, "泡面"))
    svc.add(make_once("2026-11-24 09:30", "看牙医"))
    tick_countdowns(svc.reminders, 60)

    fired = svc.tick(now=NOW)
    assert {r.title for r in fired} == {"吃药", "泡面", "看牙医"}
    assert sum(1 for c in calls if c[0] == "bubble") == 3
    assert sum(1 for c in calls if c[0] == "speak") == 3
    assert all(c[2] == "提醒事项" for c in calls if c[0] == "speak")

    # 同分钟再 tick 不重复响
    assert svc.tick(now=NOW) == []

    # 落盘后重载条目还在
    svc2 = ReminderService(shell, tick_ms=100000)
    assert len(svc2.reminders) == 3


# ------------------------------------------------------------------ 隐藏时的落点
def test_hidden_pet_falls_back_to_system_notification_only(tmp_path):
    """桌宠隐藏：只发系统通知、不碰灵动岛；桌宠可见：只走气泡。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.config import Config
    from pet.reminder.service import ReminderService

    calls: list[str] = []

    class FakeIsland:
        def isVisible(self):
            return True

        def set_last_message(self, text):
            calls.append("island_message")

        def notify_event(self, kind):
            calls.append(f"island_event:{kind}")

    class FakeWin:
        def __init__(self, visible):
            self._visible = visible

        def isVisible(self):
            return self._visible

        def show_bubble(self, text, duration_ms=0):
            calls.append("bubble")

    class FakeShell:
        def __init__(self, visible):
            self.config = Config(str(tmp_path))
            self.win = FakeWin(visible)
            self.island = FakeIsland()

        def ensure_audio_channel(self):
            return None

        def system_notify(self, title, message):
            calls.append("system_notify")

        def _show_island_chat(self, *, activate=True, reply_text=None):
            calls.append(f"island_preview:{activate}:{reply_text}")

    # 隐藏：只发系统通知，不碰岛（岛气泡已移除，岛改摘要要手动点开=没提醒）
    hidden = FakeShell(visible=False)
    svc = ReminderService(hidden, tick_ms=100000)
    svc.add(make_clock(9, 30, "吃药", repeat=True))
    svc.tick(now=NOW)
    assert "system_notify" in calls
    assert "bubble" not in calls
    assert not any(c.startswith("island_") for c in calls), "不应再走灵动岛"

    # 可见：只走气泡，不走通知/岛
    calls.clear()
    visible_shell = FakeShell(visible=True)
    svc2 = ReminderService(visible_shell, tick_ms=100000)
    svc2.add(make_clock(9, 30, "开会", repeat=True))
    svc2.tick(now=NOW)
    assert "bubble" in calls
    assert "system_notify" not in calls
    assert not any(c.startswith("island_") for c in calls)


def test_chime_plays_on_due_and_respects_quiet(tmp_path, monkeypatch):
    """到点提示音：普通情况响一声；免打扰时不响应。"""
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pet.config import Config
    from pet.reminder.service import ReminderService

    played: list[str] = []

    class FakeWin:
        def isVisible(self):
            return True

        def show_bubble(self, text, duration_ms=0):
            pass

        @property
        def cfg(self):
            return config

    class FakeShell:
        def __init__(self):
            self.win = FakeWin()

        def ensure_audio_channel(self):
            return None

    config = Config(str(tmp_path))
    shell = FakeShell()

    # 非 Windows 平台上 _play_chime 直接 return，这里模拟 win32 分支
    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    monkeypatch.setitem(sys.modules, "winsound", type("W", (), {
        "SND_ALIAS": 1, "SND_ASYNC": 2,
        "PlaySound": staticmethod(lambda name, flags: played.append(name)),
    }))

    # 普通情况：响
    svc = ReminderService(shell, config=config, tick_ms=100000)
    svc.add(make_clock(9, 30, "吃药", repeat=True))
    svc.tick(now=NOW)
    assert played == ["SystemAsterisk"]

    # 免打扰：不响（monkeypatch quiet_blocked）
    played.clear()
    from pet import window_alerts
    monkeypatch.setattr(window_alerts, "quiet_blocked", lambda win: True)
    svc2 = ReminderService(shell, config=config, tick_ms=100000)
    svc2.add(make_clock(9, 30, "开会", repeat=True))
    svc2.tick(now=NOW)
    assert played == []
