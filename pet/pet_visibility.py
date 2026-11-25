# -*- coding: utf-8 -*-
"""桌宠显隐状态的**跨进程共享真值**（三角色 = 三个独立进程）。

为什么需要这个模块：三只桌宠各跑一个 pythonw 进程，右键「隐藏桌宠」只作用于
本进程窗口；而灵动岛只在角色 A 进程创建，物理上只有一个。要让「哪几只隐藏了」
这件事在三个进程间一致（岛据此分三段亮起、点段恢复任意一只、一键全部恢复），
必须有一份所有进程都读得到的共享状态——本模块就是它。

设计纪律：

- **状态文件落在配置目录**（与 `config-角色X.json` 同目录），路径只由目录决定，
  不随实例 id 变（实例 id 那份是名字空间，不是真相源的分裂）；
- **写走目录级跨进程写锁**（`config_write_lock.locked_update_json`）：三个进程
  的 hide/show 都是用户操作级写入，锁内重读合并，绝不整表覆盖别人的更新；
- **读是纯函数**：只认布尔值，缺键/坏类型按「可见」兜底（宁可少亮一段，不可
  把一只活着的宠误报成隐藏）；文件损坏不覆盖，由写入方按 `on_broken` 策略处理；
- **角色集合固定为三只**（`PET_IDS`）：本项目是三角色桌宠，岛恒定三段；任何
  额外键在读侧被忽略，避免别的工具往文件里塞东西把岛撑成四段。

对外 API 只有读（`read_visibility`）与合并写（`set_pet_visible` /
`set_all_visible` / `register_pet`），不含任何 Qt 依赖，便于纯逻辑测试。
"""
from __future__ import annotations

import logging
from pathlib import Path

from .config_write_lock import (
    ConfigWriteError,
    JsonStateError,
    read_json_dict,
    locked_update_json,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PET_IDS",
    "VISIBILITY_FILENAME",
    "any_hidden",
    "hidden_pet_ids",
    "read_visibility",
    "register_pet",
    "set_all_visible",
    "set_pet_visible",
    "visibility_path",
]

#: 三只桌宠的稳定 id（岛的三段顺序也按这个来，不按配置目录枚举——枚举会受
#: 用户新建角色包影响，而岛的段数在产品上是固定的三）。
PET_IDS: tuple[str, ...] = ("角色A", "角色B", "角色C")

#: 状态文件名（不带实例后缀：三个进程共享同一份）。
VISIBILITY_FILENAME = "pet-visibility.json"


def visibility_path(config_dir: Path | str) -> Path:
    """状态文件路径（只由配置目录决定，与实例身份无关）。"""
    return Path(config_dir) / VISIBILITY_FILENAME


def read_visibility(config_dir: Path | str) -> dict[str, bool]:
    """读三只桌宠的可见性；缺键/坏值按「可见」兜底。

    返回一份**新的** dict，键序恒为 :data:`PET_IDS`。文件不存在、损坏、非对象
    一律返回「三只都可见」——这是安全侧：宁可岛不亮，不可把在屏上的宠报成隐藏
    （那会让岛多出一段、用户点了「显示」却什么都没发生）。
    """
    data, status = read_json_dict(visibility_path(config_dir))
    if status != "ok" or not isinstance(data, dict):
        if status not in ("missing", "ok"):
            logger.warning("桌宠显隐状态不可信（%s），按全可见兜底", status)
        return {pet_id: True for pet_id in PET_IDS}
    return {
        pet_id: data[pet_id] if isinstance(data.get(pet_id), bool) else True
        for pet_id in PET_IDS
    }


def any_hidden(visibility: dict[str, bool]) -> bool:
    """是否至少有一只隐藏（灵动岛该出现的判据）。"""
    return any(not bool(visibility.get(pet_id, True)) for pet_id in PET_IDS)


def hidden_pet_ids(visibility: dict[str, bool]) -> tuple[str, ...]:
    """隐藏的宠 id 元组（按 :data:`PET_IDS` 稳定顺序）。"""
    return tuple(pet_id for pet_id in PET_IDS
                 if not bool(visibility.get(pet_id, True)))


def _write(config_dir: Path | str, updates: dict[str, bool]) -> dict[str, bool]:
    """锁内合并写：只接受合法角色 id 与布尔值，写完全表读回并归一。"""
    path = visibility_path(config_dir)
    valid = {key: bool(value) for key, value in updates.items()
             if key in PET_IDS and isinstance(value, bool)}

    def mutate(current: dict) -> dict:
        working = dict(current)
        for pet_id in PET_IDS:
            if pet_id not in working or not isinstance(working[pet_id], bool):
                working[pet_id] = True
        working.update(valid)
        return working

    try:
        written = locked_update_json(
            path, mutate, on_broken="replace",
            default_factory=lambda: {pet_id: True for pet_id in PET_IDS})
    except ConfigWriteError:
        logger.warning("桌宠显隐状态写入失败，运行态本次不同步", exc_info=True)
        return read_visibility(config_dir)
    return {
        pet_id: written[pet_id] if isinstance(written.get(pet_id), bool) else True
        for pet_id in PET_IDS
    }


def set_pet_visible(config_dir: Path | str, pet_id: str,
                    visible: bool) -> dict[str, bool]:
    """把一只宠的显隐合并进共享状态，返回写后的全表。

    非法角色 id（不是三只之一）是 no-op：避免别的进程写坏键把岛的段序搅乱。
    """
    if pet_id not in PET_IDS:
        return read_visibility(config_dir)
    return _write(config_dir, {pet_id: bool(visible)})


def set_all_visible(config_dir: Path | str) -> dict[str, bool]:
    """一键全部显示（岛上「全部显示」段的落点）。"""
    return _write(config_dir, {pet_id: True for pet_id in PET_IDS})


def register_pet(config_dir: Path | str, pet_id: str) -> dict[str, bool]:
    """进程启动时登记自己的角色：只在缺键/坏值时补 True，不动别人已写的状态。

    这一步让「只开了一只宠」的场合也有完整三键表；重复调用是幂等的，且不会把
    另一进程刚写下的 false 覆盖回 true（那就是经典的「启动覆盖」竞态）。
    """
    path = visibility_path(config_dir)
    if not path.exists():
        return _write(config_dir, {})
    current = read_visibility(config_dir)
    raw, status = read_json_dict(path)
    if status == "ok" and isinstance(raw, dict) and isinstance(raw.get(pet_id), bool):
        return current
    return _write(config_dir, {pet_id: True})
