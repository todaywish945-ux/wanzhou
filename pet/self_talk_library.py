# -*- coding: utf-8 -*-
"""全局自言自语台词库——按角色索引、所有桌宠与设置页共享的一份数据。

**为什么要独立存储**：``self_talk_texts`` 原本是每宠配置键（``config-slot-N.json``），
于是「应用到其他桌宠」（``settings_broadcast``）会把它整份覆盖过去，把三只原本
各异的台词变成一样。台词按理是「每个角色一份、但任何设置页都能统一管理」的数据
（与 AI 记忆同款：数据独立、入口统一），所以搬到这个独立文件：

- 文件路径 ``<config_dir>/self_talk_texts.json``，**不叫** ``config-*.json``——广播的
  ``glob("config-*.json")`` 扫不到，从根上杜绝被「应用设置」覆盖。
- 结构 ``{"角色A": [...], "角色B": [...], "角色C": [...]}``，按角色索引；三只桌宠
  运行时各读自己角色的那份，设置页的台词管理对话框可切换查看/修改全部角色。
- 读写走目录级跨进程锁（``config_write_lock``），三进程 + 设置页并发不丢更新。

读取侧缺角色/缺文件时回退到出厂默认台词；首次访问会从旧的每宠配置
``config-slot-N.json`` 把台词迁移进来（一次性，迁移后本文件为唯一真源）。
"""
from __future__ import annotations

import logging
from pathlib import Path

from .config import DEFAULT_SELF_TALK_TEXTS
from .config_write_lock import ConfigWriteError, locked_update_json, read_json_dict
from .pet_visibility import PET_IDS

logger = logging.getLogger(__name__)

LIB_FILENAME = "self_talk_texts.json"

__all__ = [
    "LIB_FILENAME",
    "all_texts",
    "ensure_library",
    "library_path",
    "texts_for",
    "update_texts",
    "validate_texts",
]


def library_path(config_dir: Path | str) -> Path:
    return Path(config_dir) / LIB_FILENAME


def validate_texts(value) -> list[str]:
    """清洗一份台词：去空白/去重/每条截 120 字，与 config 的 _clean_self_talk_texts 同口径。"""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()[:120]
        if text and text not in out:
            out.append(text)
    return out


def _defaults() -> dict[str, list[str]]:
    return {cid: list(DEFAULT_SELF_TALK_TEXTS) for cid in PET_IDS}


def _migrate_from_pets(config_dir: Path) -> dict[str, list[str]]:
    """一次性迁移：从每宠 config-slot-N.json 读旧台词，按角色 id 对号入座。

    slot 与角色的对应由启动脚本钉死（角色A=slot1，B=2，C=3）。读到的每份经
    validate_texts 清洗；某角色缺档/无台词时留空，由 ``texts_for`` 回退默认。
    """
    result: dict[str, list[str]] = {}
    for slot, cid in enumerate(PET_IDS, start=1):
        path = config_dir / f"config-slot-{slot}.json"
        data, status = read_json_dict(path)
        if status == "ok" and data:
            cleaned = validate_texts(data.get("self_talk_texts"))
            if cleaned:
                result[cid] = cleaned
    return result


def ensure_library(config_dir: Path | str) -> None:
    """确保台词库存在且每个角色都有条目；首次从旧每宠配置迁移一次。

    幂等：已有文件只补齐缺失角色，不覆盖用户已有台词。
    """
    target = library_path(config_dir)
    config_dir = Path(config_dir)

    def _mutate(current: dict) -> dict:
        out = dict(current)
        missing = [cid for cid in PET_IDS if cid not in out]
        if missing:
            migrated = _migrate_from_pets(config_dir)
            for cid in missing:
                out[cid] = validate_texts(migrated.get(cid)) or list(DEFAULT_SELF_TALK_TEXTS)
        # 丢掉非角色键（防脏数据），并补齐清洗
        return {cid: validate_texts(out.get(cid)) or list(DEFAULT_SELF_TALK_TEXTS)
                for cid in PET_IDS}

    try:
        # default_factory 必须返回空 dict：这样首次建库时 _mutate 收到的 current 为空，
        # missing = 全部角色 → 触发从旧每宠配置迁移。若这里给 _defaults()，角色键
        # 齐全反而不迁移，用户上一轮配好的三套台词会被出厂默认覆盖。
        locked_update_json(target, _mutate, on_broken="replace", default_factory=dict)
    except ConfigWriteError:
        logger.warning("台词库写入失败，读取侧将回退默认台词: %s", target)


def all_texts(config_dir: Path | str) -> dict[str, list[str]]:
    """返回全部角色台词 ``{角色id: [台词...]}``（读前先确保库存在/迁移）。"""
    ensure_library(config_dir)
    data, status = read_json_dict(library_path(config_dir))
    if status != "ok" or not data:
        return _defaults()
    return {cid: validate_texts(data.get(cid)) or list(DEFAULT_SELF_TALK_TEXTS)
            for cid in PET_IDS}


def texts_for(config_dir: Path | str, character_id: str) -> list[str]:
    """读某个角色的台词；缺档/缺角色回退出厂默认。"""
    ensure_library(config_dir)
    data, status = read_json_dict(library_path(config_dir))
    if status == "ok" and data:
        cleaned = validate_texts(data.get(str(character_id)))
        if cleaned:
            return cleaned
    return list(DEFAULT_SELF_TALK_TEXTS)


def update_texts(config_dir: Path | str, character_id: str, texts) -> list[str]:
    """写某个角色的台词（只替换该角色，其他角色不动）；返回写下去的清洗结果。"""
    cid = str(character_id)
    if cid not in PET_IDS:
        raise ValueError(f"未知角色 id: {cid}")
    target = library_path(config_dir)
    cleaned = validate_texts(texts) or list(DEFAULT_SELF_TALK_TEXTS)
    config_dir = Path(config_dir)
    # 先确保库已建立/迁移，否则库不存在时 locked_update_json 用 default_factory
    # 起步，会跳过其他角色的迁移数据、把它们写成出厂默认。
    ensure_library(config_dir)

    def _mutate(current: dict) -> dict:
        out = dict(current)
        out[cid] = cleaned
        # 补齐其余角色，避免半初始化的库缺角色
        for other in PET_IDS:
            if other not in out:
                out[other] = list(DEFAULT_SELF_TALK_TEXTS)
        return out

    locked_update_json(target, _mutate, on_broken="replace", default_factory=_defaults)
    return cleaned
