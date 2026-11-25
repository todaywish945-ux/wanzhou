# -*- coding: utf-8 -*-
"""黄金回旋开关的每宠读写入口：真源是各桌宠自己的 ``config-角色X.json``。

用户口径：林德薇恩开就只有林德薇恩转；之前给艾尔妲开过的还照转，没开过的
德蕾琪娜不转。老配置本来就是把这两键写在实例配置里的，所以继续以实例配置
为真源，不再用主配置覆盖（那会把三只统一，违背每宠语义）。

设置页有两种身份：
* 独立设置进程 ``--instance slot-N``（以及空身份的主设置会话）：经
  ``SlotRoutedConfig`` 看见的是档案身份，先把槽档案里的 ``character`` 解析成
  ``config-角色X.json``，再读写那一份；
* 桌宠窗口内打开的设置页 / 老式 ``--instance 角色X``：instance_id 直接就是角色
  id，目标文件就是那份实例配置。

拿不到角色（档案不存在/损坏、单配置测试桩）时退回配置对象自己的 path——
通常是主配置 ``config.json``，保证单宠/测试场景仍能 round trip。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import pet_profiles
from .config_write_lock import locked_update_json, read_json_dict

log = logging.getLogger("dsh-pet-standalone")

KEYS = ("golden_spin_on_click", "golden_spin_direct")


def _slot_of(identity: str) -> int | None:
    if not identity.startswith("slot-"):
        return None
    try:
        return int(identity[len("slot-"):])
    except ValueError:
        return None


def target_path(config: Any) -> Path:
    """这份设置会话对应的**实例配置**路径（每宠真源）。"""
    directory = Path(getattr(config, "dir", ".") or ".")
    identity = str(getattr(config, "instance_id", "") or "").strip()
    character = ""
    slot = _slot_of(identity)
    if slot is not None:
        profile = pet_profiles.read_slot_profile(directory, slot)
        if profile.status == "ok":
            # 只读档案里**显式写过**的 character；不能走 value() 的同源默认
            # （缺键时它会给"角色A"，把空档案的主设置会话错误重定向到角色A，
            # 而且第一次写入创建档案后第二次调用的目标会突然变了）。
            raw = profile.data.get("character") if isinstance(profile.data, dict) else None
            character = str(raw or "")
    elif identity:
        character = identity
    else:
        profile = pet_profiles.read_slot_profile(directory, 0)
        if profile.status == "ok":
            raw = profile.data.get("character") if isinstance(profile.data, dict) else None
            character = str(raw or "")
    if character:
        return directory / f"config-{character}.json"
    # 没有可解析的角色时绝不退回配置对象自己的 path：设置页在 slot-N 身份下
    # 那个 path 是**槽档案**，写进去会污染代次/档案（回归用例钉得很死）。
    # 统一落到主配置，单宠/测试场景仍能 round trip。
    return directory / "config.json"


def read(config: Any, key: str, *, default: Any = False) -> Any:
    """读每宠开关：实例配置里出现过就用它，否则回落配置对象自己的读源。"""
    data, status = read_json_dict(target_path(config))
    if status == "ok" and isinstance(data, dict) and key in data:
        return data[key]
    getter = getattr(config, "get", None)
    return getter(key, default) if callable(getter) else default


def write(config: Any, key: str, value: Any) -> None:
    """把开关原子写进这只宠的实例配置（目录写锁，不覆盖别人的并发更新）。"""
    path = target_path(config)
    data = {"value": bool(value)}

    def mutate(current: dict) -> dict:
        current[key] = data["value"]
        return current

    locked_update_json(path, mutate)
    # 同步内存视图两种情况：①目标就是配置对象自己（单宠/测试桩）；②目标是主
    # 配置（无角色的 slot/空身份兜底）——路由视图的 set 会把它记进全局待写区，
    # 让随后的 config.save() 一并落盘，不产生"盘上写了、内存没有"的草稿打架。
    own = getattr(config, "path", None)
    if (own is not None and Path(own) == path) or path.name == "config.json":
        setter = getattr(config, "set", None)
        if callable(setter):
            setter(key, data["value"])
    log.info("黄金回旋每宠设置已落盘 %s: %s=%s", path.name, key, data["value"])
