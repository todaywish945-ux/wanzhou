# -*- coding: utf-8 -*-
"""出厂语音种子：只补用户缓存缺失的 wav，绝不覆盖用户重新生成过的。"""
from __future__ import annotations

import io
import wave

from pet.voice import seed


def _wav_bytes(seconds: float = 0.2) -> bytes:
    """造一个合法但极短的单声道 wav。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buf.getvalue()


def test_seed_copies_missing_wavs(tmp_path, monkeypatch):
    """种子目录有 2 个 wav、用户缓存为空 → 两个都落位。"""
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    for name in ("a.wav", "b.wav"):
        (seed_dir / name).write_bytes(_wav_bytes())
    monkeypatch.setattr(seed, "seed_dir", lambda: seed_dir)
    cfgdir = tmp_path / "APPDATA" / "wanzhou-pet"
    cfgdir.mkdir(parents=True)

    copied = seed.seed_voice_cache(cfgdir)

    assert copied == 2
    assert (cfgdir / "self_talk_voice" / "a.wav").is_file()
    assert (cfgdir / "self_talk_voice" / "b.wav").is_file()


def test_seed_never_overwrites_existing(tmp_path, monkeypatch):
    """用户缓存里已有同名 wav（重新生成过）→ 保持原内容不动。"""
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "a.wav").write_bytes(_wav_bytes())
    monkeypatch.setattr(seed, "seed_dir", lambda: seed_dir)
    cfgdir = tmp_path / "APPDATA" / "wanzhou-pet"
    cache = cfgdir / "self_talk_voice"
    cache.mkdir(parents=True)
    custom = b"RIFF-custom-user-regenerated"
    (cache / "a.wav").write_bytes(custom)

    copied = seed.seed_voice_cache(cfgdir)

    assert copied == 0
    assert (cache / "a.wav").read_bytes() == custom


def test_seed_no_source_is_noop(tmp_path, monkeypatch):
    """没有种子目录（老版本/精简包）→ 静默返回 0，不创建缓存目录。"""
    monkeypatch.setattr(seed, "seed_dir", lambda: None)
    cfgdir = tmp_path / "APPDATA" / "wanzhou-pet"
    cfgdir.mkdir(parents=True)
    assert seed.seed_voice_cache(cfgdir) == 0
    assert not (cfgdir / "self_talk_voice").exists()


def test_default_texts_are_per_role_and_distinct():
    """15 句出厂台词按角色分发，三角不重样——新用户建库不会三只说同样的话。"""
    from pet.config import DEFAULT_SELF_TALK_TEXTS_BY_ROLE

    groups = list(DEFAULT_SELF_TALK_TEXTS_BY_ROLE.values())
    assert len(groups) == 3
    assert all(len(g) == 5 for g in groups)
    assert all(len(set(g)) == len(g) for g in groups)
    assert not (set(groups[0]) & set(groups[1]))
    assert not (set(groups[0]) & set(groups[2]))
    assert not (set(groups[1]) & set(groups[2]))
