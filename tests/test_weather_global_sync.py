# -*- coding: utf-8 -*-
"""天气全局同步：主配置 → 实例（桥接）、实例 → 主配置（镜像）。"""
from __future__ import annotations

WEATHER = ("weather_enabled", "weather_city", "weather_city_list", "weather_city_codes")


def test_sync_weather_from_master(tmp_path, monkeypatch):
    """主配置有值则覆盖进实例；主配置为 None 的键不覆盖（保留实例默认值）。"""
    from pet.app import AppShell

    master_values = {
        "weather_enabled": True,
        "weather_city": "郑州",
        "weather_city_list": ["郑州", "开封"],
        "weather_city_codes": {"郑州": "101180101"},
        "weather_city_list": ["郑州", "开封"],
    }

    class FakeMaster:
        def get(self, key, default=None):
            return master_values.get(key, default)

    class FakeOwn:
        instance_id = "角色A"
        dir = tmp_path

        def __init__(self):
            self.data = {"weather_enabled": True, "weather_city": "开封",
                         "weather_city_list": ["开封"]}
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
        _WEATHER_GLOBAL_KEYS = WEATHER

    assert AppShell._sync_weather_from_master(Stub()) is True
    assert own.data["weather_city"] == "郑州"
    assert own.data["weather_city_list"] == ["郑州", "开封"]
    assert own.data["weather_city_codes"] == {"郑州": "101180101"}
    assert own.saved == 1
    assert AppShell._sync_weather_from_master(Stub()) is False  # 二次 no-op
    assert own.saved == 1


def test_sync_weather_skips_none_from_master(tmp_path, monkeypatch):
    """主配置未设置的键（None）不覆盖实例值。"""
    from pet.app import AppShell

    class FakeMaster:
        def get(self, key, default=None):
            return None  # 全部没设置

    class FakeOwn:
        instance_id = "角色A"
        dir = tmp_path

        def __init__(self):
            self.data = {"weather_city": "开封"}
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
        _WEATHER_GLOBAL_KEYS = WEATHER

    assert AppShell._sync_weather_from_master(Stub()) is False
    assert own.data["weather_city"] == "开封"
    assert own.saved == 0


def test_mirror_weather_to_master(tmp_path, monkeypatch):
    """实例配置（菜单改城市）镜像回主配置 config.json。"""
    from pet.weather import menu as menu_mod

    saved: dict = {}

    class FakeMaster:
        def __init__(self, base, instance_id):
            self.data = {"weather_city": "郑州", "weather_city_list": ["郑州"]}
            self.saved = 0

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set(self, key, value):
            self.data[key] = value

        def save(self):
            self.saved += 1
            saved["master"] = self
            return True

    captured = {}

    def fake_config(base=None, instance_id=""):
        obj = FakeMaster(base, instance_id)
        captured["obj"] = obj
        return obj

    monkeypatch.setattr("pet.config.Config", fake_config)

    class FakeCfg:
        instance_id = "角色A"
        dir = tmp_path

        def get(self, key, default=None):
            return {"weather_city": "开封", "weather_city_list": ["开封"],
                    "weather_city_codes": {"开封": "101180201"}}.get(key, default)

    menu_mod._mirror_weather_to_master(FakeCfg())
    obj = captured["obj"]
    assert obj.data["weather_city"] == "开封"
    assert obj.data["weather_city_list"] == ["开封"]
    assert obj.saved == 1


def test_mirror_skipped_for_master_config(tmp_path):
    """instance_id 为空（主配置本身）时不镜像，避免写自己。"""
    from pet.weather import menu as menu_mod

    class FakeCfg:
        instance_id = ""
        dir = tmp_path

        def get(self, key, default=None):
            return None

    # 不抛异常即可（_save 里判断 instance_id 为空就不调镜像）
    menu_mod._save(FakeCfg())
