# -*- coding: utf-8 -*-
"""三开下快捷启动配置桥接：主配置 → 实例配置。"""
from __future__ import annotations


def test_sync_quick_launch_from_master(tmp_path, monkeypatch):
    from pet.config import Config
    from pet.app import AppShell

    # 隔离到 tmp：monkeypatch Config 默认 base 不方便，这里直接验证方法语义——
    # 用真实 config 目录会让测试写用户配置，故用最小 stub 覆盖 Config 构造。
    master_apps = [
        {"name": "默认浏览器", "path": "", "kind": "default_browser"},
        {"name": "B站", "path": "https://www.bilibili.com", "kind": "url"},
    ]

    class FakeMaster:
        def get(self, key, default=None):
            return master_apps if key == "quick_launch_apps" else default

    class FakeOwn:
        instance_id = "角色A"
        dir = tmp_path

        def __init__(self):
            self.data = {"quick_launch_apps": [master_apps[0]]}
            self.saved = 0

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set(self, key, value):
            self.data[key] = value

        def save(self):
            self.saved += 1
            return True

    own = FakeOwn()
    monkeypatch.setattr(
        "pet.app.Config", lambda base=None, instance_id="": FakeMaster()
    )

    class Stub:
        config = own

    stub = Stub()
    assert AppShell._sync_quick_launch_from_master(stub) is True
    assert own.data["quick_launch_apps"] == master_apps
    assert own.saved == 1
    # 二次调用 no-op（防止 watcher 循环写盘）
    assert AppShell._sync_quick_launch_from_master(stub) is False
    assert own.saved == 1
