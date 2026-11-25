# -*- coding: utf-8 -*-
"""GPT-SoVITS 本地语音 provider —— 通过 api_v2 HTTP 服务合成。

三只桌宠各有自己的音色模型：每个角色启动一个 api_v2 实例（不同端口，各自加载
自己的 tts_infer.yaml），本 provider 只负责按配置里的地址+参考音频发请求。
服务不在 / 合成失败一律抛 TtsUnavailable，让服务层回退到 edge。

api_v2 端点（v2ProPlus 整合包实测）：
  POST {api_base}/tts
  body: {"text":…, "text_lang":"zh", "ref_audio_path":…, "prompt_text":…,
         "prompt_lang":"zh", "text_split_method":"cut0", "media_type":"wav",
         "streaming_mode":false, "speed_factor":…}
  响应：wav 二进制（非 2xx = JSON 错误）
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .base import TtsField, TtsProvider, TtsUnavailable, register

PROVIDER_ID = "gptsovits"
LABEL = "GPT-SoVITS · 本地音色"
AVAILABILITY_CODE = "gptsovits-service-offline"
MISSING_MESSAGE = (
    "本地语音服务未启动：双击 D:\\GPT-SoVITS\\wanzhou-voice\\启动语音服务.bat，"
    "看到 Uvicorn running 后再让桌宠说话"
)
DEFAULT_API_BASE = "http://127.0.0.1:9881"
# 首次请求要惰性加载 Text2Semantic 权重（实测 ~25s），30s 边缘会误判成服务不可用。
TIMEOUT_S = 60.0


def clean_api_base(value) -> str:
    text = str(value or "").strip().rstrip("/")
    return text if text.startswith(("http://", "https://")) else DEFAULT_API_BASE


def _as_float(value, default: float, lo: float, hi: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


class GptSovitsTtsProvider(TtsProvider):
    id = PROVIDER_ID
    label = LABEL
    is_fallback = False
    availability_code = AVAILABILITY_CODE
    unavailable_message = MISSING_MESSAGE
    fields = (
        TtsField(
            "api_base", "voice_chime_gptsovits_api_base", "语音服务地址",
            "本地服务的地址和端口；三只桌宠各用不同端口（角色A 9881 / B 9882 / C 9883）。",
            kind="text", default=DEFAULT_API_BASE, placeholder=DEFAULT_API_BASE,
        ),
        TtsField(
            "ref_audio", "voice_chime_gptsovits_ref_audio", "参考音频",
            "从这只角色的训练素材里挑的一句清晰人声（wav 绝对路径）。",
            kind="text", default="", placeholder="D:\\GPT-SoVITS\\...\\ref.wav",
        ),
        TtsField(
            "ref_text", "voice_chime_gptsovits_ref_text", "参考文本",
            "参考音频逐字对应的中文，标点要与音频停顿一致。",
            kind="multiline", default="", min_height=60,
        ),
        TtsField(
            "speed", "voice_chime_gptsovits_speed", "语速",
            "0.8 慢一些，1.2 快一些，1.0 原速。",
            kind="number", default=100, minimum=70, maximum=130, suffix="%", advanced=True,
        ),
    )

    # ------------------------------------------------------------ 纯层
    def plan(self, values: dict) -> dict:
        return {
            "provider": self.id,
            "api_base": clean_api_base(values.get("api_base")),
            "ref_audio": str(values.get("ref_audio") or "").strip(),
            "ref_text": str(values.get("ref_text") or "").strip(),
            "speed": max(70, min(130, int(values.get("speed") or 100))),
            "ext": "wav",
        }

    def flavor(self, values: dict) -> str:
        # 地址不同 = 音色不同（三个端口对应三个角色），必须进缓存键
        base = clean_api_base(values.get("api_base"))
        port = urllib.parse.urlparse(base).port or 0
        return f"gptsovits|{port}|{_as_float(values.get('speed'), 1.0, 0.7, 1.3):.2f}"

    def availability(self, values: dict) -> str:
        # 纯层只看配置：没填参考音频就不可用（连不上属于 synth 阶段才发现）
        if not str(values.get("ref_audio") or "").strip():
            return AVAILABILITY_CODE
        return ""

    # ------------------------------------------------------------ IO 层
    def synth(self, text: str, plan: dict, out_path) -> None:
        base = clean_api_base(plan.get("api_base"))
        ref = str(plan.get("ref_audio") or "").strip()
        if not ref:
            raise TtsUnavailable(AVAILABILITY_CODE, "没填参考音频")
        if not Path(ref).is_file():
            raise TtsUnavailable(AVAILABILITY_CODE, f"参考音频文件不存在：{ref}")
        speed = _as_float(float(plan.get("speed") or 100) / 100.0, 1.0, 0.7, 1.3)
        body = {
            "text": str(text or ""),
            "text_lang": "zh",
            "ref_audio_path": ref,
            "prompt_text": str(plan.get("ref_text") or "").strip(),
            "prompt_lang": "zh",
            "text_split_method": "cut0",
            "batch_size": 1,
            "media_type": "wav",
            "streaming_mode": False,
            "speed_factor": speed,
        }
        request = urllib.request.Request(
            base + "/tts",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                audio = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise TtsUnavailable(AVAILABILITY_CODE, f"语音服务返回 {exc.code}：{detail}") from exc
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            raise TtsUnavailable(AVAILABILITY_CODE, f"连不上语音服务 {base}：{exc}") from exc
        if not audio:
            raise TtsUnavailable(AVAILABILITY_CODE, "语音服务返回空音频")
        # 错误响应是 JSON，不是 wav
        if audio[:4] != b"RIFF":
            raise TtsUnavailable(AVAILABILITY_CODE, f"语音服务返回非 wav：{audio[:120]!r}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio)
        try:
            if not out_path.exists() or out_path.stat().st_size == 0:
                raise TtsUnavailable(AVAILABILITY_CODE, "GPT-SoVITS 产物为空")
        except OSError as exc:
            raise TtsUnavailable(AVAILABILITY_CODE, f"GPT-SoVITS 产物不可读：{exc}") from exc


PROVIDER = register(GptSovitsTtsProvider())
