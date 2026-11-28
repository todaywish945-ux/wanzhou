# -*- coding: utf-8 -*-
"""出厂自言自语语音：随包 wav 首次落到用户缓存目录（只补缺，不覆盖）。

背景：台词库与语音缓存的真源都在 ``%APPDATA%/wanzhou-pet/``（每用户各自维护）。
作者重写了 15 句台词并录好对应 wav，希望新用户开箱就能听到——把这些 wav
放在包内 ``assets/self_talk_voice_seed/``，启动时复制到用户缓存目录。

**只复制用户缺失的文件**：用户重新生成过某句语音后缓存里已有同名文件，
绝不覆盖（那正是用户自己的选择）。三进程并发启动由目录锁串行化。
"""
from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

from ..config_write_lock import ConfigWriteError, config_write_lock

logger = logging.getLogger("pet.voice.seed")

#: 包内种子目录的相对路径（冻结包按 sys._MEIPASS 为根，源码树按仓库根）
SEED_RELATIVE_PATH = ("assets", "self_talk_voice_seed")
#: 用户缓存目录名（与 pet.voice.self_talk.CACHE_DIR_NAME 一致）
CACHE_DIR_NAME = "self_talk_voice"


def seed_candidates() -> tuple[Path, ...]:
    """种子目录候选：冻结包在前、源码树在后（纯函数）。"""
    meipass = getattr(sys, "_MEIPASS", None)
    candidates: list[Path] = []
    if meipass:
        candidates.append(Path(meipass).joinpath(*SEED_RELATIVE_PATH))
    # 本模块在 pet/voice/ 下：parents[0]=voice, [1]=pet, [2]=仓库根
    candidates.append(Path(__file__).resolve().parents[2].joinpath(*SEED_RELATIVE_PATH))
    return tuple(candidates)


def seed_dir() -> Path | None:
    """第一个真实存在的种子目录；没有就返回 None、不影响启动。"""
    for candidate in seed_candidates():
        if candidate.is_dir():
            return candidate
    return None


def seed_file_names() -> frozenset[str]:
    """包内种子 wav 的文件名 stem 集合（= 出厂台词文本的 md5[:16]）。

    供 ``self_talk._classic_audio`` 识别"这句的缓存文件其实是出厂录音"：
    种子录音是作者声线，不该盖过用户自己配置的合成音色（删除台词回退
    内置台词后声线突变的根因，见 ``self_talk`` 模块注释）。包里没有种子
    目录就返回空集合，查找侧零影响。
    """
    source = seed_dir()
    if source is None:
        return frozenset()
    try:
        return frozenset(p.stem for p in source.glob("*.wav"))
    except OSError:
        return frozenset()


def seed_voice_cache(config_dir: Path | str) -> int:
    """把包内种子 wav 复制到用户缓存目录，只补缺失文件。

    返回本次复制的文件数。任何失败都只记日志，绝不让桌宠启动中断。
    """
    source = seed_dir()
    if source is None:
        return 0
    target_dir = Path(config_dir) / CACHE_DIR_NAME
    copied = 0
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with config_write_lock(Path(config_dir)):
            for wav in sorted(source.glob("*.wav")):
                target = target_dir / wav.name
                if target.exists():
                    continue  # 用户已有（含重新生成过的）→ 不覆盖
                try:
                    shutil.copy2(wav, target)
                    copied += 1
                except OSError:
                    logger.debug("语音种子复制失败 %s", wav.name, exc_info=True)
    except (OSError, ConfigWriteError):
        logger.debug("语音种子目录写入失败", exc_info=True)
    return copied
