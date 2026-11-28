# -*- coding: utf-8 -*-
"""移植裁剪桩：被裁掉的子系统在此提供惰性替代实现。

挽昼桌宠移植自 dsh-pet-indesktop，裁掉了 overlay/灵动岛/音乐歌词/待办/节日/
主动识屏/Agent 联动/帧序列动画等子系统（对应 feature 门保持关闭，入口永不
触达）。保留代码里指向这些模块的 import 统一改引本模块：

- 谓词/查询类（is_overlay_topology、session_ending、effective_proactive_config、
  other_instances_use_agent、write_command）返回安全默认值；
- 服务类（TodoReminderService、DecodeFanoutHub、ProactiveScreenWatcher、
  AgentLinkManager 等）是有 ``stop()`` 的惰性空壳，被误构造也不炸；
- 未知名走 PEP 562 模块级 ``__getattr__`` 返回空壳——只应出现在被门禁挡死的
  路径上；真被触达时表现为"什么都不做"，不会崩溃。
"""
from __future__ import annotations

from typing import Any


class _InertMeta(type):
    """类级属性访问同样惰性：`AgentLinkManager.AGENT_NAMES` 这类"拿类当命名空间"
    的用法（模块别名指向 _Inert 类本身时）也回落空壳而不是 AttributeError。"""

    def __getattr__(cls, name: str) -> "_Inert":
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _Inert()


class _Inert(metaclass=_InertMeta):
    """惰性空壳：任意方法调用、任意属性链都返回新的空壳，绝不抛错。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def stop(self, *args: Any, **kwargs: Any) -> None:
        pass

    def stop_all(self, *args: Any, **kwargs: Any) -> None:
        pass

    def apply_config(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __getattr__(self, name: str) -> "_Inert":
        # dunder 一律抛 AttributeError：inspect/shiboken 的签名装载器会探测
        # __wrapped__/__module__ 等协议属性，返回空壳会让 unwrap 陷入"wrapper loop"。
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _Inert()

    def __call__(self, *args: Any, **kwargs: Any) -> "_Inert":
        return _Inert()

    def __bool__(self) -> bool:
        return False

    def __iter__(self):
        return iter(())

    def __add__(self, other):
        # `[...] + settings_music.xxx_rows()` 这类拼接：空壳按空序列参与
        return list(self) + list(other)

    def __radd__(self, other):
        return list(other)


def is_overlay_topology(*args: Any, **kwargs: Any) -> bool:
    """overlay 多宠拓扑已裁剪：恒为 legacy 单窗拓扑。"""
    return False


_SESSION_ENDING = False


def set_session_ending(on: bool) -> None:
    global _SESSION_ENDING
    _SESSION_ENDING = bool(on)


def session_ending() -> bool:
    return _SESSION_ENDING


def set_first_frame_budget(*args: Any, **kwargs: Any) -> None:
    pass


def effective_proactive_config(raw: Any = None) -> dict:
    """主动识屏已裁剪：返回全关配置（白名单为空 = 永不触发）。

    键集对齐上游 effective_proactive_config 的返回面（设置页/窗口侧按这些键
    直接下标访问，缺键会 KeyError）：开关全关 + 各阈值给中性默认值。
    """
    return {
        "enabled": False,
        "dry_run": False,
        "preset": "quiet",
        "dwell_seconds": 3,
        "cooldown_minutes": 10.0,
        "min_request_interval_seconds": 60,
        "daily_cap": 0,
        "require_idle": False,
        "allow_when_mouse_through": False,
        "pre_cue": False,
        "prefer_free_provider": False,
        "whitelist": [],
    }


def other_instances_use_agent(config: Any, agent_key: str) -> bool:
    return False


def slot_from_instance_id(instance_id: Any):
    """原契约：``slot-N`` → int N；其他身份（主身份/自定义实例）→ None。"""
    m = str(instance_id or "").strip()
    if m.startswith("slot-"):
        try:
            return int(m[len("slot-"):])
        except ValueError:
            return None
    return None


def write_command(config_dir: Any, command: Any, target: Any = None) -> bool:
    """overlay 指令通道已裁剪：假装写成功，设置刷新回落到配置监听/重启。"""
    return True


CMD_APPLY_SETTINGS_RESET = "apply_settings_reset"
CMD_PROFILE_RESET = "profile_reset"
CMD_EXIT_SPAWNED_PETS = "exit_spawned_pets"


class AgentEvent:
    """agent_event_protocol.AgentEvent 的注解占位（类型标注专用）。"""


class ClaudeCodeMonitor:
    @staticmethod
    def uninstall_hooks(*args: Any, **kwargs: Any) -> None:
        pass


class DshMonitor:
    @staticmethod
    def uninstall_bridge(*args: Any, **kwargs: Any) -> None:
        pass


# ---- 服务空壳别名：保留代码里 `from ._removed import X` 直接可用 ----
TodoReminderService = _Inert
DecodeFanoutHub = _Inert
ProactiveScreenWatcher = _Inert
AgentLinkManager = _Inert
FestivalReminderService = _Inert
OverlayShell = _Inert
TodoPanelDialog = _Inert
MusicLyricController = _Inert


def __getattr__(name: str) -> _Inert:
    """PEP 562：未列名的裁剪模块属性（island.balance 的函数、music.players 的
    注册表等）统一回落空壳。dunder 协议属性必须抛错（见 _Inert.__getattr__）。"""
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(name)
    return _Inert()
