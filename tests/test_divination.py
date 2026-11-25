# -*- coding: utf-8 -*-
"""每日一签的回归用例。

三条硬不变量：**签库形状/文案格式**、**同一天必得同一支**（含跨进程）、
**一轮之内不重复**。跨进程那条是抓 `hash()` 随机化的——真踩过。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

import pytest

from pet import divination
from pet.divination.quotes import RAW_QUOTES

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


# ------------------------------------------------------------- 签库形状
def test_pool_has_48_quotes() -> None:
    assert len(divination.QUOTES) == 48
    assert len(RAW_QUOTES) == 48


def test_tier_counts_are_all_daily() -> None:
    """2026-11-23 起内容换成每日英文：吉凶档位取消，统一中性档。"""
    counts = {tier: sum(1 for q in divination.QUOTES if q.tier == tier) for tier in divination.TIERS}
    assert counts == {"每日一句": 48}


def test_ids_are_consecutive_and_append_only() -> None:
    """签号＝下标+1（配置里存的是号；扩签只追加、永不重排）。"""
    assert [q.id for q in divination.QUOTES] == list(range(1, 49))
    for idx, q in enumerate(divination.QUOTES):
        assert q.id == idx + 1
        assert divination.quote_by_id(q.id) is q


# ------------------------------------------------------------- 文案格式
def test_quote_format_contract() -> None:
    """每日英文：英文句非空、译文非空且以句号收尾、verses 弃用空元组。"""
    bad = []
    for q in divination.QUOTES:
        if not q.title.strip() or not any(c.isascii() and c.isalpha() for c in q.title):
            bad.append((q.id, "英文句无效", q.title))
        if q.verses != ():
            bad.append((q.id, "verses 应弃用为空", q.verses))
        if not q.reading.strip() or not q.reading.endswith("。"):
            bad.append((q.id, "中文翻译无效", q.reading))
    assert bad == [], bad


def test_titles_and_readings_are_unique() -> None:
    assert len({q.title for q in divination.QUOTES}) == 48
    assert len({q.reading for q in divination.QUOTES}) == 48


# ------------------------------------------------------------- 同一天同一支
def test_same_day_same_quote() -> None:
    day = _d("2026-10-16")
    assert len({divination.draw_for_day(day).id for _ in range(5)}) == 1


def test_draw_is_reproducible_across_calls_and_days() -> None:
    start = _d("2026-01-01")
    first = [divination.draw_for_day(start + dt.timedelta(days=i)).id for i in range(30)]
    second = [divination.draw_for_day(start + dt.timedelta(days=i)).id for i in range(30)]
    assert first == second


def test_draw_is_reproducible_across_processes() -> None:
    """**跨进程**也必须一致（专抓 `hash()` 随机化：同一天不能出不同的签）。"""
    script = (
        "import datetime as dt, json;"
        "from pet import divination;"
        "days=[dt.date(2026,10,16), dt.date(2026,1,1), dt.date(2027,3,20)];"
        "print(json.dumps([divination.draw_for_day(d).id for d in days]))"
    )
    outs = []
    for seed in ("0", "12345", "random"):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            env={"PYTHONHASHSEED": seed, "PATH": os.environ.get("PATH", "")},
        )
        assert proc.returncode == 0, proc.stderr
        outs.append(json.loads(proc.stdout.strip()))
    assert outs[0] == outs[1] == outs[2], outs


def test_days_are_not_all_the_same_quote() -> None:
    start = _d("2026-01-01")
    assert len({divination.draw_for_day(start + dt.timedelta(days=i)).id for i in range(60)}) > 10


# ------------------------------------------------------------- 权重与档位分布
def test_tier_probabilities_sum_to_one() -> None:
    probs = divination.tier_probabilities()
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    assert {k: round(v * 100) for k, v in probs.items()} == divination.TIER_WEIGHTS


def test_tier_distribution_matches_weights() -> None:
    """2000 天的档位频率应当贴着 4/18/56/22（不带排除时的纯分布）。"""
    start = _d("2026-01-01")
    counts = dict.fromkeys(divination.TIERS, 0)
    n = 2000
    for i in range(n):
        counts[divination.draw_for_day(start + dt.timedelta(days=i)).tier] += 1
    for tier, weight in divination.TIER_WEIGHTS.items():
        assert abs(counts[tier] / n - weight / 100) < 0.04, (tier, counts)


# ------------------------------------------------------------- 一轮不重复
def test_a_round_covers_all_48_without_repeat() -> None:
    """一轮 48 天恰好走完 48 支：一支不重、一支不漏，档位构成＝签库构成。"""
    drawn: list[int] = []
    day = _d("2026-01-01")
    walked = []
    for i in range(48):
        q = divination.draw_for_day(day + dt.timedelta(days=i), drawn)
        assert q.id not in drawn, (i, q)
        drawn.append(q.id)
        walked.append(q.id)
    assert sorted(walked) == list(range(1, 49))
    counts: dict[str, int] = {}
    for qid in walked:
        tier = divination.quote_by_id(qid).tier
        counts[tier] = counts.get(tier, 0) + 1
    assert counts == {"每日一句": 48}


def test_everything_drawn_behaves_like_a_fresh_round() -> None:
    day = _d("2026-10-16")
    all_ids = [q.id for q in divination.QUOTES]
    assert divination.draw_for_day(day, all_ids).id == divination.draw_for_day(day, []).id


def test_exclusion_does_change_the_result_within_a_tier() -> None:
    day = _d("2026-10-16")
    base = divination.draw_for_day(day)
    again = divination.draw_for_day(day, [base.id])
    assert again.id != base.id
    assert again.tier == base.tier


# ------------------------------------------------------------- 渲染三档
def test_bubble_is_two_lines() -> None:
    q = divination.QUOTES[0]
    head, reading = divination.bubble_lines(q)
    assert head == q.title
    assert reading == q.reading


def test_bubble_for_every_quote() -> None:
    for q in divination.QUOTES:
        head, reading = divination.bubble_lines(q)
        assert head == q.title
        assert reading == q.reading


def test_card_lines_carry_english_and_translation() -> None:
    q = divination.QUOTES[0]
    lines = divination.card_lines(q)
    assert lines == [q.title, q.reading]


def test_speech_text_has_the_ritual_shape() -> None:
    """播报：先英文句子，再中文翻译；**开头不带起手**「每日英文...」。"""
    q = divination.QUOTES[42]
    text = divination.speech_text(q)
    assert not text.startswith(divination.WAITING_TEXT)
    assert text == f"{q.title} {q.reading}"


def test_speech_text_for_every_quote() -> None:
    for q in divination.QUOTES:
        text = divination.speech_text(q)
        assert divination.WAITING_TEXT not in text
        assert all(line in text for line in q.verses)
        assert q.reading in text


# ------------------------------------------------------------- 边界
def test_unknown_id_returns_none() -> None:
    assert divination.quote_by_id(0) is None
    assert divination.quote_by_id(999) is None


@pytest.mark.parametrize("day", ["2024-02-29", "2026-12-31", "2027-01-01"])
def test_draw_survives_leap_and_year_boundaries(day: str) -> None:
    assert divination.draw_for_day(_d(day)).id in {q.id for q in divination.QUOTES}


# ------------------------------------------------------------- 配置清洗
def test_normalize_reads_flat_keys() -> None:
    cfg = divination.normalize_divination_config(
        {"divination_enabled": "no", "divination_speak": 1, "divination_hint": None})
    assert cfg == {"enabled": False, "speak": True, "hint": True}


def test_clean_state_drops_garbage() -> None:
    assert divination.clean_divination_state("nonsense") == {}
    cleaned = divination.clean_divination_state(
        {"date": "bad", "quote_id": "x", "drawn": ["1", "y", 2]})
    assert cleaned == {"drawn": [1, 2]}


def test_state_no_longer_carries_history() -> None:
    """签册已按她的决定删掉（B）——旧配置里遗留的 history 不再被读进来。"""
    cleaned = divination.clean_divination_state(
        {"date": "2026-10-16", "quote_id": 43, "drawn": [43],
         "history": {"2026-10-16": 43}})
    assert "history" not in cleaned
    assert cleaned == {"date": "2026-10-16", "quote_id": 43, "drawn": [43]}
