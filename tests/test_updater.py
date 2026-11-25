# -*- coding: utf-8 -*-
"""检查更新模块测试。"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

from pet import updater


def _ns_shim(real, **overrides):
    """模块命名空间垫片：显式给出的成员覆盖，其余全部转发给真模块。

    用法是 ``monkeypatch.setattr(updater, 'os', _ns_shim(os, name='nt'))``——只换
    **被测模块里那个名字的绑定**。若写成 ``setattr(updater.os, 'name', …)``，改的
    其实是**全局** os 模块：pathlib 的平台分派只看全局 ``os.name``，窗口期里 pytest
    生成失败报告时会抛 ``NotImplementedError: cannot instantiate …Path``，整场
    INTERNALERROR。转发而不是只给 ``name``，是因为同一窗口里被测模块的其它 ``os``
    成员（``PathLike`` / ``environ`` …）仍要能用。
    """
    class _Shim(SimpleNamespace):
        def __getattr__(self, item):
            return getattr(real, item)

    return _Shim(**overrides)


def test_version_parts_and_is_newer():
    assert updater.version_parts("v3.0.1") == [3, 0, 1]
    assert updater.version_parts("3.0.0") == [3, 0, 0]
    assert updater.version_parts("v10.2") > updater.version_parts("v9.9.9")
    assert updater.version_parts("v3.0.0-beta") == [3, 0, 0]
    assert updater.is_newer("v3.0.1", "3.0.0") is True
    assert updater.is_newer("v3.0.0", "3.0.0") is False
    assert updater.is_newer("v2.9", "3.0.0") is False


def test_latest_release_parses_github_api(monkeypatch):
    import io

    def fake_ok(*args, **kwargs):
        body = json.dumps({
            "tag_name": "v3.0.1",
            "html_url": "https://github.com/x/releases",
            "body": "release notes",
            "assets": [
                {"name": "a-setup.exe", "browser_download_url": "https://dl/a-setup.exe"},
            ],
        }).encode()
        return io.BytesIO(body)

    monkeypatch.setattr(updater, "trusted_urlopen", fake_ok)
    release = updater.latest_release()
    assert release["version"] == "3.0.1"  # v 前缀被剥离
    assert release["notes"] == "release notes"
    assert release["assets"]["a-setup.exe"] == "https://dl/a-setup.exe"


def test_latest_release_falls_back_to_update_json(monkeypatch):
    """静态清单命中即返回，不再打 GitHub API。"""
    import io
    import urllib.error

    calls = []

    def fake_urlopen(request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        calls.append(url)
        if url == updater.RELEASE_API:
            raise urllib.error.URLError("blocked")
        # update.json 镜像
        body = json.dumps({
            "version": "3.0.1",
            "html_url": "https://github.com/x/releases",
            "notes": "cdn notes",
            "assets": {"a-setup.exe": "https://cdn/a-setup.exe"},
        }).encode()
        return io.BytesIO(body)

    monkeypatch.setattr(updater, "trusted_urlopen", fake_urlopen)
    release = updater.latest_release()
    assert release is not None
    assert release["version"] == "3.0.1"
    assert release["notes"] == "cdn notes"
    assert release["assets"]["a-setup.exe"] == "https://cdn/a-setup.exe"
    # 清单是真源：第一条命中就直接返回，GitHub API 根本不会被问。
    assert calls[0] == updater._UPDATE_JSON_URLS[0]
    assert updater.RELEASE_API not in calls


def test_manifest_wins_over_legacy_github_tags(monkeypatch):
    """仓库里遗留的上游 v4.4.x Release 不能把 1.00 用户骗去"升级"。"""
    import io

    calls = []

    def fake_urlopen(request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        calls.append(url)
        if url == updater.RELEASE_API:
            body = json.dumps({
                "tag_name": "v4.4.1",
                "html_url": "https://github.com/todaywish945-ux/wanzhou/releases/tag/v4.4.1",
                "body": "上游遗留 tag",
                "assets": [],
            }).encode()
        else:
            body = json.dumps({"version": "1.01", "notes": "本次真版本"}).encode()
        return io.BytesIO(body)

    monkeypatch.setattr(updater, "trusted_urlopen", fake_urlopen)
    release = updater.latest_release()
    assert release["version"] == "1.01"
    assert release["notes"] == "本次真版本"
    assert calls[-1] != updater.RELEASE_API  # API 根本没被问


def test_auto_check_state_is_deduped_and_cooldown(tmp_path):
    now = 1_000_000.0
    assert updater.auto_check_due(tmp_path, now=now) is True
    updater.mark_auto_check(tmp_path, now=now)
    assert updater.auto_check_due(tmp_path, now=now + 60) is False
    assert updater.auto_check_due(
        tmp_path, now=now + updater.AUTO_CHECK_INTERVAL_SECONDS) is True

    assert updater.should_notify_update(tmp_path, "1.01", now=now) is True
    updater.mark_update_notified(tmp_path, "1.01", now=now)
    assert updater.should_notify_update(tmp_path, "1.01", now=now + 60) is False
    assert updater.should_notify_update(tmp_path, "1.02", now=now + 60) is True


def test_auto_check_state_survives_corruption(tmp_path):
    state = updater.auto_check_state_path(tmp_path)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{broken", encoding="utf-8")
    assert updater.auto_check_due(tmp_path) is True
    updater.mark_auto_check(tmp_path)
    assert updater.auto_check_due(tmp_path, now=1_000_000) is False


def test_auto_check_can_be_disabled_via_master_config(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"auto_check_update": False}), encoding="utf-8")
    assert updater.auto_check_enabled(tmp_path) is False
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert updater.auto_check_enabled(tmp_path) is True


def test_make_update_manifest_writes_baidu_release_fields(tmp_path):
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[1] / "scripts" / "make_update_manifest.py"
    archive = tmp_path / "wanzhou-1.01-source.zip"
    archive.write_bytes(b"source-zip")
    manifest = tmp_path / "update.json"
    completed = subprocess.run(
        [sys.executable, str(script), "--version", "1.01", "--notes", "新版说明",
         "--download-url", "https://pan.baidu.com/s/abc123", "--download-code", "wz26",
         "--archive", str(archive), "--manifest", str(manifest)],
        capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["version"] == "1.01"
    assert data["download_url"] == "https://pan.baidu.com/s/abc123"
    assert data["download_code"] == "wz26"
    assert data["assets"]["wanzhou-1.01-source.zip"]["size"] == len(b"source-zip")
    assert len(data["assets"]["wanzhou-1.01-source.zip"]["sha256"]) == 64


def test_latest_release_all_sources_fail(monkeypatch):
    import urllib.error

    def fake_fail(*args, **kwargs):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(updater, "trusted_urlopen", fake_fail)
    assert updater.latest_release() is None


def test_config_persists_auto_hide(tmp_path):
    """全屏自动隐藏开关必须能持久化（回归：_load 白名单漏键）。"""
    from pet.config import Config

    cfg = Config(tmp_path)
    assert cfg.get("auto_hide_fullscreen", True) is True  # 默认开启
    cfg.set("auto_hide_fullscreen", False)
    cfg.save()

    reloaded = Config(tmp_path)
    assert reloaded.get("auto_hide_fullscreen", True) is False


def test_config_persists_click_behavior_keys(tmp_path):
    """点击行为（自言自语）与音效开关持久化。

    两键都是**每宠键**：真值在 ``config-slot-0.json``，生产里由 slot0 的路由视图读写。
    """
    from pet.config import Config
    from pet.settings_slot_config import route_settings_config

    def slot0():
        return route_settings_config(Config(base=tmp_path, instance_id="slot-0"))

    cfg = slot0()
    cfg.set("click_sound_enabled", False)
    cfg.set("click_show_self_talk", True)
    assert cfg.save() is True

    reloaded = slot0()
    assert reloaded.get("click_sound_enabled", True) is False
    assert reloaded.get("click_show_self_talk", False) is True



def test_structured_manifest_keeps_mirrors_and_integrity_fields(monkeypatch):
    import io

    def fake_ok(*args, **kwargs):
        body = json.dumps({
            "version": "4.3.0",
            "assets": {
                "dsh-pet-standalone-webm-chat-setup.exe": {
                    "fileName": "dsh-pet-standalone-webm-chat-setup.exe",
                    "urls": [
                        "https://github.com/todaywish945-ux/wanzhou/releases/download/v4.3.0/a.exe",
                        "https://cdn.jsdelivr.net/gh/todaywish945-ux/wanzhou@v4.3.0/a.exe",
                    ],
                    "size": 123,
                    "sha256": "A" * 64,
                    "platform": "windows",
                    "kind": "installer",
                },
            },
        }).encode()
        return io.BytesIO(body)

    monkeypatch.setattr(updater, "trusted_urlopen", fake_ok)
    release = updater.latest_release()
    detail = release["asset_details"]["dsh-pet-standalone-webm-chat-setup.exe"]
    assert detail["urls"][1].startswith("https://cdn.jsdelivr.net")
    assert detail["size"] == 123
    assert detail["sha256"] == "a" * 64


def test_download_asset_verifies_size_and_sha256(tmp_path, monkeypatch):
    import hashlib

    payload = b"installer-payload"
    digest = hashlib.sha256(payload).hexdigest()

    class Response:
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size=-1):
            nonlocal payload
            chunk, payload = payload, b""
            return chunk

    monkeypatch.setattr(
        updater,
        "trusted_urlopen",
        lambda *args, **kwargs: Response(),
    )
    path = updater.download_asset(
        {
            "name": "dsh-pet-standalone-webm-chat-setup.exe",
            "urls": ["https://github.com/todaywish945-ux/wanzhou/releases/download/v4.3.0/a.exe"],
            "size": len(b"installer-payload"),
            "sha256": digest,
        },
        tmp_path,
    )
    assert path.read_bytes() == b"installer-payload"


def test_download_asset_rejects_untrusted_origin(tmp_path):
    import pytest

    with pytest.raises(RuntimeError, match="untrusted URL"):
        updater.download_asset(
            {"name": "a.exe", "urls": ["http://evil.example/a.exe"]},
            tmp_path,
        )


def test_select_windows_installer_supports_legacy_and_structured_assets(monkeypatch):
    monkeypatch.setattr(updater, "os", _ns_shim(os, name="nt"))
    release = {
        "assets": {"dsh-pet-standalone-webm-setup.exe": "https://github.com/todaywish945-ux/wanzhou/releases/download/v4.3.0/a.exe"},
        "asset_details": {},
    }
    asset = updater.select_windows_installer(release, include_chat=False)
    assert asset["name"] == "dsh-pet-standalone-webm-setup.exe"
    assert asset["urls"]
