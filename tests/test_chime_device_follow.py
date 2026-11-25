# -*- coding: utf-8 -*-
"""语音通道跟随系统默认输出设备（插/拔耳机）的回归测试。

点击音效走 sound_winmm 的 winmm 池，早已跟随默认设备（issue #315）；语音通道的
QAudioOutput 创建时绑死默认设备，此前不会跟随——表现是"点击音走耳机了、说话还在
扬声器"。本文件锁定"起播前限频对账、变了整只重建"的语义。

纪律：不打网络、不依赖真实音频设备——播放器/音频输出全用替身；默认端点探测
monkeypatch 到 sound_winmm.default_render_device_id（产品代码走的就是这个入口）。
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from pet import sound_winmm
from pet.config import Config
from pet.voice.chime_service import VoiceChimeService


class _FakeSignal:
    """最小 Qt 信号替身：只记 connect / disconnect 次数。"""

    def __init__(self) -> None:
        self.connected = 0
        self.disconnected = 0

    def connect(self, slot) -> None:  # noqa: ARG002 - 替身只计数
        self.connected += 1

    def disconnect(self, slot) -> None:  # noqa: ARG002 - 替身只计数
        self.disconnected += 1


class _TrackedPlayer:
    """记录 stop / setSource / 信号断开的播放器替身。"""

    def __init__(self) -> None:
        self.sources: list = []
        self.stops = 0
        self.plays = 0
        self.mediaStatusChanged = _FakeSignal()
        self.errorOccurred = _FakeSignal()

    def setSource(self, url) -> None:  # noqa: N802 - 对齐 Qt API
        self.sources.append(url)

    def play(self) -> None:
        self.plays += 1

    def stop(self) -> None:
        self.stops += 1


class _FakeAudioOut:
    def __init__(self) -> None:
        self.volumes: list[float] = []

    def setVolume(self, value: float) -> None:  # noqa: N802 - 对齐 Qt API
        self.volumes.append(value)


class _App:
    """服务只用到 config / win；本文件不触发气泡与通知。"""

    def __init__(self, config) -> None:
        self.config = config
        self.win = None

    def system_notify(self, *args, **kwargs) -> None:  # noqa: ARG002
        pass


def _service(tmp_path, monkeypatch):
    """构造一个带假播放器的服务（无网络、无真实设备）。"""
    QApplication.instance() or QApplication([])
    app = _App(Config(base=tmp_path))
    service = VoiceChimeService(app)
    service._player = _TrackedPlayer()
    service._audio_out = _FakeAudioOut()
    service._terminal_statuses = ("EndOfMedia", "InvalidMedia")
    return service


def _probe(monkeypatch, ids):
    """把默认端点探测换成按序返回 ids 的桩；None = 探测失败。"""
    iterator = iter(ids)

    def fake_probe():
        return next(iterator, None)

    monkeypatch.setattr(sound_winmm, "default_render_device_id", fake_probe)


def _unthrottle(service) -> None:
    """把限频起点拨回远古，让下一次对账必定执行探测。"""
    service._device_checked_at = 0.0


# ------------------------------------------------------------ 探测与记录


def test_probe_failure_keeps_player(tmp_path, monkeypatch):
    """探测不到（非 Windows / COM 异常 / 无默认设备）时绝不动播放器。"""
    service = _service(tmp_path, monkeypatch)
    _probe(monkeypatch, [None])
    old_player = service._player
    old_out = service._audio_out

    service._follow_default_device()

    assert service._player is old_player, "探测失败不得重建——宁可继续往旧设备播"
    assert service._audio_out is old_out
    assert service._device_id is None


def test_first_probe_records_device_without_rebuild(tmp_path, monkeypatch):
    """首次探测只记录端点 ID：此刻的播放器本来就绑在它上面，无需重建。"""
    service = _service(tmp_path, monkeypatch)
    _probe(monkeypatch, ["dev-speaker"])
    old_player = service._player

    service._follow_default_device()

    assert service._device_id == "dev-speaker"
    assert service._player is old_player


def test_probe_is_throttled(tmp_path, monkeypatch):
    """限频窗口内不重复做 COM 往返（play 是热路径）。"""
    calls: list[int] = []

    def fake_probe():
        calls.append(1)
        return "dev-speaker"

    monkeypatch.setattr(sound_winmm, "default_render_device_id", fake_probe)
    service = _service(tmp_path, monkeypatch)

    service._follow_default_device()
    service._follow_default_device()

    assert len(calls) == 1, "2s 内的第二次对账必须跳过探测"


def test_same_device_does_not_rebuild(tmp_path, monkeypatch):
    """默认设备没变时不重建——避免每次起播都掐正在播的那一段。"""
    service = _service(tmp_path, monkeypatch)
    _probe(monkeypatch, ["dev-speaker", "dev-speaker"])
    old_player = service._player

    service._follow_default_device()
    _unthrottle(service)
    service._follow_default_device()

    assert service._player is old_player


# ------------------------------------------------------------ 切换重建


def test_device_change_resets_player_and_state(tmp_path, monkeypatch):
    """默认设备变了：停旧段、断信号、清载、放标志，并把播放器置空待重建。"""
    service = _service(tmp_path, monkeypatch)
    _probe(monkeypatch, ["dev-speaker", "dev-headphones"])
    old_player = service._player
    old_out = service._audio_out
    service._follow_default_device()
    # 模拟"起播但未收到终止态"：切设备时这个标志必须被清掉，否则新播放器
    # 起来之前通道一直判忙。
    service._play_pending_end = True
    service._current_respect_quiet = True

    _unthrottle(service)
    service._follow_default_device()

    assert service._device_id == "dev-headphones"
    assert service._player is None, "收回旧播放器，下一次 _ensure_player 在新设备上建"
    assert service._audio_out is None
    assert service._terminal_statuses == ()
    assert service._play_pending_end is False
    assert service._current_respect_quiet is None
    assert old_player.stops == 1, "旧段必须停住，否则继续往扬声器出声"
    assert len(old_player.sources) == 1, "必须清载（setSource(QUrl())）把状态拽出加载态"
    assert old_player.mediaStatusChanged.disconnected == 1, "先断信号，别让析构期冒出的事件结算队列"
    assert old_player.errorOccurred.disconnected == 1


def test_ensure_player_follows_device_before_returning(tmp_path, monkeypatch):
    """对账必须在 _ensure_player 里、且在判 _player 之前——否则已建播放器会漏检。"""
    service = _service(tmp_path, monkeypatch)
    calls: list[int] = []
    monkeypatch.setattr(service, "_follow_default_device", lambda: calls.append(1))

    assert service._ensure_player() is True
    assert calls == [1], "即使播放器已存在，起播前也要对一次默认设备"


def test_device_change_then_ensure_player_creates_fresh_player(tmp_path, monkeypatch):
    """切设备后下一次起播：_ensure_player 真的建出新播放器并接回两个信号。"""
    from PySide6 import QtMultimedia

    service = _service(tmp_path, monkeypatch)
    _probe(monkeypatch, ["dev-speaker", "dev-headphones"])
    service._follow_default_device()

    created: list[_TrackedPlayer] = []

    class _FakeQMediaPlayer:
        class MediaStatus:
            EndOfMedia = "EndOfMedia"
            InvalidMedia = "InvalidMedia"

        def __init__(self):
            self.mediaStatusChanged = _FakeSignal()
            self.errorOccurred = _FakeSignal()
            created.append(self)

        def setAudioOutput(self, out) -> None:  # noqa: N802
            pass

    class _FakeQAudioOutput:
        def __init__(self):
            pass

    monkeypatch.setattr(QtMultimedia, "QMediaPlayer", _FakeQMediaPlayer)
    monkeypatch.setattr(QtMultimedia, "QAudioOutput", _FakeQAudioOutput)

    _unthrottle(service)
    assert service._ensure_player() is True

    assert len(created) == 1, "重建必须新建 QMediaPlayer，而不是复用绑旧设备的那只"
    assert created[0].mediaStatusChanged.connected == 1, "终止态信号要接回"
    assert created[0].errorOccurred.connected == 1, "错误信号要接回（否则设备拔掉会永久判忙）"
    assert service._terminal_statuses == ("EndOfMedia", "InvalidMedia")
