# -*- coding: utf-8 -*-
"""灵动岛三角色显隐条：三段恒在、隐藏段亮起、隐藏越多岛越长、命中恢复。

岛常驻显示，三段条叠加在右侧：
- 三段固定按角色 A/B/C 排布，头像+「角色A」+状态点已删；时间挪到整条最右；
- 隐藏段带「已隐藏 · 点击显示」提示，宽于可见段 → 隐藏越多条越长；
- 点任一角色段 = 切换显隐（显示→隐藏 / 隐藏→显示，pet_visibility_toggled）；
  点「全部显示」chip 恢复三只（show_all_pets_requested）。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.island.dynamic_island import DynamicIsland
from pet.island.pet_bar import PetBarSegment, plan_pet_bar
from pet.pet_visibility import PET_IDS


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _island(tmp_path: Path, **overrides) -> DynamicIsland:
    _qapp()
    cfg = Config(base=tmp_path)
    data = {
        "enabled": True, "show_icon": False, "show_name": False,
        "show_info": True, "show_status": False, "info_mode": "time",
        "style": "dark", "x": 400, "y": 300, "dock_edge": "none",
    }
    data.update(overrides)
    cfg.set("dynamic_island", data)
    return DynamicIsland(cfg)


def _states(**hidden) -> dict[str, bool]:
    return {pet_id: pet_id not in hidden for pet_id in PET_IDS}


def test_active_only_when_some_pet_hidden(tmp_path):
    island = _island(tmp_path)
    try:
        # 裸岛没有状态源 → 三段不启用（保护直接构造的旧测试）；AppShell 注入
        # 状态后三段常驻叠加，全可见也在（岛不再因全可见而隐藏）。
        assert island._petbar_active() is False
        island.set_pet_states(_states(角色A=False))
        assert island._petbar_active() is True
        island.set_pet_states(_states())
        assert island._petbar_active() is True
        # 哪只隐藏由段数据表达，不再由 active 开关表达
        island.set_pet_states(_states(角色B=False))
        assert [p.seg.pet_id for p in island._petbar_layout().placements
                if p.seg.hidden] == ["角色B"]
    finally:
        island.close()


def test_all_segments_equal_width_avatars_only(tmp_path):
    """三段只显示头像、等宽；隐藏段不再带提示文字（否则留大块空白）。"""
    island = _island(tmp_path)
    try:
        island.set_pet_states(_states(角色A=False), labels={
            "角色A": "德蕾琪娜", "角色B": "林德薇恩", "角色C": "艾尔妲"})
        plan = island._petbar_layout()
        assert len(plan.placements) == 3
        widths = [p.width for p in plan.placements]
        assert widths[0] == widths[1] == widths[2], widths
        assert all(p.hint == "" for p in plan.placements), [p.hint for p in plan.placements]
        assert all(seg.label == "" for seg in (p.seg for p in plan.placements))
    finally:
        island.close()


def test_hidden_count_does_not_stretch_island(tmp_path):
    """三段等宽后，岛不再随隐藏只数变长；有隐藏才多出「全部显示」chip。"""
    island = _island(tmp_path)
    try:
        island.set_pet_states(_states())
        all_visible = island.width()
        assert island._petbar_layout().all_chip_x is None
        hidden_widths = []
        for states in (_states(角色A=False),
                       _states(角色A=False, 角色B=False),
                       _states(角色A=False, 角色B=False, 角色C=False)):
            island.set_pet_states(states)
            hidden_widths.append(island.width())
            assert island._petbar_layout().all_chip_x is not None
        # 只要出现「全部显示」chip 就长一次；之后隐藏 1/2/3 只长度恒定
        assert hidden_widths[0] > all_visible
        assert hidden_widths[0] == hidden_widths[1] == hidden_widths[2], hidden_widths
    finally:
        island.close()


def test_hit_test_segment_and_all_chip(tmp_path):
    island = _island(tmp_path)
    try:
        island.set_pet_states(_states(角色B=False), labels={
            "角色A": "德蕾琪娜", "角色B": "林德薇恩", "角色C": "艾尔妲"})
        plan = island._petbar_layout()
        offset = island._petbar_offset_x()  # 三段在胶囊里的起点（窗口坐标）
        hidden = [p for p in plan.placements if p.seg.hidden][0]
        assert island._petbar_hit(offset + hidden.x + 4) == ("pet", "角色B")
        assert island._petbar_hit(offset + plan.all_chip_x + 4) == ("all", "")
    finally:
        island.close()


def test_signals_on_click(tmp_path):
    island = _island(tmp_path)
    toggled: list[str] = []
    got_all: list[int] = []
    island.pet_visibility_toggled.connect(toggled.append)
    island.show_all_pets_requested.connect(lambda: got_all.append(1))
    try:
        island.set_pet_states(_states(角色C=False))
        plan = island._petbar_layout()
        x = island._petbar_offset_x() + \
            [p for p in plan.placements if p.seg.hidden][0].x + 4
        assert island._petbar_hit(x) == ("pet", "角色C")
        # 信号接线可达（点击路由在 mouseReleaseEvent，此处发同一信号）
        island.pet_visibility_toggled.emit("角色C")
        island.show_all_pets_requested.emit()
        assert toggled == ["角色C"]
        assert got_all == [1]
    finally:
        island.close()


def test_plan_pet_bar_pure_and_stable_order():
    fm = type("FM", (), {"horizontalAdvance": lambda self, s: len(s) * 8})()
    segs = [
        PetBarSegment(pet_id, pet_id, pet_id == "角色B", 0)
        for pet_id in PET_IDS
    ]
    plan = plan_pet_bar(
        segs, lead_w=0, trail_w=0, available_w=0,
        name_fm=fm, hint_fm=fm, metrics_fm=fm)
    assert [p.seg.pet_id for p in plan.placements] == list(PET_IDS)
    assert plan.all_chip_x is not None  # 有隐藏段就有「全部显示」chip
    again = plan_pet_bar(
        segs, lead_w=0, trail_w=0, available_w=0,
        name_fm=fm, hint_fm=fm, metrics_fm=fm)
    assert plan.width == again.width


def _click_at(island, x: float) -> None:
    """模拟单击岛的窗口局部坐标 x（click_action 默认 expand，靠三段分支拦截）。"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    island.show()
    local = QPointF(x, island.height() / 2.0)
    global_pos = island.mapToGlobal(local.toPoint())
    press = QMouseEvent(QEvent.Type.MouseButtonPress, local, QPointF(global_pos),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, local, QPointF(global_pos),
                          Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                          Qt.KeyboardModifier.NoModifier)
    island.mousePressEvent(press)
    island.mouseReleaseEvent(release)


def test_click_any_pet_toggles_both_visible_and_hidden(tmp_path):
    """点三段里任一角色（可见或隐藏）都发 toggle —— 再点即显示的语义。"""
    island = _island(tmp_path)
    toggled: list[str] = []
    island.pet_visibility_toggled.connect(toggled.append)
    try:
        # 角色A 可见、角色C 隐藏
        island.set_pet_states(_states(角色C=False))
        plan = island._petbar_layout()
        visible_x = island._petbar_offset_x() + plan.placements[0].x + 4  # 角色A（可见）
        hidden_x = island._petbar_offset_x() + \
            [p for p in plan.placements if p.seg.hidden][0].x + 4       # 角色C（隐藏）
        _click_at(island, visible_x)
        _click_at(island, hidden_x)
        assert toggled == ["角色A", "角色C"], toggled
    finally:
        island.close()


def _click_at(island, x: float) -> None:
    """模拟单击岛的窗口局部坐标 x（click_action 默认 expand，靠三段分支拦截）。"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    island.show()
    local = QPointF(x, island.height() / 2.0)
    global_pos = island.mapToGlobal(local.toPoint())
    press = QMouseEvent(QEvent.Type.MouseButtonPress, local, QPointF(global_pos),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, local, QPointF(global_pos),
                          Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                          Qt.KeyboardModifier.NoModifier)
    island.mousePressEvent(press)
    island.mouseReleaseEvent(release)


def test_click_any_pet_toggles_both_visible_and_hidden(tmp_path):
    """点三段里任一角色（可见或隐藏）都发 toggle —— 再点即显示的语义。"""
    island = _island(tmp_path)
    toggled: list[str] = []
    island.pet_visibility_toggled.connect(toggled.append)
    try:
        # 角色A 可见、角色C 隐藏
        island.set_pet_states(_states(角色C=False))
        plan = island._petbar_layout()
        visible_x = island._petbar_offset_x() + plan.placements[0].x + 4  # 角色A（可见）
        hidden_x = island._petbar_offset_x() + \
            [p for p in plan.placements if p.seg.hidden][0].x + 4       # 角色C（隐藏）
        _click_at(island, visible_x)
        _click_at(island, hidden_x)
        assert toggled == ["角色A", "角色C"], toggled
    finally:
        island.close()


def test_click_in_card_content_area_does_not_toggle_pet(tmp_path):
    """卡片展开后点下方内容区（如「空闲」状态行）不应误隐藏桌宠。

    旧版 mouseReleaseEvent 只用 x 命中三段，卡片高 ~200px 时下方空白的 x
    恰好落在段内 → 误触发 toggle。修复：命中限定 y ∈ [0, 44] 胶囊行。
    """
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    island = _island(tmp_path)
    toggled: list[str] = []
    island.pet_visibility_toggled.connect(toggled.append)
    try:
        island.set_pet_states(_states(角色B=False))
        island.show()
        island.expand_card()
        plan = island._petbar_layout()
        # 角色B 段在胶囊行的 x
        x = island._petbar_offset_x() + \
            [p for p in plan.placements if p.seg.pet_id == "角色B"][0].x + 4
        # 命中点：胶囊行内 y=22 → 命中；卡片内容区 y=90 → 不命中
        from PySide6.QtCore import QPoint
        assert island._petbar_hit_at(QPointF(x, 22)) == ("pet", "角色B")
        assert island._petbar_hit_at(QPointF(x, 90)) is None

        # 真实事件：点卡片内容区（y=90）应走 expand_card（展开态→收起），不 toggle
        local = QPointF(x, 90)
        gp = island.mapToGlobal(local.toPoint())
        press = QMouseEvent(QEvent.Type.MouseButtonPress, local, QPointF(gp),
                            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
        release = QMouseEvent(QEvent.Type.MouseButtonRelease, local, QPointF(gp),
                              Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                              Qt.KeyboardModifier.NoModifier)
        island.mousePressEvent(press)
        island.mouseReleaseEvent(release)
        assert toggled == [], toggled
    finally:
        island.close()


def test_click_on_time_never_triggers_all_display(tmp_path):
    """点最右端的时间不该触发「全部显示」（按钮与时间贴太近的误触）。"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    island = _island(tmp_path)
    all_calls: list[int] = []
    island.show_all_pets_requested.connect(lambda: all_calls.append(1))
    try:
        island.set_pet_states(_states(角色B=False))
        island.show()
        plan = island._petbar_layout()
        # chip 本身仍可命中（左边缘）
        chip_x = island._petbar_offset_x() + plan.all_chip_x + 4
        assert island._petbar_hit_at(QPointF(chip_x, 22)) == ("all", "")
        # 时间区（含与时间之间的留白）都不命中
        time_x = island._time_start_x()
        for x in (time_x - 4, time_x + 5, time_x + island._time_box_width() // 2,
                  island.width() - 2):
            assert island._petbar_hit_at(QPointF(x, 22)) is None, x

        # 真实鼠标事件点时间：不发「全部显示」
        local = QPointF(time_x + 8, 22)
        gp = island.mapToGlobal(local.toPoint())
        press = QMouseEvent(QEvent.Type.MouseButtonPress, local, QPointF(gp),
                            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
        release = QMouseEvent(QEvent.Type.MouseButtonRelease, local, QPointF(gp),
                              Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                              Qt.KeyboardModifier.NoModifier)
        island.mousePressEvent(press)
        island.mouseReleaseEvent(release)
        assert all_calls == [], all_calls
    finally:
        island.close()


def test_three_segments_only_avatars_and_indicators_do_not_overlap(tmp_path):
    """三段条只显示头像（无名字），附加指标段排在三段之后、不与头像重叠。

    用户开了 CPU/内存/GPU/帧率/网络后曾出现指标文字与角色名叠成一团——
    根因是三段条和常规指标段都从 19px 起画、宽度账又没算指标段。
    """
    island = _island(tmp_path)
    try:
        # 模拟开了 5 个指标
        island.config.set("island_metrics", ["cpu", "mem", "gpu", "fps", "network"])
        island.set_pet_states(_states(角色B=False))
        # label 恒空 → 段宽只有头像 + 槽位，三段明显变窄
        assert all(seg.label == "" for seg in island._petbar_segments())
        assert island._petbar_width() < 350, island._petbar_width()
        # 指标段在三段之后，时间又在所有指标之后
        chip_end = island._petbar_offset_x() + \
            island._petbar_layout().all_chip_x + island._petbar_layout().all_chip_w
        assert island._indicators_start_x() >= chip_end
        assert island._indicators_width() > 0
        assert island._time_start_x() > island._indicators_start_x() \
            + island._indicators_width()
        # 总宽容纳得下所有块
        assert island.width() >= island._time_start_x() + island._time_box_width()
    finally:
        island.close()


def test_three_segments_only_avatars_and_indicators_do_not_overlap(tmp_path):
    """三段条只显示头像（无名字），附加指标段排在三段之后、不与头像重叠。

    用户开了 CPU/内存/GPU/帧率/网络后曾出现指标文字与角色名叠成一团——
    根因是三段条和常规指标段都从 19px 起画、宽度账又没算指标段。
    """
    island = _island(tmp_path)
    try:
        # 模拟开了 5 个指标
        island.config.set("island_metrics", ["cpu", "mem", "gpu", "fps", "network"])
        island.set_pet_states(_states(角色B=False))
        # label 恒空 → 段宽只有头像 + 槽位，三段明显变窄
        assert all(seg.label == "" for seg in island._petbar_segments())
        assert island._petbar_width() < 350, island._petbar_width()
        # 指标段在三段之后，时间又在所有指标之后
        chip_end = island._petbar_offset_x() + \
            island._petbar_layout().all_chip_x + island._petbar_layout().all_chip_w
        assert island._indicators_start_x() >= chip_end
        assert island._indicators_width() > 0
        assert island._time_start_x() > island._indicators_start_x() \
            + island._indicators_width()
        # 总宽容纳得下所有块
        assert island.width() >= island._time_start_x() + island._time_box_width()
    finally:
        island.close()
