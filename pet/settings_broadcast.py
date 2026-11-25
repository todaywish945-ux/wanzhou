# -*- coding: utf-8 -*-
"""把当前桌宠的所有设置一键应用到其他桌宠（多开分槽架构）。

三只挽昼是独立进程，各自一份 ``config-<instance_id>.json``。设置页点「应用到
其他桌宠」时，读当前实例的配置，把**设置类**顶层键整份写进其他桌宠的配置文件；
每宠自己的身份/位置/角色档案等键保留不动（否则三只会变成同一角色、挤在一处）。

写盘走目录级跨进程锁（``config_write_lock.locked_update_json``）——目标桌宠的
配置 watcher 检测到文件变化会自行重载，无需重启。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config_write_lock import ConfigWriteError, locked_update_json, read_json_dict

logger = logging.getLogger(__name__)

# 每宠独有、绝不能被"应用设置"覆盖的键：身份 / 位置 / 朝向 / 角色数据 / 运行状态。
# 其余顶层键（外观、行为、声音、AI、快捷键……）全部同步。
_PET_SPECIFIC_KEYS: frozenset[str] = frozenset({
    "character",            # 角色身份：不能把林德薇恩变成德蕾琪娜
    "rx", "ry", "screen_name", "facing",  # 位置/朝向：不能让三只挤在一起
    "character_aliases", "character_profiles",  # 每宠角色档案
    # 台词真源已在全局库 self_talk_texts.json（按角色索引、统一管理）；每宠 config
    # 里的这个键只是兼容回退，绝不能被「应用设置」整份覆盖成一样。
    "self_talk_texts",
    "dialogue_last_scope",  # 运行状态
    "user_customized",      # 各槽是否自定义过
    "version",              # 配置版本（各自迁移状态）
    "instance_id",
})

__all__ = ["apply_settings_to_other_pets", "settings_source_snapshot"]


def settings_source_snapshot(config_dir: Path | str, source_instance_id: str) -> dict[str, Any]:
    """读源实例配置，返回可同步的顶层键快照（已剔除每宠独有键）。"""
    root = Path(config_dir)
    source_path = root / (f"config-{source_instance_id}.json" if source_instance_id else "config.json")
    data, status = read_json_dict(source_path)
    if status != "ok" or not data:
        logger.warning("读取源配置失败（%s），无法应用设置: %s", status, source_path)
        return {}
    return {k: v for k, v in data.items() if k not in _PET_SPECIFIC_KEYS}


def apply_settings_to_other_pets(
    config_dir: Path | str, source_instance_id: str,
) -> tuple[int, list[str]]:
    """把源实例的设置应用到其他所有桌宠。

    返回 ``(成功数, 失败说明列表)``。找不到其他实例配置时不算失败（单宠环境）。
    """
    root = Path(config_dir)
    source_name = f"config-{source_instance_id}.json" if source_instance_id else "config.json"
    targets = sorted(
        p for p in root.glob("config-*.json")
        if p.name != source_name and not p.name.startswith("config-slot-")
    )
    if not targets:
        return 0, []

    snapshot = settings_source_snapshot(root, source_instance_id)
    if not snapshot:
        return 0, ["无法读取当前桌宠配置，未应用（请先保存本宠设置）"]

    ok = 0
    failures: list[str] = []

    def _mutate(current: dict) -> dict:
        merged = dict(current)
        for key, value in snapshot.items():
            merged[key] = value  # 顶层整值替换，符合 locked_update_json 的合并语义
        return merged

    for path in targets:
        try:
            locked_update_json(path, _mutate)
            ok += 1
            logger.info("设置已应用到其他桌宠: %s", path.name)
        except (ConfigWriteError, OSError, ValueError) as exc:
            failures.append(f"{path.name}: {exc}")
            logger.warning("设置应用到 %s 失败: %s", path.name, exc)
    return ok, failures
