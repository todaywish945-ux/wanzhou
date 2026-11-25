# -*- coding: utf-8 -*-
"""A 类全局键通用桥接：主配置 → 实例。人设/每宠/报时/待办不得被覆盖。"""
from __future__ import annotations


def _stub_and_patch(monkeypatch, tmp_path, master_values):
    from pet.app import AppShell

    class FakeMaster:
        def get(self, key, default=None):
            return master_values.get(key, default)

    class FakeOwn:
        instance_id = "角色A"
        dir = tmp_path

        def __init__(self):
            self.data = {}
            self.saved = 0

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set(self, key, value):
            self.data[key] = value

        def save(self):
            self.saved += 1
            return True

    own = FakeOwn()
    monkeypatch.setattr("pet.app.Config", lambda base=None, instance_id="": FakeMaster())

    class Stub:
        config = own
        _SHARED_GLOBAL_KEYS = AppShell._SHARED_GLOBAL_KEYS

    return Stub(), own


def test_syncs_shared_globals_and_skips_none(monkeypatch, tmp_path):
    from pet.app import AppShell

    master = {
        "quiet_minutes_default": 30,
        "network_info_menu_enabled": False,
        "context_menu_appearance": {"theme": "dark"},
        # master 没设的键（None）不该覆盖实例
    }
    stub, own = _stub_and_patch(monkeypatch, tmp_path, master)
    # 实例有个本地值，master 没设 → 应保留
    own.data["pet_opacity"] = 90

    assert AppShell._sync_shared_globals_from_master(stub) is True
    assert own.data["quiet_minutes_default"] == 30
    assert own.data["network_info_menu_enabled"] is False
    assert own.data["context_menu_appearance"] == {"theme": "dark"}
    assert own.data["pet_opacity"] == 90  # master None → 不覆盖
    assert own.saved == 1
    # 二次 no-op
    assert AppShell._sync_shared_globals_from_master(stub) is False
    assert own.saved == 1


def test_never_touches_pet_specific_keys():
    from pet.app import AppShell

    forbidden = {
        "character", "self_talk_texts", "dialogue_phrases", "dialogue_last_scope",
        "golden_spin_on_click", "voice_chime_enabled", "voice_chime_schedule",
        "reminders", "chat_follow_pet", "chat_always_on_top", "rx", "ry",
    }
    assert not (AppShell._SHARED_GLOBAL_KEYS & forbidden)
