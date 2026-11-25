# -*- coding: utf-8 -*-
"""单进程窗口生命周期（多宠生成功能已删除）的机器可验测试。

覆盖批5.2 修复轮（DISPATCH_batch52_fix1）处置清单与验收（4.4b 已删去
feature flag / 碰撞 IPC 相关项）：
- P0-2：右键退出恒注入窗级「退出这只」；
- P1-2/P2-6：runtime 标记恒用 versioned 名；
- P1-3：「退出这只」退主窗后实例提升，托盘/灵动岛动作仍指向存活实例；
- P1-5：「退出这只」关闭该窗从属聊天窗/设置窗（防 writer 复活）；
- P1-7：close_root 改为 per-root 屏障（关 A 窗 writer 期间 B 窗 save 不被拒）；
- T-3：close_root 直接单测；
- switch_character：热切换只做本窗解码收尾，不重建进程级共享 hub。
"""
from __future__ import annotations

import json
import os
import threading
import time

import pytest
from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

import pet.app as app_mod
import pet.slot_manager as slot_manager_mod
from pet import catalog
from pet.app import AppShell, PetInstance
from pet.chat import session_store as session_store_mod
from pet.chat.session_store import SessionStore
from pet.config import APP_DIR_NAME, Config
from pet.window import PetWindow
from tests.pet_window_fakes import FakeLibrary


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


class _FakeLib:
    def pause_warm(self):
        pass

    def resume_warm(self):
        pass


class _FakeAgentLink:
    def __init__(self):
        self.shutdown_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1


class _FakeWindow:
    """窗级退出/切换所需的薄替身：记录调用，不触碰真实 Qt 窗口。

    4.4b：进程内多窗常开化，runtime 标记恒用 versioned 名（无 flag 快照）。
    """

    def __init__(self):
        self.calls = []
        self.lib = _FakeLib()
        self.agent_link_manager = _FakeAgentLink()
        self.is_shown = True

    def save_position(self):
        self.calls.append("save")

    def close(self):
        self.calls.append("close")

    def remove_runtime_marker(self):
        self.calls.append("marker_del")
        slot_manager_mod.delete_runtime_marker(
            self.cfg.dir, self.cfg.instance_id)

    def detach_decode_sessions(self):
        self.calls.append("detach_collision")

    def isVisible(self):
        return self.is_shown

    def hide(self, notify=False):
        self.is_shown = False

    def show(self):
        self.is_shown = True

    def deleteLater(self):
        pass


class _FanoutMovie:
    """与 DecodeFanoutHub fan-out 接缝兼容的最小替身（批5.3 生命周期断言用）。"""

    def __init__(self, path: str):
        self.path = path
        self.playback_speed = 1.0
        self._publish_sink = None
        self._feed_source = None
        self.decode_throttle_divisor = 1
        self.decode_pace_external = False

    def set_decode_throttle(self, divisor: int) -> None:
        self.decode_throttle_divisor = max(1, int(divisor))

    def set_decode_pace_external(self, value: bool) -> None:
        self.decode_pace_external = bool(value)


def _make_primary_with_slot(tmp_path):
    """建主窗 AppShell（无 slot 文件锁，第三返回值恒 None）。"""
    config = Config(tmp_path)
    config.save()
    shell = AppShell(QApplication.instance(), config, enable_chat=True, slot_id=0)
    return shell, config, None


def _stop_sessions(*_insts):
    """4.4a：碰撞 IPC 会话随多进程多宠退役层停用——保留调用点占位（无操作）。"""






def _alive_pid() -> int:
    # 用当前测试进程的 pid（一定存活），用于构造"活着"的标记
    return os.getpid()


def test_switch_character_keeps_process_shared_decode_hub(tmp_path, app, monkeypatch):
    """4.4a：热切换只做本窗解码收尾，不重建进程级共享 hub、不碰其它窗。"""
    config = Config(tmp_path)
    shell = AppShell(QApplication.instance(), config, enable_chat=True)

    monkeypatch.setattr(
        app_mod.PetInstance, "_create_library", lambda self, cid: _FakeLib())

    def fake_build_window(self, character_id, lib=None, build_tray=True):
        win = _FakeWindow()
        win.cfg = self.config
        self.win = win
        return win

    monkeypatch.setattr(app_mod.PetInstance, "_build_window", fake_build_window)

    # 主窗先有一个窗口
    win0 = _FakeWindow()
    win0.cfg = config
    shell.instance.win = win0

    # 第二个窗（独立资源）：其 broker 不应被 touch
    sec = PetInstance(shell, Config(tmp_path, instance_id="slot-1"), enable_chat=True)
    sec_win = _FakeWindow()
    sec_win.cfg = sec.config
    sec.win = sec_win
    shell._instances.append(sec)

    old_broker = shell.instance.broker_facade
    broker_shutdown = []
    monkeypatch.setattr(old_broker, "shutdown", lambda: broker_shutdown.append(1))
    sec_broker_id = id(sec.broker_facade)

    char_ids = catalog.list_available_characters()
    current = str(config.get("character", catalog.DEFAULT_CHARACTER))
    target = next((c for c in char_ids if c != current), "not-default-character")

    shell.instance.switch_character(target)

    # 进程级共享 hub 不被重建（各窗共用，批5.3）。
    assert broker_shutdown == [], \
        "switch_character 不应关进程级共享解码 hub（批5.3 各窗共用）"
    assert shell.instance.broker_facade is old_broker, \
        "进程级解码 hub 不被重建（各窗共用同一份）"
    # 其它窗的解码资源未被动
    assert id(sec.broker_facade) == sec_broker_id
    assert shell.instance.win is not win0

    # 收口：停新会话（避免遗留运行中的独占 QLocal server）
    _stop_sessions(shell.instance, sec)


def test_runtime_marker_versioned_name_avoids_legacy_glob(tmp_path, app):
    """R4：窗口恒用版本化新名（不被旧 'runtime-*.json' glob 匹配），
    且读取侧同时认新旧两种命名（回滚兼容）。"""
    config = Config(tmp_path)
    config.save()

    ver_path = slot_manager_mod.runtime_marker_path(
        config.dir, config.instance_id, versioned=True)
    # 新名不匹配旧 glob（旧 glob 只认 'runtime-*.json' 前缀）
    assert ver_path.name.startswith("pet-runtime-v2-")
    assert len(list(config.dir.glob("runtime-*.json"))) == 0, \
        "新窗不得写入旧格式标记"

    # 写新标记
    slot_manager_mod.write_runtime_marker(
        config.dir, config.instance_id, 10, 10, 100, 100, versioned=True)
    assert ver_path.exists()

    # 新版读取侧：旧名（活 pid 的旧标记）与新名都会被读到
    leg = config.dir / f"runtime-{_alive_pid()}.json"
    leg.write_text(json.dumps({"pid": _alive_pid(), "x": 1, "y": 1, "w": 5, "h": 5}),
                   encoding="utf-8")

    live = slot_manager_mod.read_live_instances(config.dir)
    assert len(live) == 2



def test_exit_primary_promotes_primary_window(tmp_path, app, monkeypatch):
    """P1-3：「退出这只」退主窗后实例提升——托盘/灵动岛/Dock 动作指向存活实例。"""
    shell, config, primary_handle = _make_primary_with_slot(tmp_path)
    primary = shell.instance
    primary.win = _FakeWindow()
    primary.win.cfg = config

    # 第二个实例即将成为新主窗
    sec = PetInstance(shell, Config(base=tmp_path, instance_id="slot-1"),
                      enable_chat=True, slot_id=1)
    sec_win = _FakeWindow()
    sec_win.cfg = sec.config
    sec.win = sec_win
    shell._instances.append(sec)

    monkeypatch.setattr(session_store_mod, "close_writer_for_root",
                        lambda root, timeout=10.0: True)
    monkeypatch.setattr(shell.instance.broker_facade, "shutdown", lambda: None)
    monkeypatch.setattr(sec.broker_facade, "shutdown", lambda: None)

    assert shell.instance is primary
    shell._on_window_exit_requested(shell.instance)

    # 主窗退出后：新列表头（sec）成为主窗，self.instance 更新为存活实例
    assert len(shell.instances) == 2
    assert shell.instance is primary
    assert shell.instance.win is None
    assert sec.win is sec_win
    assert sec.slot_id == 1



def test_exit_window_closes_subwindows(tmp_path, app, monkeypatch):
    """P1-5：「退出这只」关闭该窗从属聊天窗/设置窗并断开引用（防 writer 复活）。"""
    shell, config, primary_handle = _make_primary_with_slot(tmp_path)
    shell.instance.win = _FakeWindow()
    shell.instance.win.cfg = config

    saves = []

    class _Store:
        def save(self, session):
            saves.append(session)

    class _Subwindow:
        def __init__(self):
            self.store = _Store()
            self.session = object()
            self.deleted = False

        def close(self):
            closed.append(self)

        def deleteLater(self):
            self.deleted = True

    sub_legacy = _Subwindow()
    sub_modern = _Subwindow()
    sub_quick = _Subwindow()
    sub_settings = _Subwindow()
    sub_mod_settings = _Subwindow()
    shell.instance.legacy_chat_window = sub_legacy
    shell.instance.modern_chat_window = sub_modern
    shell.instance.quick_chat = sub_quick
    shell.instance.chat_settings_dialog = sub_settings
    shell.instance.modern_settings_dialog = sub_mod_settings
    shell.instance.chat_window = sub_legacy
    closed = []

    # 预备第二个实例（让退出主窗不是最后一窗，避免触发 app.quit）
    sec = PetInstance(shell, Config(base=tmp_path, instance_id="slot-1"),
                      enable_chat=True, slot_id=1)
    sec_win = _FakeWindow()
    sec_win.cfg = sec.config
    sec.win = sec_win
    shell._instances.append(sec)

    monkeypatch.setattr(session_store_mod, "close_writer_for_root",
                        lambda root, timeout=10.0: True)
    monkeypatch.setattr(shell.instance.broker_facade, "shutdown", lambda: None)
    monkeypatch.setattr(sec.broker_facade, "shutdown", lambda: None)

    shell._on_window_exit_requested(shell.instance)

    # slot0 退出不关共享会话与从属聊天窗（他们由该 instance 继续持有、可恢复）；
    # 唯一被关的是**进程内设置窗**：收口前的设置页闸门（ops P3-c）必须让它先过一遍
    # 保存/放弃/继续编辑，否则草稿会随父窗一起无声消失
    # （见 tests/test_settings_stale_form_exit.py 第 9 节）。
    assert closed == [sub_mod_settings], "只有设置窗该被闸门关掉"
    assert saves == []
    assert shell.instance.legacy_chat_window is sub_legacy
    assert shell.instance.modern_chat_window is sub_modern
    assert shell.instance.quick_chat is sub_quick
    assert shell.instance.win is None
    assert shell.instance is not sec


def test_exit_window_callback_injected_on_every_window(tmp_path, app, monkeypatch):
    """P0-2（4.4b 语义）：窗级「退出这只」恒注入；_request_quit 走窗级分支。

    多窗常开化后不再有 flag 关的"不注入走 app.quit"分支——最后一窗退出即
    全进程退出，两者对外行为等价。
    """
    config = Config(tmp_path)
    config.save()
    shell = AppShell(QApplication.instance(), config, enable_chat=True)
    inst = shell.instance
    win = _FakeWindow()
    win.cfg = config
    inst.win = win
    inst._wire_window(win)
    assert callable(win.on_exit_window), "每窗都应注入窗级「退出这只」"

    # _request_quit 走窗级分支（on_exit_window 被调用，而非 app.quit）
    exit_calls = []
    win.on_exit_window = lambda: exit_calls.append(1)
    win._active_context_menu = None
    quit_calls = []
    _app = QApplication.instance()
    monkeypatch.setattr(_app, "quit", lambda: quit_calls.append(1))
    PetWindow._request_quit(win)
    assert exit_calls == [1], "右键退出应走窗级「退出这只」"
    assert quit_calls == [], "右键退出不应走 app.quit"


# --------------------------------------------------------------------------
# P1-7 / T-3：close_root per-root 屏障
# --------------------------------------------------------------------------
def _make_session_store_pairs(tmp_path):
    store_a = SessionStore(tmp_path, "slot-1")
    store_b = SessionStore(tmp_path, "slot-2")
    return store_a, store_b


def _create_sessions(store):
    from pet.chat.models import ChatSession
    session = store.create("char", "provider", "prompt")
    return session


def test_close_root_closes_only_target_writer(tmp_path, app):
    """T-3：close_root 只关闭目标 root 的 writer，其它窗 writer 保持可用。"""
    store_a, store_b = _make_session_store_pairs(tmp_path)
    sa = _create_sessions(store_a)
    sb = _create_sessions(store_b)
    assert store_a.save(sa) is True
    assert store_b.save(sb) is True
    root_a = store_a.root
    root_b = store_b.root
    assert session_store_mod._registry.get_writer(root_a) is not None
    assert session_store_mod._registry.get_writer(root_b) is not None

    assert session_store_mod.close_writer_for_root(root_a) is True
    assert session_store_mod._registry.get_writer(root_a) is None
    # B 窗 writer 不受影响、仍可写
    assert session_store_mod._registry.get_writer(root_b) is not None
    assert store_b.save(sb) is True


def test_close_root_per_root_barrier_does_not_reject_other_window(tmp_path, app, monkeypatch):
    """P1-7：关 A 窗 writer 期间 B 窗 save 不被拒（per-root 屏障取代全局 _closing）。"""
    store_a, store_b = _make_session_store_pairs(tmp_path)
    sa = _create_sessions(store_a)
    sb = _create_sessions(store_b)
    assert store_a.save(sa) is True
    assert store_b.save(sb) is True
    root_a = store_a.root

    writer_a = session_store_mod._registry.get_writer(root_a)
    writer_b = session_store_mod._registry.get_writer(store_b.root)
    assert writer_a is not None and writer_b is not None

    entered = threading.Event()
    release = threading.Event()
    orig_close = writer_a.close

    def blocking_close(timeout=10.0):
        entered.set()
        release.wait(5.0)
        return orig_close(timeout=timeout)

    monkeypatch.setattr(writer_a, "close", blocking_close)

    result = {}

    def do_close():
        result["ok"] = session_store_mod.close_writer_for_root(root_a)

    t = threading.Thread(target=do_close)
    t.start()
    assert entered.wait(5.0), "close_root(A) 应已进入且阻塞"
    try:
        # A 窗 writer 关闭窗口期内，B 窗 save 不被拒（per-root 屏障）
        assert store_b.save(sb) is True, "关 A 窗 writer 期间 B 窗 save 不应被拒"
    finally:
        release.set()
        t.join(5.0)
    assert result["ok"] is True


# --------------------------------------------------------------------------
# T-1：两窗各持 session → runtime_id 不同、互不为 peer-self（P1-1）
# --------------------------------------------------------------------------
def _pump(seconds: float) -> None:
    app = QApplication.instance() or QApplication([])
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
        time.sleep(0.005)



def test_enable_chat_setter_does_not_write_shell(tmp_path, app):
    """P2-4：PetInstance.enable_chat setter 不得改写进程级 shell（只读转发）。"""
    shell = AppShell(QApplication.instance(), Config(tmp_path), enable_chat=True)
    inst = shell.instance
    # setter 只缓存无 shell 兜底，不改写进程级权威源
    inst.enable_chat = False
    assert shell.enable_chat is True, "PetInstance setter 不得改写进程级 shell"
    assert inst.enable_chat is True, "getter 仍读 shell 权威值（只读转发）"

    # 无 shell（__new__ 测试桩）：setter 缓存值作兜底
    bare = PetInstance.__new__(PetInstance)
    bare._enable_chat = True
    bare.enable_chat = False
    assert bare.enable_chat is False




def test_real_window_construction_writes_versioned_marker(tmp_path, app):
    """N-1（红→绿回归）：真实 PetWindow 构造期就写 v2 名标记，绝不写旧名
    （4.4b：多窗常开化 → 恒版本化，旧名无法区分同进程多窗）。"""
    config = Config(tmp_path)
    config.save()  # 确保 config.dir 已建（生产路径由启动流程建，测试需显式）
    win = PetWindow(FakeLibrary(), config)
    try:
        v2 = slot_manager_mod.runtime_marker_path(
            config.dir, config.instance_id, versioned=True)
        assert v2.exists(), "窗构造后必须已写 v2 标记（N-1）"
        legacy = [p for p in config.dir.glob("runtime-*.json")]
        assert legacy == [], f"窗不得写旧名标记，实际: {legacy}"
    finally:
        win.close()
        win.deleteLater()


def test_non_primary_switch_builds_no_tray(tmp_path, app, monkeypatch):
    """T-6 补全（托盘半边）：非主窗热切换 build_tray=False，绝不动共享托盘。"""
    config = Config(tmp_path)
    shell = AppShell(QApplication.instance(), config, enable_chat=True)
    monkeypatch.setattr(
        app_mod.PetInstance, "_create_library", lambda self, cid: _FakeLib())

    build_tray_calls = []

    def fake_build_window(self, character_id, lib=None, build_tray=True):
        build_tray_calls.append(build_tray)
        win = _FakeWindow()
        win.cfg = self.config
        self.win = win
        return win

    monkeypatch.setattr(app_mod.PetInstance, "_build_window", fake_build_window)

    primary_win = _FakeWindow()
    primary_win.cfg = config
    shell.instance.win = primary_win
    sec = PetInstance(shell, Config(tmp_path, instance_id="slot-1"),
                      enable_chat=True)
    sec_win = _FakeWindow()
    sec_win.cfg = sec.config
    sec.win = sec_win
    shell._instances.append(sec)

    char_ids = catalog.list_available_characters()
    current = str(sec.config.get("character", catalog.DEFAULT_CHARACTER))
    target = next((c for c in char_ids if c != current), "not-default-character")
    sec.switch_character(target)

    assert build_tray_calls == [False], \
        f"非主窗热切换不得触碰托盘，实际 build_tray 序列: {build_tray_calls}"

    _stop_sessions(shell.instance, sec)


# ---------------------------------------------------------------- 新 slot 落种
def test_seed_slot_config_follows_main_settings(tmp_path):
    """新 slot 首次多开：配置跟随主设置（剔除每窗状态键，落种含 user_customized=False）。"""
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    main_cfg = {"character": "shenshen", "click_sound_enabled": False,
                "rx": 0.5, "ry": 0.9, "screen_name": "X", "facing": "left"}
    (config_dir / "config.json").write_text(
        json.dumps(main_cfg), encoding="utf-8")

    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 2) is True
    seeded = json.loads(
        (config_dir / "config-slot-2.json").read_text(encoding="utf-8"))
    assert seeded["click_sound_enabled"] is False  # 跟随主设置
    assert seeded["character"] == "shenshen"
    assert seeded.get("user_customized") is False  # 落种默认不置位
    for k in ("rx", "ry", "screen_name", "facing"):
        assert k not in seeded, f"每窗状态键 {k} 不得继承"



def test_seed_slot_config_refreshes_non_customized_slot(tmp_path):
    """批 C：slot 存在但 user_customized 为假（含旧存档无此键）→ 按当前主设置重新刷新。"""
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({"character": "shenshen"}),
        encoding="utf-8")
    # 旧存档（无 user_customized 键）按假处理 → 应被刷新成主设置。
    existing = {"character": "other", "custom": 1}
    (config_dir / "config-slot-3.json").write_text(json.dumps(existing), encoding="utf-8")

    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 3) is True
    refreshed = json.loads(
        (config_dir / "config-slot-3.json").read_text(encoding="utf-8"))
    assert refreshed["character"] == "shenshen"  # 跟随主设置
    assert refreshed.get("user_customized") is False


def test_seed_slot_config_preserves_customized_slot(tmp_path):
    """批 C：slot 存在且 user_customized 为真 → 整个跳过，一个键都不碰。"""
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({"character": "shenshen"}), encoding="utf-8")
    existing = {"character": "other", "custom": 1, "user_customized": True}
    (config_dir / "config-slot-4.json").write_text(json.dumps(existing), encoding="utf-8")

    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 4) is False
    assert json.loads((config_dir / "config-slot-4.json").read_text(
        encoding="utf-8")) == existing


def test_seed_slot_config_refresh_preserves_slot_position(tmp_path):
    """批 C：落种/刷新永不写位置键——刷新不覆盖 slot 自己拖动后自存的位置。"""
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    # 主配置的位置键是另一个值；刷新后 slot 应保留自己的位置，不被主配置覆盖。
    (config_dir / "config.json").write_text(json.dumps({
        "character": "shenshen",
        "rx": 0.1, "ry": 0.2, "screen_name": "MAIN", "facing": "left",
    }), encoding="utf-8")
    existing = {"character": "other",
                "rx": 0.6, "ry": 0.7, "screen_name": "SLOT", "facing": "right"}
    (config_dir / "config-slot-5.json").write_text(json.dumps(existing), encoding="utf-8")

    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 5) is True
    refreshed = json.loads(
        (config_dir / "config-slot-5.json").read_text(encoding="utf-8"))
    assert refreshed["rx"] == 0.6
    assert refreshed["ry"] == 0.7
    assert refreshed["screen_name"] == "SLOT"
    assert refreshed["facing"] == "right"


def test_multi_process_start_seed_then_config_roundtrip(tmp_path):
    """多进程启动路径（main 先 seed 再构造 Config）落种可被 Config 读回。"""
    config_dir = tmp_path / APP_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps({
        "scale": 1.0,
        "dynamic_island": {"enabled": True},
    }), encoding="utf-8")

    # 与 main() 的 seed → Config(instance_id) 次序一致。
    assert slot_manager_mod.seed_slot_config_from_main(config_dir, 2) is True
    cfg = Config(base=tmp_path, instance_id="slot-2")
    assert cfg.get("scale") == 1.0
    assert cfg.get("dynamic_island", {}).get("enabled") is False
    assert cfg.get("user_customized") is False






def test_runtime_marker_written_on_first_show(tmp_path, app):
    """窗口首次显示即登记 runtime 标记——没被拖动过的窗口也有标记，
    设置进程按标记枚举活窗口时不会漏掉它。"""
    from pet.window import PetWindow

    config = Config(tmp_path)
    config.set("collision_enabled", False)
    config.save()
    win = PetWindow(FakeLibrary(), config)
    win.show()
    QApplication.instance().processEvents()
    # 4.4b：恒写版本化名 pet-runtime-v2-<pid>-slot-<N>.json
    marker = slot_manager_mod.runtime_marker_path(
        config.dir, config.instance_id, versioned=True)
    assert marker.exists(), "首次显示必须登记 runtime 标记"
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()
    win.close()


def test_open_quick_chat_routes_to_overlay_shell_when_win_none(tmp_path, app, monkeypatch):
    """overlay 拓扑（``win`` 恒 None、不建 PetWindow）：快速对话必须改走 overlay
    壳的 sprite 锚定路径——锚到隐藏/不存在的 PetWindow 等于点了没反应（岛卡片
    「聊天」与托盘「快速对话（气泡）」共用本缝，2026-10-08 实机发现的回归）。"""
    shell, config, _handle = _make_primary_with_slot(tmp_path)
    inst = PetInstance(shell, config, enable_chat=True, slot_id=None)
    inst.win = None  # overlay 拓扑恒为 None（不建 PetWindow）
    monkeypatch.setattr(shell, "_aggregate_pet_visible", lambda: True)

    calls = []

    class _FakeOverlay:
        def open_quick_chat(self, sprite=None):
            calls.append(sprite)
            return True

    shell._overlay_shell = _FakeOverlay()
    inst.open_quick_chat()
    deadline = time.time() + 2.0
    while not calls and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert calls == [None], "win=None 时必须路由到 overlay 壳（sprite=None = 主宠）"


def test_open_quick_chat_win_none_without_overlay_is_quiet_noop(tmp_path, app, monkeypatch):
    """反面：win=None 且没有 overlay 壳（异常中间态）——安静不炸，不抛异常。"""
    shell, config, _handle = _make_primary_with_slot(tmp_path)
    inst = PetInstance(shell, config, enable_chat=True, slot_id=None)
    inst.win = None
    monkeypatch.setattr(shell, "_aggregate_pet_visible", lambda: True)
    shell._overlay_shell = None
    inst.open_quick_chat()  # 不抛即过
    QApplication.processEvents()
