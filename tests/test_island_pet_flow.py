# -*- coding: utf-8 -*-
"""端到端契约（纯逻辑层）：三进程共享状态 + 灵动岛三段的完整显隐流程。

模拟真实拓扑：三个进程共用配置目录，岛只在角色 A 进程且**常驻显示**（时间/
指标等旧功能始终在）。验证：
1. 全可见 → 岛仍显示，三段都是窄态（暗），时间段在；
2. B 进程隐藏 → 共享状态写 False → B 段亮起展开、岛变长；
3. 点岛的 B 段 → 写共享状态 True → B 进程 poll 收到 hidden→visible 边沿 → show；
4. 一键全部显示 → 三只全 True → 三段收回窄态，岛仍常驻。

不改任何产品代码，只组合公开 API，钉住跨进程协作的语义。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from pet import pet_visibility as pv
from pet.config import Config
from pet.island.dynamic_island import DynamicIsland


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _island(tmp_path: Path) -> DynamicIsland:
    _qapp()
    cfg = Config(base=tmp_path)
    cfg.set("dynamic_island", {
        "enabled": True, "show_icon": False, "show_name": False,
        "show_info": True, "show_status": False, "info_mode": "time",
        "style": "dark", "x": 400, "y": 300, "dock_edge": "none",
    })
    return DynamicIsland(cfg)


def _sync_island(island: DynamicIsland, shared_dir: Path) -> None:
    """岛宿主按共享状态刷新三段（对应 AppShell._sync_island_visibility_for_pets）。

    新契约：岛常驻，显隐只由开关/模块门决定；这里只同步三段状态，不碰 show/hide。
    """
    states = pv.read_visibility(shared_dir)
    island.set_pet_states(states)


def test_full_hide_recover_flow(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    island = _island(tmp_path / "island")
    try:
        # 0) 三进程启动：各自登记可见。岛常驻（时间/指标等旧功能一直在）
        for pet_id in pv.PET_IDS:
            pv.register_pet(shared, pet_id)
        island.show()
        _sync_island(island, shared)
        assert island.isVisible()
        assert [p.seg.pet_id for p in island._petbar_layout().placements] == list(pv.PET_IDS)
        # 旧功能保留：时间主信息段仍在常规段列表里（三段是叠加，不是替换）
        seg_ids = [seg.seg_id for seg in island._compose_info_segments()]
        assert "primary" in seg_ids
        all_visible_width = island.width()

        # 1) B 进程用户右键隐藏 → 写共享状态 → B 段亮起、岛伸长
        pv.set_pet_visible(shared, "角色B", False)
        _sync_island(island, shared)
        assert island.isVisible()  # 常驻，不因隐藏才出现
        active = [p for p in island._petbar_layout().placements if p.seg.hidden]
        assert [p.seg.pet_id for p in active] == ["角色B"]
        assert island.width() > all_visible_width

        # 2) 点岛的 B 段 → 只恢复 B（模拟 AppShell._on_show_pet_requested）
        states = pv.set_pet_visible(shared, "角色B", True)
        assert states == {"角色A": True, "角色B": True, "角色C": True}
        _sync_island(island, shared)
        assert island.isVisible()
        assert island.width() == all_visible_width  # 三段收回窄态

        # 3) 再隐藏两只 → 岛更长、两段亮起
        pv.set_pet_visible(shared, "角色A", False)
        pv.set_pet_visible(shared, "角色C", False)
        _sync_island(island, shared)
        two_hidden_width = island.width()
        active = [p.seg.pet_id for p in island._petbar_layout().placements if p.seg.hidden]
        assert active == ["角色A", "角色C"]
        assert two_hidden_width > all_visible_width

        # 4) 一键全部显示 → 三只全恢复、三段回窄态，岛仍常驻
        states = pv.set_all_visible(shared)
        assert all(states.values())
        _sync_island(island, shared)
        assert island.isVisible()
        assert island.width() == all_visible_width
    finally:
        island.close()


def test_edge_only_hidden_to_visible_triggers_show(tmp_path):
    """poll 只收口 hidden→visible 边沿：可见→隐藏不反向 show（全屏避让不被打断）。"""
    shared = tmp_path / "shared"
    shared.mkdir()
    pv.register_pet(shared, "角色B")
    # 初始 seen = 可见
    seen = pv.read_visibility(shared)
    # 用户隐藏 B：写 False，但 seen 里还是 True。按边沿规则这不是 hidden→visible，不动窗。
    states = pv.set_pet_visible(shared, "角色B", False)
    my_id = "角色B"
    should_show = seen.get(my_id) is False and states.get(my_id) is True
    assert should_show is False  # 隐藏边沿不触发 show
    # 岛请求显示 B：状态回 True，此时 seen（上一拍 False）→ True，触发 show
    seen = dict(states)
    states = pv.set_pet_visible(shared, "角色B", True)
    should_show = seen.get(my_id) is False and states.get(my_id) is True
    assert should_show is True


def test_toggle_pet_writes_opposite_state(tmp_path):
    """AppShell 的 toggle 处理：读当前状态写相反值（可见→隐藏、隐藏→可见）。"""
    from types import SimpleNamespace
    from pet.app import AppShell

    shared = tmp_path / "shared"
    shared.mkdir()
    # 假 config：只需 .dir 指向共享状态目录（_on_toggle_pet_requested 只读它）
    cfg = SimpleNamespace(dir=shared)
    shell = AppShell.__new__(AppShell)
    shell.config = cfg
    shell.island = None
    shell.instance = SimpleNamespace(win=None)
    try:
        pv.register_pet(shared, "角色B")

        # B 当前可见 → toggle 写隐藏
        shell._on_toggle_pet_requested("角色B")
        assert pv.read_visibility(shared)["角色B"] is False
        # B 当前隐藏 → toggle 写可见
        shell._on_toggle_pet_requested("角色B")
        assert pv.read_visibility(shared)["角色B"] is True
    finally:
        pass


def test_poll_hides_window_on_visible_to_hidden_edge(tmp_path):
    """岛点角色写 false 后，poll 必须**真的 hide 窗口**（用户反馈的 bug）。

    旧实现在 shared=false 时把状态补写回 true，导致点岛「隐藏」永不生效。
    这里用假窗口记录 hide/show 调用，钉住三条边沿：
    - visible→hidden：hide
    - hidden→visible：show
    - 稳态 hidden + 窗在屏上（托盘直接 show 的滞后）：补写 true，不 hide
    """
    from types import SimpleNamespace
    from pet.app import AppShell

    shared = tmp_path / "shared"
    shared.mkdir()
    pv.register_pet(shared, "角色B")

    calls: list[str] = []
    visible = True

    class FakeWin:
        def isVisible(self):
            return visible

        def hide(self, **kwargs):
            nonlocal visible
            calls.append("hide")
            visible = False

        def show(self):
            nonlocal visible
            calls.append("show")
            visible = True

    shell = AppShell.__new__(AppShell)
    shell.config = SimpleNamespace(dir=shared, get=lambda key, default=None: "角色B")
    shell.instance = SimpleNamespace(win=FakeWin())
    shell._pet_states_seen = dict(pv.read_visibility(shared))  # B 可见

    # 1) 岛请求隐藏：写 false → poll 应 hide
    pv.set_pet_visible(shared, "角色B", False)
    shell._poll_pet_visibility()
    assert "hide" in calls, calls
    assert pv.read_visibility(shared)["角色B"] is False  # 没被补写回 true

    # 2) 岛请求显示：写 true → poll 应 show
    calls.clear()
    pv.set_pet_visible(shared, "角色B", True)
    shell._poll_pet_visibility()
    assert "show" in calls, calls

    # 3) 稳态 hidden + 窗被托盘直接 show（无新边沿）→ 补写 true，不 hide
    calls.clear()
    pv.set_pet_visible(shared, "角色B", False)
    shell._poll_pet_visibility()   # 先让 seen 跟上 false
    calls.clear()
    visible = True                  # 模拟托盘直接把窗 show 了（没写状态）
    shell._poll_pet_visibility()
    assert "hide" not in calls, calls
    assert pv.read_visibility(shared)["角色B"] is True  # 补写可见事实


def test_poll_hides_window_on_visible_to_hidden_edge(tmp_path):
    """岛点角色写 false 后，poll 必须**真的 hide 窗口**（用户反馈的 bug）。

    旧实现在 shared=false 时把状态补写回 true，导致点岛「隐藏」永不生效。
    这里用假窗口记录 hide/show 调用，钉住三条边沿：
    - visible→hidden：hide
    - hidden→visible：show
    - 稳态 hidden + 窗在屏上（托盘直接 show 的滞后）：补写 true，不 hide
    """
    from types import SimpleNamespace
    from pet.app import AppShell

    shared = tmp_path / "shared"
    shared.mkdir()
    pv.register_pet(shared, "角色B")

    calls: list[str] = []
    visible = True

    class FakeWin:
        def isVisible(self):
            return visible

        def hide(self, **kwargs):
            nonlocal visible
            calls.append("hide")
            visible = False

        def show(self):
            nonlocal visible
            calls.append("show")
            visible = True

    shell = AppShell.__new__(AppShell)
    shell.config = SimpleNamespace(dir=shared, get=lambda key, default=None: "角色B")
    shell.instance = SimpleNamespace(win=FakeWin())
    shell._pet_states_seen = dict(pv.read_visibility(shared))  # B 可见

    # 1) 岛请求隐藏：写 false → poll 应 hide
    pv.set_pet_visible(shared, "角色B", False)
    shell._poll_pet_visibility()
    assert "hide" in calls, calls
    assert pv.read_visibility(shared)["角色B"] is False  # 没被补写回 true

    # 2) 岛请求显示：写 true → poll 应 show
    calls.clear()
    pv.set_pet_visible(shared, "角色B", True)
    shell._poll_pet_visibility()
    assert "show" in calls, calls

    # 3) 稳态 hidden + 窗被托盘直接 show（无新边沿）→ 补写 true，不 hide
    calls.clear()
    pv.set_pet_visible(shared, "角色B", False)
    shell._poll_pet_visibility()   # 先让 seen 跟上 false
    calls.clear()
    visible = True                  # 模拟托盘直接把窗 show 了（没写状态）
    shell._poll_pet_visibility()
    assert "hide" not in calls, calls
    assert pv.read_visibility(shared)["角色B"] is True  # 补写可见事实


def test_sync_island_settings_from_master(tmp_path):
    """主配置（独立设置进程写）的岛设置要同步进实例配置（岛读的那份）。

    用户改「信息栏显示什么=自定义短文本」后主配置变了，但实例配置还停在 time，
    岛仍显示时间（「改了没用」）。同步时位置键 x/y/dock_edge 不覆盖。
    """
    from types import SimpleNamespace
    from pet.app import AppShell
    from pet.config import Config

    d = tmp_path / "wanzhou-pet"
    d.mkdir()
    master = Config(base=tmp_path, instance_id="")
    master.set("dynamic_island", {
        "enabled": True, "info_mode": "custom", "custom_text": "你好",
        "accent": "green", "x": 0, "y": 0, "dock_edge": "top",
    })
    master.set("island_metrics", ["cpu", "mem"])
    master.save()
    inst_cfg = Config(base=tmp_path, instance_id="角色A")
    inst_cfg.set("dynamic_island", {
        "enabled": True, "info_mode": "time", "custom_text": "",
        "accent": "blue", "x": 921, "y": 100, "dock_edge": "none",
    })
    inst_cfg.set("island_metrics", [])
    inst_cfg.save()

    shell = AppShell.__new__(AppShell)
    shell.config = Config(base=tmp_path, instance_id="角色A")
    shell._slot_id = 1

    assert shell._sync_island_settings_from_master() is True
    got = Config(base=tmp_path, instance_id="角色A")
    di = got.get("dynamic_island")
    assert di["info_mode"] == "custom"
    assert di["custom_text"] == "你好"
    assert di["accent"] == "green"
    # 位置键保留实例自己的值（主配置 x=0/y=0 是假的，覆盖会弹回原点）
    assert di["x"] == 921 and di["y"] == 100 and di["dock_edge"] == "none"
    assert got.get("island_metrics") == ["cpu", "mem"]
    # 第二次同步：无变化 → False（避免 watcher 自触发循环）
    shell.config = Config(base=tmp_path, instance_id="角色A")
    assert shell._sync_island_settings_from_master() is False


def test_sync_island_settings_from_master(tmp_path):
    """主配置（独立设置进程写）的岛设置要同步进实例配置（岛读的那份）。

    用户改「信息栏显示什么=自定义短文本」后主配置变了，但实例配置还停在 time，
    岛仍显示时间（「改了没用」）。同步时位置键 x/y/dock_edge 不覆盖。
    """
    from types import SimpleNamespace
    from pet.app import AppShell
    from pet.config import Config

    d = tmp_path / "wanzhou-pet"
    d.mkdir()
    master = Config(base=tmp_path, instance_id="")
    master.set("dynamic_island", {
        "enabled": True, "info_mode": "custom", "custom_text": "你好",
        "accent": "green", "x": 0, "y": 0, "dock_edge": "top",
    })
    master.set("island_metrics", ["cpu", "mem"])
    master.save()
    inst_cfg = Config(base=tmp_path, instance_id="角色A")
    inst_cfg.set("dynamic_island", {
        "enabled": True, "info_mode": "time", "custom_text": "",
        "accent": "blue", "x": 921, "y": 100, "dock_edge": "none",
    })
    inst_cfg.set("island_metrics", [])
    inst_cfg.save()

    shell = AppShell.__new__(AppShell)
    shell.config = Config(base=tmp_path, instance_id="角色A")
    shell._slot_id = 1

    assert shell._sync_island_settings_from_master() is True
    got = Config(base=tmp_path, instance_id="角色A")
    di = got.get("dynamic_island")
    assert di["info_mode"] == "custom"
    assert di["custom_text"] == "你好"
    assert di["accent"] == "green"
    # 位置键保留实例自己的值（主配置 x=0/y=0 是假的，覆盖会弹回原点）
    assert di["x"] == 921 and di["y"] == 100 and di["dock_edge"] == "none"
    assert got.get("island_metrics") == ["cpu", "mem"]
    # 第二次同步：无变化 → False（避免 watcher 自触发循环）
    shell.config = Config(base=tmp_path, instance_id="角色A")
    assert shell._sync_island_settings_from_master() is False
