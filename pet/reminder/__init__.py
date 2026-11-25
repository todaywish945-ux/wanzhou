# -*- coding: utf-8 -*-
"""提醒事项：闹钟（每天重复）/ 倒计时 / 单次指定时刻。

架构（与本项目「纯逻辑层 + Qt 管理器」同族，参考小蕾米 alarm.py）：

- ``core.py``：纯逻辑、零 Qt——数据模型、到点判定、持久化编解码，可无 GUI 测试；
- ``service.py``：Qt 管理器——每秒 tick、气泡 + 语音播报、配置读写；
- ``settings.py`` / UI：管理窗口（另建），负责增删改查。

三种提醒：

- ``clock``：指定 HH:MM，可选每天重复（``repeat=True`` 用 ``last_fired`` 去重）；
- ``countdown``：剩余秒数递减，到 0 触发一次；
- ``once``：指定日期时间（YYYY-MM-DD HH:MM），到点触发一次。
"""
from .core import (
    Reminder,
    clean_reminders,
    decode_reminders,
    encode_reminders,
    due_reminders,
    make_clock,
    make_countdown,
    make_once,
    next_fire_text,
)

__all__ = [
    "Reminder", "clean_reminders", "decode_reminders",
    "encode_reminders", "due_reminders", "make_clock", "make_countdown",
    "make_once", "next_fire_text",
]
