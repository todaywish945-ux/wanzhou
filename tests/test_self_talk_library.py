# -*- coding: utf-8 -*-
"""全局台词：**固定池 + 勾选播报**（2026-11-28 起）。

台词音频全部由作者预先训练/录制放进包里，项目暂无实时合成能力——台词池锁定为
出厂台词，用户唯一可动的是"这句要不要播报"的勾选（``self_talk_disabled.json``，
缺省全勾选）。旧全局库（``self_talk_texts.json``）与每宠配置键保留在盘上但不再
被 ``texts_for`` 读取：编辑入口关闭，历史数据不静默删除，开放编辑前是死数据。
"""
import json

import pytest

from pet import self_talk_library as lib
from pet import settings_broadcast
from pet.pet_visibility import PET_IDS


@pytest.fixture
def cfgdir(tmp_path):
    return tmp_path


def _seed_old_pet_configs(cfgdir):
    """按旧每宠配置种三套台词——固定化之后它们不再影响播报名单。"""
    for slot, cid in enumerate(PET_IDS, start=1):
        cfgdir.joinpath(f"config-slot-{slot}.json").write_text(
            json.dumps({"character": cid, "self_talk_texts": [f"{cid} 台词"]},
                       ensure_ascii=False),
            encoding="utf-8",
        )


def test_library_file_is_not_a_config_file():
    """台词库文件名不以 config- 开头——广播的 glob 扫不到，从根上不被覆盖。"""
    assert not lib.LIB_FILENAME.startswith("config-")
    assert not lib.DISABLED_FILENAME.startswith("config-")
    assert "self_talk_texts" in settings_broadcast._PET_SPECIFIC_KEYS


def test_texts_for_returns_fixed_pool_regardless_of_legacy_files(cfgdir):
    """旧每宠配置/旧全局库写过的台词不再影响播报名单：固定池兜底一切。"""
    _seed_old_pet_configs(cfgdir)
    lib.update_texts(cfgdir, "角色A", ["德蕾琪娜专用"])
    lib.library_path(cfgdir).write_text(
        json.dumps({"角色A": ["库里的旧台词"]}, ensure_ascii=False), encoding="utf-8")
    for cid in PET_IDS:
        assert lib.texts_for(cfgdir, cid) == lib.DEFAULT_SELF_TALK_TEXTS_BY_ROLE[cid], (
            "固定台词池锁死：任何历史编辑数据都不能改变播报名单")


def test_fixed_pool_roles_are_independent(cfgdir):
    """固定池三角各异（角色A/B/C 各自的出厂台词），不串池。"""
    pools = {cid: lib.texts_for(cfgdir, cid) for cid in PET_IDS}
    assert len({tuple(texts) for texts in pools.values()}) == len(PET_IDS)
    for cid in PET_IDS:
        assert pools[cid] and pools[cid] == lib.DEFAULT_SELF_TALK_TEXTS_BY_ROLE[cid]


def test_disabled_texts_default_empty(cfgdir):
    """默认全部勾选：没写过勾选状态时禁用集为空。"""
    assert lib.disabled_texts_for(cfgdir, "角色A") == []
    assert lib.texts_for(cfgdir, "角色A") == lib.DEFAULT_SELF_TALK_TEXTS_BY_ROLE["角色A"]


def test_unchecked_line_is_filtered_out(cfgdir):
    """取消勾选的句子不再出现在播报名单，其余保持固定池顺序。"""
    pool = lib.DEFAULT_SELF_TALK_TEXTS_BY_ROLE["角色A"]
    first, second = pool[0], pool[1]
    lib.set_disabled_texts(cfgdir, "角色A", [first])
    assert lib.texts_for(cfgdir, "角色A") == [t for t in pool if t != first]
    # 取消勾选写盘即生效（独立文件，与旧库无关）
    assert lib.disabled_path(cfgdir).exists()


def test_set_disabled_ignores_lines_outside_fixed_pool(cfgdir):
    """台词池锁死：勾选状态只接受池内句子，池外文本一律丢弃（防脏数据）。"""
    lib.set_disabled_texts(cfgdir, "角色B", ["自己编的一句", "自己编的一句"])
    assert lib.disabled_texts_for(cfgdir, "角色B") == []


def test_disabled_roles_are_independent(cfgdir):
    """勾选状态按角色隔离：A 取消勾选不影响 B/C。"""
    first = lib.DEFAULT_SELF_TALK_TEXTS_BY_ROLE["角色A"][0]
    lib.set_disabled_texts(cfgdir, "角色A", [first])
    assert first in lib.disabled_texts_for(cfgdir, "角色A")
    assert lib.disabled_texts_for(cfgdir, "角色B") == []
    assert lib.disabled_texts_for(cfgdir, "角色C") == []


def test_corrupted_disabled_file_falls_back_to_all_checked(cfgdir):
    """勾选状态文件坏了 → 按全勾选处理，不许让台词消失。"""
    lib.disabled_path(cfgdir).write_text("{broken json", encoding="utf-8")
    assert lib.disabled_texts_for(cfgdir, "角色C") == []
    assert lib.texts_for(cfgdir, "角色C") == lib.DEFAULT_SELF_TALK_TEXTS_BY_ROLE["角色C"]


def test_all_texts_covers_every_role(cfgdir):
    """all_texts 兼容接口仍按角色全覆盖（历史调用方）。"""
    result = lib.all_texts(cfgdir)
    assert set(result) == set(PET_IDS)


def test_validate_texts_dedups_and_trims(cfgdir):
    assert lib.validate_texts(["  甲  ", "甲", "", "乙"]) == ["甲", "乙"]
