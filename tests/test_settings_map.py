# -*- coding: utf-8 -*-
"""设置「功能地图」：全部设置可浏览、可按口语搜到、双击跳回原位置。

这里钉的是**发现层**而不是配置语义：不新增/搬动任何设置行，所有断言都落在公开
UI seam（侧栏按钮、地图窗口、跳转后的域/标签/高亮）上。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QTreeWidgetItem  # noqa: E402

import pet.modern_settings_dialog as settings_mod  # noqa: E402
from pet import settings_map  # noqa: E402
from pet.config import Config  # noqa: E402
from pet.settings_widgets import SettingRow  # noqa: E402

app = QApplication.instance() or QApplication([])


def _dialog(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod.autostart_mod, "is_enabled", lambda: False)
    dialog = settings_mod.ModernSettingsDialog(Config(base=tmp_path), include_ai=True)
    dialog.show()
    app.processEvents()
    return dialog


def _leaves(item: QTreeWidgetItem) -> list[QTreeWidgetItem]:
    found = []
    if isinstance(item.data(0, Qt.ItemDataRole.UserRole), dict):
        found.append(item)
    for index in range(item.childCount()):
        found.extend(_leaves(item.child(index)))
    return found


def _all_leaves(window) -> list[QTreeWidgetItem]:
    return [leaf for index in range(window.tree.topLevelItemCount())
            for leaf in _leaves(window.tree.topLevelItem(index))]


def _visible_leaves(window) -> list[QTreeWidgetItem]:
    return [leaf for leaf in _all_leaves(window) if not leaf.isHidden()]


def test_map_button_and_shortcut_open_one_browsable_window(tmp_path, monkeypatch):
    dialog = _dialog(tmp_path, monkeypatch)
    window = None
    try:
        button = dialog.findChild(QPushButton, "settingsMapButton")
        assert button is not None, "页头缺少「功能地图」入口"
        button.click()
        app.processEvents()
        window = dialog._settings_map_window
        assert window is not None and window.isVisible()

        domains = [window.tree.topLevelItem(i).text(0)
                   for i in range(window.tree.topLevelItemCount())]
        for index in range(dialog.sidebar.count()):
            assert dialog.sidebar.item(index).text() in domains
        assert "常用操作" not in domains, "命令按钮不是设置域，不该混进域树"

        labels = [leaf.text(0) for leaf in _all_leaves(window)]
        for expected in ("桌宠大小", "启用灵动岛", "点击音效"):
            assert any(expected in label for label in labels), f"地图里找不到「{expected}」"
        # 常用操作改成搜索框下的固定按钮排，不进树。
        for name in ("mapCmdApply", "mapCmdResetPet", "mapCmdResetGlobal"):
            command = window.findChild(QPushButton, name)
            assert command is not None and command.isVisible(), f"缺少常用操作按钮 {name}"
        # 2026-11-24：「功能」总开关页从侧栏移除，功能卡片不再登记进地图
        # （地图只遍历侧栏实际挂载的页）；各功能由自己的具体设置行进入。
        cards = [leaf for leaf in _all_leaves(window)
                 if leaf.data(0, Qt.ItemDataRole.UserRole)["widget"].objectName().startswith("featureCard_")]
        assert not cards, f"功能卡片不应再出现在地图里：{len(cards)} 张"
        assert window.status.text().startswith("共 ")
    finally:
        if window is not None:
            window.close()
        dialog.close()


def test_map_search_finds_spoken_name_and_jumps_to_the_exact_row(tmp_path, monkeypatch):
    dialog = _dialog(tmp_path, monkeypatch)
    window = None
    try:
        window = settings_map.open_map(dialog)
        app.processEvents()
        window.search.setText("网速")
        app.processEvents()
        matches = _visible_leaves(window)
        assert matches, "「网速」一条都没找到"
        # 「网速」既命中灵动岛指标行，也命中介绍里写到网速的功能卡片；
        # 这里只钉用户真正要改的那条设置行。
        target = next(
            leaf for leaf in matches
            if leaf.data(0, Qt.ItemDataRole.UserRole)["widget"].objectName()
            == "settingRow_island_network")
        assert "灵动岛指标 · 网络" in target.text(0)
        # 第二列只写所属分组，完整路径放 tooltip（不再每行重复一遍长路径）。
        assert "桌面胶囊（灵动岛）" in target.text(1)
        assert "灵动岛 › 桌面胶囊（灵动岛）" in target.toolTip(0)

        window.tree.setCurrentItem(target)
        window.jump_button.click()
        app.processEvents()
        assert not window.isVisible(), "跳转后地图应关闭，把界面交还给设置页"
        assert dialog.sidebar.currentItem().text() == "灵动岛"
        row = dialog.findChild(SettingRow, "settingRow_island_network")
        assert row.property("searchMatch") is True, "跳过去的那一行应被高亮"
        assert row.isVisibleTo(dialog), "命中行应真的滚进视口"
    finally:
        if window is not None:
            window.close()
        dialog.close()


def test_map_commands_locate_buttons_without_executing_them(tmp_path, monkeypatch):
    """常用操作只定位到原按钮；尤其「重置」绝不能被找功能时误触。"""
    dialog = _dialog(tmp_path, monkeypatch)
    window = None
    try:
        window = settings_map.open_map(dialog)
        app.processEvents()
        command = window.findChild(QPushButton, "mapCmdApply")
        assert command is not None
        command.click()
        app.processEvents()
        # offscreen 平台没有真正的活动窗口，hasFocus() 恒为 False；钉住能确定的部分：
        # 地图已关闭，且目标按钮就在当前可见的设置窗里（真实桌面上再 setFocus）。
        assert not window.isVisible()
        assert dialog.apply_to_others_btn.isVisibleTo(dialog)
        assert dialog.apply_to_others_btn.isEnabled()

        reset_clicks = []
        dialog.reset_defaults_btn.clicked.connect(lambda: reset_clicks.append(1))
        window = settings_map.open_map(dialog)
        app.processEvents()
        window.findChild(QPushButton, "mapCmdResetPet").click()
        app.processEvents()
        assert not reset_clicks, "地图里的「重置本宠设置」不能真的执行"
        assert not window.isVisible()
    finally:
        if window is not None:
            window.close()
        dialog.close()


def test_sidebar_tooltips_explain_the_short_domain_names(tmp_path, monkeypatch):
    dialog = _dialog(tmp_path, monkeypatch)
    try:
        for index in range(dialog.sidebar.count()):
            item = dialog.sidebar.item(index)
            hint = settings_map.DOMAIN_HINTS.get(item.text(), "")
            assert hint and item.toolTip() == hint, f"「{item.text()}」缺少侧栏解释"
    finally:
        dialog.close()


def _expanded_rows(window) -> int:
    """树里实际铺开的行数（收起分支的子节点不算）。"""
    def count(item):
        total = 1
        if item.isExpanded():
            for index in range(item.childCount()):
                total += count(item.child(index))
        return total
    return sum(count(window.tree.topLevelItem(i))
               for i in range(window.tree.topLevelItemCount()))


def test_map_first_screen_only_expands_current_domain_and_tab(tmp_path, monkeypatch):
    """首屏只展开当前域（有页内标签的只展开当前标签），清空搜索后仍回到这个态。"""
    from pet.settings_widgets import SettingsTabContainer

    dialog = _dialog(tmp_path, monkeypatch)
    window = None
    try:
        dialog.sidebar.setCurrentRow(2)  # 「动作与碰撞」域：无页内标签
        app.processEvents()
        window = settings_map.open_map(dialog)
        app.processEvents()
        roots = [window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())]
        assert [r.text(0) for r in roots if r.isExpanded()] == ["动作与碰撞"]
        baseline = _expanded_rows(window)
        assert baseline < 30, f"首屏仍铺了 {baseline} 行"
        assert window.tree.columnWidth(1) <= 180, "第二列又被长路径撑宽了"

        # 有页内标签的域：只展开当前那一个标签，其余标签收起。
        dialog.sidebar.setCurrentRow(3)  # 「互动」域
        app.processEvents()
        tabs = dialog.pages.widget(3).findChild(SettingsTabContainer, "settingsTaskTabs")
        expected_tab = tabs.labels()[tabs.keys().index(tabs.currentKey())]
        window.close()
        window = settings_map.open_map(dialog)
        app.processEvents()
        interaction = next(window.tree.topLevelItem(i)
                           for i in range(window.tree.topLevelItemCount())
                           if window.tree.topLevelItem(i).text(0) == "互动")
        opened = [interaction.child(i).text(0)
                  for i in range(interaction.childCount())
                  if interaction.child(i).isExpanded()]
        assert opened == [expected_tab], (opened, expected_tab)
        interaction_baseline = _expanded_rows(window)

        # 搜索命中时展开命中路径，清空后复原，不把上一轮展开态留在屏幕上。
        window.search.setText("网速")
        app.processEvents()
        assert _expanded_rows(window) > interaction_baseline, "搜索命中路径没有展开"
        window.search.setText("")
        app.processEvents()
        roots = [window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())]
        assert [r.text(0) for r in roots if r.isExpanded()] == ["互动"]
        assert _expanded_rows(window) == interaction_baseline
    finally:
        if window is not None:
            window.close()
        dialog.close()
