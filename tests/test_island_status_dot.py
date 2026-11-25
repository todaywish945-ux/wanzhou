# -*- coding: utf-8 -*-
"""灵动岛状态点：Agent 联动删除后只剩「空闲 / 宠物隐藏」两态。

旧版五态（工作/待确认/完成/错误）由 DSH 八态收敛驱动；数据源删除后，
2026-11-24 连同注入接口、声纳环与瞬态定时器一并移除。本文件只钉住
仍然成立的两态语义与「余额行已删」的结构约束。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.island.dynamic_island import DynamicIsland

_NEUTRAL = "#a0aabe"


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _island(tmp_path: Path, **overrides) -> DynamicIsland:
    """只留状态点的岛：内容层除状态点外零图元（像素断言的前提）。"""
    _qapp()
    cfg = Config(base=tmp_path)
    data = {
        "enabled": True, "show_icon": False, "show_name": False,
        "show_info": False, "show_status": True, "info_mode": "time",
        "style": "dark", "x": 400, "y": 300,
    }
    data.update(overrides)
    cfg.set("dynamic_island", data)
    return DynamicIsland(cfg)


def _content_image(island: DynamicIsland) -> QImage:
    return island._content_cache().toImage().convertToFormat(QImage.Format.Format_ARGB32)


def _has_opaque_pixel(image: QImage) -> bool:
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() >= 40:
                return True
    return False


def test_status_dot_two_states(tmp_path):
    island = _island(tmp_path)
    try:
        shape, color = island._status_dot_style()
        assert island._status_dot_state() == "idle"
        assert shape == "solid" and color.name() == _NEUTRAL
        island.set_pet_visible(False)
        shape, color = island._status_dot_style()
        assert island._status_dot_state() == "hidden"
        assert shape == "hollow" and color.name() == _NEUTRAL
    finally:
        island.close()


def test_hidden_card_text_has_no_dsh_wording(tmp_path):
    island = _island(tmp_path)
    try:
        island.set_pet_visible(False)
        assert island._card_status_text() == "桌宠已隐藏"
    finally:
        island.close()


def test_status_dot_off_config_draws_nothing(tmp_path):
    off = _island(tmp_path, show_status=False)
    on = _island(tmp_path / "on", show_status=True)
    try:
        assert off._visible_parts()[3] is False
        assert on._visible_parts()[3] is True
        # 内容层里只有状态点这一处差别：关掉后位图与开启态不同，且不再画出圆点。
        off_img = _content_image(off)
        on_img = _content_image(on)
        assert bytes(off_img.bits()) != bytes(on_img.bits())
    finally:
        off.close()
        on.close()


def test_balance_rows_removed_from_card(tmp_path):
    """余额/峰谷展示随 Agent 联动删除，卡片概览只剩状态行。"""
    island = _island(tmp_path)
    try:
        assert not hasattr(island, "_card_balance_label")
        assert not hasattr(island, "_card_tier_label")
        assert not hasattr(island, "set_balance_info")
        assert island._card_overview_height() > 0
    finally:
        island.close()
