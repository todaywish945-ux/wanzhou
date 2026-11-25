# -*- coding: utf-8 -*-
"""收尾审计补丁的回归测试：会话路径穿越、JS 桥非法角色、内网 URL、畸形联动事件。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_session_store_rejects_traversal_ids_and_keeps_normal_ids(tmp_path):
    from pet.chat.models import ChatMessage
    from pet.chat.session_store import SessionStore

    store = SessionStore(tmp_path, "")
    evil = f"../{uuid.uuid4().hex}"
    session = store.create(evil, "p", "sys")
    session.messages.append(ChatMessage("user", "不该落盘"))
    assert store.save(session) is False
    assert store.load(evil) is None
    assert store.list(evil) == []
    assert store.delete(session) is False
    assert not (tmp_path.parent / f"{Path(evil).name}.json").exists()

    good = store.create("角色A", "p", "sys")
    good.messages.append(ChatMessage("user", "正常保存"))
    assert store.save(good) is True
    assert store.flush()
    loaded = store.load(good.session_id, "角色A")
    assert loaded is not None and loaded.messages[0].content == "正常保存"


def test_kk_bridge_open_session_rejects_unknown_character():
    from pet.chat.kk_web_window import KKWebWindow

    def must_not_run(cid):
        raise AssertionError(f"非法角色不应触碰会话仓库: {cid}")

    fake = SimpleNamespace(_store_for=must_not_run)
    KKWebWindow._open_session(fake, "../evil", "anything")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8080/admin",
    "http://localhost/secret",
    "http://[::1]/secret",
    "http://169.254.169.254/latest/meta-data/",
    "http://192.168.1.1/",
    "file:///C:/Windows/win.ini",
    "ftp://example.com/file",
])
def test_fetch_page_text_blocks_internal_and_non_http_urls(url, monkeypatch):
    from pet.chat import web_search

    def must_not_run(*args, **kwargs):
        raise AssertionError("内网/非 HTTP URL 不应发起网络请求")

    monkeypatch.setattr(web_search.urllib.request, "urlopen", must_not_run)
    monkeypatch.setattr(web_search.urllib.request.OpenerDirector, "open", must_not_run)
    with pytest.raises(web_search.WebSearchError):
        web_search.fetch_page_text(url)


def test_safe_redirect_handler_rechecks_target():
    from pet.chat.web_search import WebSearchError, _SafeRedirectHandler

    handler = _SafeRedirectHandler()
    req = SimpleNamespace(full_url="https://example.com/page")
    with pytest.raises(WebSearchError):
        handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/admin")


def test_fetch_page_text_uses_public_only_http_path(monkeypatch):
    from pet.chat import web_search

    seen = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return "<html><body>公开网页</body></html>", "text/html"

    monkeypatch.setattr(web_search, "_http_get", fake_get)
    text = web_search.fetch_page_text("https://example.com/page")
    assert "公开网页" in text
    assert seen.get("public_only") is True


def test_game_link_ignores_nan_timestamp_and_nonfinite_scale(tmp_path, monkeypatch):
    import math

    from pet.game_link import GameLink

    calls = []

    class Win:
        cfg = {"character": "角色A"}
        x = 0
        y = 0
        scale = 1.0

        def move(self, x, y):
            calls.append(("move", x, y))

        def change_scale(self, scale, persist=True):
            calls.append(("scale", scale, persist))

        def _save_position(self):
            calls.append(("save",))

    link = GameLink.__new__(GameLink)  # QObject 子类不能用 object.__new__
    link._ts = 0.0
    link._win = Win()
    path = tmp_path / "link.json"
    path.write_text(json.dumps({
        "ts": math.nan,
        "events": [{"char": "角色A", "move": {"x": -10, "y": 20, "scale": math.nan}}],
    }), encoding="utf-8")
    monkeypatch.setattr(link, "_event_file", lambda: path)
    link._poll()
    assert link._ts == 0.0
    assert calls == []
