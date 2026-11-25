# -*- coding: utf-8 -*-
"""「显示」「动作与碰撞」两个一级域的回归。

原「桌宠」是含两个页内标签的域；现在两个任务直接提升为侧栏一级域，用户不必
先点分组再点标签。这里钉住四件事：

1. 侧栏有这两项、没有「桌宠」；每行都落在其中一个域，且两页互不串线；
2. 每页内组序：主视线组在前、高级组垫底；高级组默认收起但行仍在；
3. 搜索命中任一页的行时切到那一页，并展开折叠组让命中行真正可见；
4. 保存 round trip 不变——拆域只改呈现，不碰配置键、默认值与保存链。
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

DOMAIN_DISPLAY = "显示"
DOMAIN_MOTION = "动作与碰撞"

DISPLAY_ROWS = ("scale", "bubble_text_scale", "pet_opacity")
MOTION_PRIMARY_ROWS = (
    "playback_speed", "animation_gap", "idle_low_fps",
    "drag_physics", "throw_strength", "slingshot_enabled",
    "edge_probe", "collision_enabled", "collision_sound_enabled",
)
MOTION_ADVANCED_ROWS = (
    "collision_restitution", "collision_friction", "collision_mass_scale",
    "collision_impulse_cap", "collision_sound_volume",
)
MOTION_SECTIONS = (
    "动画与移动", "拖拽与弹射", "边缘探头", "多开碰撞", "碰撞参数（高级）",
)


def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(tmp_path, monkeypatch):
    import pet.modern_settings_dialog as settings_mod
    from pet.config import Config
    from pet.settings_slot_config import route_settings_config

    app = _qapp()
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    dlg = settings_mod.ModernSettingsDialog(
        route_settings_config(Config(base=tmp_path, instance_id="slot-0")),
        include_ai=True)
    yield dlg
    dlg.close()
    app.processEvents()


def _sidebar(dialog):
    return [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())]


def _domain_page(dialog, domain: str):
    index = next(i for i, name in enumerate(_sidebar(dialog)) if name == domain)
    return dialog.pages.widget(index)


def _row(dialog, key):
    from pet.modern_settings_dialog import SettingRow

    found = dialog.findChild(SettingRow, f"settingRow_{key}")
    assert found is not None, f"缺少设置行 {key}"
    return found


def _section_title(section) -> str:
    from PySide6.QtWidgets import QLabel

    if section.toggle is not None:  # 高级组：标题在 disclosure 按钮上
        return section.toggle.text()
    label = section.findChild(QLabel, "sectionTitle")
    return label.text() if label is not None else ""


def _sections_of(page):
    """按真实布局顺序取滚动内容里的 ``SettingsSection``。"""
    from PySide6.QtWidgets import QScrollArea

    from pet.settings_widgets import SettingsSection

    scroll = page.findChild(QScrollArea, "settingsScroll")
    root = scroll.widget()
    return [root.layout().itemAt(i).widget()
            for i in range(root.layout().count())
            if isinstance(root.layout().itemAt(i).widget(), SettingsSection)]


def _section_of(row):
    from pet.modern_settings_dialog import SettingsSection

    parent = row.parentWidget()
    while parent is not None and not isinstance(parent, SettingsSection):
        parent = parent.parentWidget()
    assert parent is not None, f"{row.objectName()} 必须落在某个 SettingsSection 内"
    return parent


def test_two_sidebar_domains_replace_the_pet_group(dialog):
    names = _sidebar(dialog)
    assert DOMAIN_DISPLAY in names and DOMAIN_MOTION in names
    assert "桌宠" not in names, "「桌宠」分组应已提升为两个一级域"
    assert names.index(DOMAIN_DISPLAY) + 1 == names.index(DOMAIN_MOTION)


def test_group_order_puts_the_advanced_group_last(dialog):
    display_sections = _sections_of(_domain_page(dialog, DOMAIN_DISPLAY))
    assert _section_title(display_sections[0]) == "显示"
    assert display_sections[0].advanced is False
    # 音乐模块激活时还会挂出「音乐关联」/播放器路径组；高级组若存在必须垫底。
    advanced_positions = [i for i, section in enumerate(display_sections) if section.advanced]
    if advanced_positions:
        assert advanced_positions == list(range(advanced_positions[0], len(display_sections)))

    motion_sections = _sections_of(_domain_page(dialog, DOMAIN_MOTION))
    assert [_section_title(section) for section in motion_sections] == list(MOTION_SECTIONS)
    assert all(section.advanced is False for section in motion_sections[:-1])
    assert motion_sections[-1].advanced is True


def test_every_row_lives_in_its_own_domain_and_is_reachable(dialog):
    display_page = _domain_page(dialog, DOMAIN_DISPLAY)
    motion_page = _domain_page(dialog, DOMAIN_MOTION)

    for key in DISPLAY_ROWS:
        row = _row(dialog, key)
        assert display_page.isAncestorOf(row), f"{key} 应在「{DOMAIN_DISPLAY}」页"
        assert not motion_page.isAncestorOf(row)
        assert row.isVisibleTo(display_page), f"{key} 在显示页里不可见"

    for section in _sections_of(motion_page):
        if section.advanced:
            section.toggle.setChecked(True)  # 高级组默认收起
    _qapp().processEvents()
    for key in MOTION_PRIMARY_ROWS + MOTION_ADVANCED_ROWS:
        row = _row(dialog, key)
        assert motion_page.isAncestorOf(row), f"{key} 应在「{DOMAIN_MOTION}」页"
        assert not display_page.isAncestorOf(row)
        assert row.isVisibleTo(motion_page), f"{key} 在动作页里不可见"


def _search(dialog, query: str):
    dialog.search_edit.setText("")
    _qapp().processEvents()
    dialog.search_edit.setText(query)
    for _ in range(3):
        _qapp().processEvents()
    matches = dialog._search_matches
    assert matches, f"搜索「{query}」没有命中任何行"
    return matches[dialog._search_index]


def test_search_switches_to_the_domain_that_owns_the_hit(dialog):
    for query, key, domain in (
        ("碰撞开关", "collision_enabled", DOMAIN_MOTION),
        ("桌宠大小", "scale", DOMAIN_DISPLAY),
    ):
        row = _search(dialog, query)
        assert row.objectName() == f"settingRow_{key}"
        assert dialog.sidebar.currentItem().text() == domain
        assert row.isVisibleTo(_domain_page(dialog, domain))


def test_search_expands_the_advanced_group_on_the_hit(dialog):
    row = _search(dialog, "碰撞音量")
    assert row.objectName() == "settingRow_collision_sound_volume"
    assert dialog.sidebar.currentItem().text() == DOMAIN_MOTION
    section = _section_of(row)
    assert section.advanced is True
    assert _section_title(section) == "碰撞参数（高级）"
    assert section.toggle.isChecked() is True, "命中折叠组内的行必须自动展开"
    assert row.isVisibleTo(_domain_page(dialog, DOMAIN_MOTION))


def test_pet_settings_save_round_trip_is_unchanged(dialog, tmp_path):
    _row(dialog, "collision_enabled").control.setChecked(False)
    _row(dialog, "drag_physics").control.setChecked(True)

    dialog._save()
    _qapp().processEvents()

    from pet.config import Config
    from pet.settings_slot_config import route_settings_config

    saved = route_settings_config(Config(base=tmp_path, instance_id="slot-0"))
    assert saved.get("collision_enabled") is False
    assert saved.get("drag_physics") is True
