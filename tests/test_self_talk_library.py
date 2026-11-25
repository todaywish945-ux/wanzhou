# -*- coding: utf-8 -*-
"""全局自言自语台词库：按角色隔离、统一管理、不被配置广播覆盖。"""
import json

import pytest

from pet import self_talk_library as lib
from pet import settings_broadcast
from pet.pet_visibility import PET_IDS


@pytest.fixture
def cfgdir(tmp_path):
    return tmp_path


def _seed_old_pet_configs(cfgdir):
    """按旧每宠配置种三套台词，验证首次迁移对号入座。"""
    for slot, cid in enumerate(PET_IDS, start=1):
        cfgdir.joinpath(f"config-slot-{slot}.json").write_text(
            json.dumps({"character": cid, "self_talk_texts": [f"{cid} 台词"]},
                       ensure_ascii=False),
            encoding="utf-8",
        )


def test_library_file_is_not_a_config_file():
    """台词库文件名不以 config- 开头——广播的 glob 扫不到，从根上不被覆盖。"""
    assert not lib.LIB_FILENAME.startswith("config-")
    assert "self_talk_texts" in settings_broadcast._PET_SPECIFIC_KEYS


def test_first_access_migrates_old_pet_configs(cfgdir):
    _seed_old_pet_configs(cfgdir)
    for slot, cid in enumerate(PET_IDS, start=1):
        assert lib.texts_for(cfgdir, cid) == [f"{cid} 台词"]
    assert lib.library_path(cfgdir).exists()


def test_roles_are_independent(cfgdir):
    _seed_old_pet_configs(cfgdir)
    lib.update_texts(cfgdir, "角色A", ["德蕾琪娜专用"])
    assert lib.texts_for(cfgdir, "角色A") == ["德蕾琪娜专用"]
    assert lib.texts_for(cfgdir, "角色B") == ["角色B 台词"]
    assert lib.texts_for(cfgdir, "角色C") == ["角色C 台词"]
    assert len({tuple(lib.texts_for(cfgdir, c)) for c in PET_IDS}) == 3


def test_all_texts_covers_every_role(cfgdir):
    _seed_old_pet_configs(cfgdir)
    result = lib.all_texts(cfgdir)
    assert set(result) == set(PET_IDS)


def test_empty_texts_falls_back_to_default(cfgdir):
    lib.update_texts(cfgdir, "角色B", [])
    assert lib.texts_for(cfgdir, "角色B")


def test_validate_texts_dedups_and_trims(cfgdir):
    assert lib.validate_texts(["  甲  ", "甲", "", "乙"]) == ["甲", "乙"]


def test_missing_roles_default_without_overwriting(cfgdir):
    """库里已有部分角色时，缺的补默认，不覆盖已存的。"""
    lib.library_path(cfgdir).write_text(
        json.dumps({"角色A": ["保留我"]}, ensure_ascii=False), encoding="utf-8")
    assert lib.texts_for(cfgdir, "角色A") == ["保留我"]
    assert lib.texts_for(cfgdir, "角色B")
