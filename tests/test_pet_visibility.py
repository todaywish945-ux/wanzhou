# -*- coding: utf-8 -*-
"""三角色桌宠跨进程显隐状态：共享 JSON + 目录写锁的读/写/兜底契约。

纯逻辑测试，不碰 Qt。重点是三条纪律：
1. 键固定三只、缺键/坏值按「可见」兜底（安全侧：不把活着的宠报成隐藏）；
2. 写是锁内合并，绝不整表覆盖别的进程刚写下的 hidden；
3. 读函数是纯的，损坏文件不会被读操作改写。
"""
from __future__ import annotations

import json

from pet import pet_visibility as pv


def test_pet_ids_are_exactly_three():
    assert pv.PET_IDS == ("角色A", "角色B", "角色C")


def test_read_missing_is_all_visible(tmp_path):
    assert pv.read_visibility(tmp_path) == {
        "角色A": True, "角色B": True, "角色C": True}


def test_read_bad_values_fall_back_to_visible(tmp_path):
    path = pv.visibility_path(tmp_path)
    path.write_text(json.dumps({
        "角色A": False, "角色B": "false", "角色C": 0, "extra": False,
    }), encoding="utf-8")
    got = pv.read_visibility(tmp_path)
    assert got == {"角色A": False, "角色B": True, "角色C": True}
    assert "extra" not in got  # 额外键不进岛的段序


def test_read_corrupt_file_is_safe_and_read_only(tmp_path):
    path = pv.visibility_path(tmp_path)
    path.write_text("{not json", encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    assert pv.read_visibility(tmp_path) == {
        "角色A": True, "角色B": True, "角色C": True}
    assert path.read_text(encoding="utf-8") == before  # 读不改文件


def test_set_pet_visible_merges_other_pets_state(tmp_path):
    pv.set_pet_visible(tmp_path, "角色B", False)
    pv.set_pet_visible(tmp_path, "角色C", False)
    got = pv.set_pet_visible(tmp_path, "角色A", False)
    assert got == {"角色A": False, "角色B": False, "角色C": False}
    # 恢复其中一只，其余两只的隐藏不被覆盖
    got = pv.set_pet_visible(tmp_path, "角色B", True)
    assert got == {"角色A": False, "角色B": True, "角色C": False}


def test_set_all_visible(tmp_path):
    pv.set_pet_visible(tmp_path, "角色A", False)
    pv.set_pet_visible(tmp_path, "角色B", False)
    pv.set_pet_visible(tmp_path, "角色C", False)
    assert pv.any_hidden(pv.read_visibility(tmp_path))
    got = pv.set_all_visible(tmp_path)
    assert got == {"角色A": True, "角色B": True, "角色C": True}
    assert not pv.any_hidden(got)


def test_invalid_pet_id_is_noop(tmp_path):
    pv.set_pet_visible(tmp_path, "角色B", False)
    got = pv.set_pet_visible(tmp_path, "角色D", True)
    assert got == {"角色A": True, "角色B": False, "角色C": True}


def test_register_pet_preserves_existing_hidden(tmp_path):
    pv.set_pet_visible(tmp_path, "角色A", False)
    got = pv.register_pet(tmp_path, "角色A")
    assert got["角色A"] is False  # 启动不抹掉已写下的隐藏意图
    # 缺文件的角色首次登记补 True
    assert pv.register_pet(tmp_path, "角色B")["角色B"] is True


def test_hidden_pet_ids_stable_order(tmp_path):
    pv.set_pet_visible(tmp_path, "角色C", False)
    pv.set_pet_visible(tmp_path, "角色A", False)
    got = pv.read_visibility(tmp_path)
    assert pv.hidden_pet_ids(got) == ("角色A", "角色C")
