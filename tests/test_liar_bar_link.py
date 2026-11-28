# -*- coding: utf-8 -*-
"""骗子酒馆 ↔ 桌宠 联动事件路径契约（读侧 game_link / 写侧 liar_game）。

回归（v1.04）：游戏写侧曾把 ``联动事件.json`` 落在「骗子酒馆 的同级晚昼桌宠
目录」——源码开发恰好可用；打包后 ``__file__`` 在 ``liar-game\\_internal``，
按旧拼法得到的目录不存在，写盘 FileNotFoundError 被 ``except OSError`` 静默
吞掉，桌宠永远收不到入座事件（实测「游戏启动桌宠不就座」）。两端契约统一为
``%APPDATA%/wanzhou-pet/联动事件.json``，这里钉死两侧。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from pet.game_link import _EVENT_FILENAME, preferred_event_file

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GAME_DIR = _REPO_ROOT / "骗子酒馆"


def _appdata(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path / "wanzhou-pet"


def test_reader_prefers_appdata_file(tmp_path, monkeypatch):
    pet_root = _appdata(tmp_path, monkeypatch)
    pet_root.mkdir(parents=True)
    (pet_root / _EVENT_FILENAME).write_text('{"ts": 1}', encoding="utf-8")
    assert preferred_event_file() == pet_root / _EVENT_FILENAME


def test_reader_falls_back_to_legacy_repo_root(tmp_path, monkeypatch):
    """APPDATA 没有事件文件、仓库根有 → 读仓库根（源码开发期兼容）。"""
    _appdata(tmp_path, monkeypatch)
    from pet import game_link

    legacy = tmp_path / "legacy-root" / _EVENT_FILENAME
    legacy.parent.mkdir()
    legacy.write_text('{"ts": 0}', encoding="utf-8")
    monkeypatch.setattr(game_link, "_LEGACY_EVENT_FILE", legacy)
    assert preferred_event_file() == legacy


def test_reader_returns_appdata_candidate_when_missing(tmp_path, monkeypatch):
    """两处都没有：仍返回 APPDATA 候选（读失败 = 没有事件，语义一致）。"""
    pet_root = _appdata(tmp_path, monkeypatch)
    from pet import game_link

    missing_legacy = tmp_path / "nothing-here" / _EVENT_FILENAME
    monkeypatch.setattr(game_link, "_LEGACY_EVENT_FILE", missing_legacy)
    assert preferred_event_file() == pet_root / _EVENT_FILENAME


def test_game_side_writes_appdata_and_reader_sees_it(tmp_path, monkeypatch):
    """写侧（骗子酒馆，PyQt6）落盘 APPDATA 后，读侧在同一位置拿到事件。"""
    pytest.importorskip("PyQt6")
    import importlib

    pet_root = _appdata(tmp_path, monkeypatch)
    assert _GAME_DIR.is_dir(), f"找不到骗子酒馆目录：{_GAME_DIR}"
    sys.path.insert(0, str(_GAME_DIR))
    try:
        liar_game = importlib.import_module("liar_game")
        assert liar_game.EVENT_FILE == str(pet_root / _EVENT_FILENAME)
        liar_game.notify_pets([
            {"char": "角色A", "move": {"x": 10, "y": 20}, "emotion": "待机"},
        ])
    finally:
        sys.path.remove(str(_GAME_DIR))

    assert (pet_root / _EVENT_FILENAME).is_file()
    data = json.loads((pet_root / _EVENT_FILENAME).read_text(encoding="utf-8"))
    assert data["events"][0]["move"] == {"x": 10, "y": 20}
    # 读侧拿到的就是写侧刚落的这份
    assert preferred_event_file() == pet_root / _EVENT_FILENAME
