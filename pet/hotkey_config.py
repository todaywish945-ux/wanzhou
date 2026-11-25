# -*- coding: utf-8 -*-
"""全局快捷键的**唯一真源**：配置目录下的 ``config.json``。

三只桌宠是三个独立进程，各自读 ``config-角色X.json``；而独立设置进程把
「进程级」设置写进主配置 ``config.json``。热键服务过去读的是本进程那份实例
配置，于是用户在设置页绑了键、盘上主配置也有值，主进程却拿到空串——按下去
毫无反应。这里统一收口：

- :func:`read_global_bindings` —— 从主配置读三个热键键；**键存在即生效**
  （包括显式空串 = 用户主动解绑），没写过的键回落调用方给的旧值。
- :func:`write_global_bindings` —— 只改主配置里的这三个顶层键，带目录写锁，
  不碰同一份文件里的其他设置。

只依赖标准库 + 同包纯文本口径，不导入 Qt / ctypes，便于单测。
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import hotkey_spec
from .config_write_lock import locked_update_json, read_json_dict

logger = logging.getLogger(__name__)

#: 三个动作的配置键（与 pet/hotkeys.py::ACTIONS 的 value 一致；此处不反过来
#: 导入 hotkeys，避免 hotkeys → hotkey_spec → 本模块的循环）。
GLOBAL_KEYS = (
    "hotkey_open_chat",
    "hotkey_look_screen",
    "hotkey_screen_capture",
)

MASTER_CONFIG_NAME = "config.json"


def master_config_path(config_dir: Path | str) -> Path:
    """主配置文件路径（没有实例后缀的那一份）。"""
    return Path(config_dir) / MASTER_CONFIG_NAME


def read_global_bindings(config_dir: Path | str, fallback: dict | None = None) -> dict[str, str]:
    """读主配置里的热键绑定。

    ``fallback`` 是调用方（实例配置）的现值；主配置里**出现过**的键以主配置
    为准，没出现的键才用 fallback——这样老版本把热键写进实例配置的值仍能被
    读到，而用户在主配置里显式清空也能真正解绑。
    """
    result = {key: str((fallback or {}).get(key) or "") for key in GLOBAL_KEYS}
    path = master_config_path(config_dir)
    data, status = read_json_dict(path)
    if status != "ok" or not isinstance(data, dict):
        if status not in ("missing", "ok"):
            logger.warning("读取主配置热键失败（%s）：%s", status, path)
        return result
    for key in GLOBAL_KEYS:
        if key in data:
            result[key] = hotkey_spec.normalize(data.get(key))
    return result


def write_global_bindings(config_dir: Path | str, values: dict) -> bool:
    """把三个热键写进主配置（锁内重读→合并→原子写）。返回是否成功。"""
    path = master_config_path(config_dir)
    normalized = {key: hotkey_spec.normalize((values or {}).get(key)) for key in GLOBAL_KEYS}

    def _mutate(current: dict) -> dict:
        merged = dict(current)
        for key, value in normalized.items():
            merged[key] = value
        return merged

    try:
        locked_update_json(path, _mutate)
    except Exception:
        logger.warning("写主配置热键失败：%s", path, exc_info=True)
        return False
    return True
