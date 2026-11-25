# -*- coding: utf-8 -*-
"""情景记忆（照搬叶瞬光项目 memory.ts 的双卡 + 向量召回机制）。

- 衰减卡 ``memory.json``：每场对话静默后由 LLM 压成 1~2 句第三人称「事后回忆」，
  再用智谱 embedding-3 向量化。清晰度按 30 天半衰衰减；太老的自然想不起来，
  半新不旧的以「模糊印象」措辞带出；超出容量的旧回忆转入全量卡存档。
- 全量卡 ``memory-full.jsonl``：append-only，永不删除、永不进提示词。
- 每轮对话前把语义最相关、还没忘干净的旧回忆拼进 system prompt。

任何向量化失败都不阻塞（该条回忆仍存在，只是不参与语义召回）——与叶瞬光同口径。
"""
from __future__ import annotations

import json
import logging
import math
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .service import ChatService  # noqa: F401  (类型参照；不在此模块发请求)

logger = logging.getLogger(__name__)

MAX_EPISODES = 300
SIM_THRESHOLD = 0.38
#: embedding 不可用时的关键词包含率阈值（bigram 切法下自然语言重合低，放宽到命中1个核心词）
KEYWORD_THRESHOLD = 0.1
CLARITY_HALF_LIFE_DAYS = 30
FORGET_CLARITY = 0.1
FUZZY_CLARITY = 0.45
EMBED_MODEL = "embedding-3"
EMBED_TIMEOUT = 5.0

SUMMARY_SYSTEM = (
    "你是回忆整理器。把一段对话压缩成 1~2 句第三人称的「事后回忆」，聚焦："
    "用户说了什么重要的事、发生了什么、用户的情绪状态。不要寒暄和流水账。"
    "直接输出回忆文本，不要任何前缀或引号。"
)
RECALL_HEADER = (
    "\n\n【你回想起的更早的对话记忆（跨天回忆，自然带出，别机械复述，"
    "也别说\"我记着\"；标注了\"模糊\"的只当隐约印象，不确定就别说得笃定）】\n"
)


def clarity_of(episode: dict, now: float | None = None) -> float:
    """回忆清晰度：按记录时间距今天数半衰（纯推导，不落盘）。"""
    now = now if now is not None else time.time()
    days = max(0.0, (now - float(episode.get("ts", now))) / 86_400.0)
    return math.pow(0.5, days / CLARITY_HALF_LIFE_DAYS)


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = norm_a = norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if not norm_a or not norm_b:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class EpisodicMemory:
    """一只角色一套双卡情景记忆。路径 = <角色目录>/episodic-memory.json。"""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.full_path = self.path.with_name("memory-full.jsonl")

    def _load(self) -> list[dict]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("episodes"), list):
                return raw["episodes"]
        except (OSError, ValueError):
            pass
        return []

    def _save(self, episodes: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"episodes": episodes}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _append_full(self, entries: list[dict]) -> None:
        if not entries:
            return
        with self.full_path.open("a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    def add_episode(
        self, text: str, session_id: str = "", vec: list[float] | None = None,
    ) -> dict:
        """追加一条回忆（已向量化则带 vec），超容量转全量卡。"""
        text = str(text or "").strip()[:120]
        try:
            from .memory_recall import extract_keywords

            keywords = extract_keywords(text)
        except Exception:
            keywords = []
        episode = {
            "id": uuid.uuid4().hex[:8],
            "date": datetime.now().astimezone().strftime("%Y-%m-%d"),
            "text": text,
            "vec": vec,
            "keywords": keywords,  # embedding 不可用时的召回降级依据
            "ts": time.time(),
            "sessionId": session_id,
        }
        episodes = self._load()
        episodes.append(episode)
        overflow: list[dict] = []
        while len(episodes) > MAX_EPISODES:
            dropped = episodes.pop(0)
            overflow.append(dropped)
        self._append_full(overflow)
        self._save(episodes)
        return episode

    def recall(self, query: str, current_session_id: str = "", embed_fn=None) -> str:
        """语义召回：按相似度 × 清晰度取 top3，拼进 system prompt。

        优先用 embedding 向量余弦；embedding 不可用（如额度不足）时自动降级为
        关键词 Jaccard——保证召回在任何环境都能工作（叶瞬光原版无此降级）。
        """
        try:
            from .memory_recall import extract_keywords

            pool = [e for e in self._load() if e.get("sessionId") != current_session_id]
            if not pool:
                return ""
            picked: list[dict] = []
            qv = embed_fn(query) if (query and embed_fn is not None) else None
            now = time.time()
            scored = []
            for e in pool:
                clarity = clarity_of(e, now)
                if clarity < FORGET_CLARITY:
                    continue
                if qv and e.get("vec"):
                    score = cosine(qv, e["vec"])
                    threshold = SIM_THRESHOLD
                else:
                    # 降级：关键词包含率（query 的关键词有多少落在回忆里）。
                    # 不用 Jaccard：bigram 切法下自然语言问句与回忆措辞重合极低，
                    # Jaccard 几乎恒为 0；包含率对"问到咖啡→想起咖啡的事"更合理。
                    kw_q = set(extract_keywords(query))
                    kw_e = set(e.get("keywords") or extract_keywords(e.get("text", "")))
                    score = len(kw_q & kw_e) / len(kw_q) if kw_q else 0.0
                    threshold = KEYWORD_THRESHOLD
                if score >= threshold:
                    scored.append((score * clarity, e, clarity))
            scored.sort(key=lambda x: x[0], reverse=True)
            picked = [e for _, e, _ in scored[:3]]
            if not picked:
                return ""
            now = time.time()
            lines = []
            for e in picked:
                prefix = (
                    f"（{e.get('date', '')}，这段印象已有些模糊）"
                    if clarity_of(e, now) < FUZZY_CLARITY
                    else f"（{e.get('date', '')}）"
                )
                lines.append(prefix + str(e.get("text", "")))
            return RECALL_HEADER + "\n".join(lines)
        except Exception as exc:
            logger.warning("情景记忆召回失败（已静默）: %s", exc)
            return ""

    def all_episodes(self) -> list[dict]:
        return self._load()

    def remove(self, episode_id: str) -> bool:
        """删除一条情景回忆（按 id）；返回是否真的删掉了。"""
        episodes = self._load()
        kept = [e for e in episodes if str(e.get("id", "")) != str(episode_id)]
        if len(kept) == len(episodes):
            return False
        self._save(kept)
        return True

    def clear(self) -> int:
        """清空全部情景回忆；返回删除的条数。"""
        episodes = self._load()
        n = len(episodes)
        if n:
            self._save([])
        return n


# ---------------------------------------------------------------- 异步调度层
import threading
from datetime import datetime

_summary_timers: dict[str, threading.Timer] = {}
_summarized_up_to: dict[str, int] = {}
_summary_busy = False
_summary_lock = threading.Lock()


def embed_text(base_url: str, api_key: str, text: str) -> list[float] | None:
    """智谱 embedding-3 向量化；5 秒超时，失败返回 None（不阻塞主流程）。"""
    import urllib.request

    url = base_url.rstrip("/") + "/embeddings"
    body = json.dumps({"model": EMBED_MODEL, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        vec = (data.get("data") or [{}])[0].get("embedding")
        return [float(x) for x in vec] if isinstance(vec, list) and vec else None
    except Exception as exc:
        logger.debug("embedding 失败（已降级为无向量）: %s", exc)
        return None


def summarize_dialogue(
    base_url: str, api_key: str, model: str, dialogue: str,
) -> str:
    """LLM 把一段对话压成 1~2 句第三人称回忆（照搬叶瞬光 SUMMARY_SYSTEM）。"""
    import urllib.request

    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": dialogue},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = str((data.get("choices") or [{}])[0].get("message", {}).get("content") or "")
        # 去首尾引号
        return text.strip().strip("\"'「」").strip()
    except Exception as exc:
        logger.warning("回忆压缩失败（已静默）: %s", exc)
        return ""


def dialogue_for_extraction(messages: list[dict]) -> str:
    """对话转文本（照搬叶瞬光 profile.dialogueForExtraction 的精简版）。"""
    lines = []
    for m in messages:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        if role in ("user", "assistant") and content:
            lines.append(f"{'用户' if role == 'user' else '她'}：{content}")
    return "\n".join(lines)


def schedule_summary(
    *, session_id: str, memory: EpisodicMemory, messages: list[dict],
    base_url: str, api_key: str, model: str,
) -> None:
    """对话静默 90 秒后调度一次回忆压缩（排期即锁会话身份）。

    门槛：本次新增 ≥6 条消息、对话文本 ≥60 字；全局同一时刻只跑一个总结。
    """
    seen = _summarized_up_to.get(session_id, 0)
    if len(messages) - seen < 6:
        return
    prev = _summary_timers.get(session_id)
    if prev is not None:
        prev.cancel()
    timer = threading.Timer(
        90.0, _run_summary,
        kwargs=dict(
            session_id=session_id, memory=memory, messages=list(messages),
            base_url=base_url, api_key=api_key, model=model,
        ),
    )
    timer.daemon = True
    _summary_timers[session_id] = timer
    timer.start()


def _run_summary(
    *, session_id: str, memory: EpisodicMemory, messages: list[dict],
    base_url: str, api_key: str, model: str,
) -> None:
    global _summary_busy
    _summary_timers.pop(session_id, None)
    if _summary_busy:
        return  # 下一轮对话会再次排期
    _summary_busy = True
    try:
        seen = _summarized_up_to.get(session_id, 0)
        if len(messages) - seen < 6:
            return
        dialogue = dialogue_for_extraction(messages[-24:])
        if len(dialogue) < 60:
            return
        text = summarize_dialogue(base_url, api_key, model, dialogue)
        if not text:
            return
        vec = embed_text(base_url, api_key, text)
        memory.add_episode(text, session_id=session_id, vec=vec)
        _summarized_up_to[session_id] = len(messages)
        logger.info("情景记忆已压缩: %s", text[:30])
    except Exception as exc:
        logger.warning("情景记忆总结失败（已静默）: %s", exc)
    finally:
        _summary_busy = False


def recall_text(
    memory: EpisodicMemory, query: str, current_session_id: str = "",
    base_url: str = "", api_key: str = "",
) -> str:
    """每轮对话前的语义召回（同步、有 5 秒 embedding 超时保护）。"""
    if not base_url or not api_key:
        return ""
    return memory.recall(
        query, current_session_id,
        embed_fn=lambda q: embed_text(base_url, api_key, q),
    )
