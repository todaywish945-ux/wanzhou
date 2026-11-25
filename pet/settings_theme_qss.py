# -*- coding: utf-8 -*-
"""Modern settings 主题 QSS 常量与组装。

从 modern_settings_dialog.py 纯机械搬移。_system_dark / BROWSER_CONTROL_STYLESHEET
在 settings_widgets 中定义，被 _settings_stylesheet 引用；_DARK_POPUP_OVERRIDE 亦属
settings_widgets（本模块未引用）。

视觉口径（2026-11-25）：本项目的设置窗走「暮灯」暖色系，而不是常见的中性灰 +
蓝色开关。侧栏选中态仍保留 3px 左条，但底色/卡片/控件都带一点棕紫暖调；分组标题
左缘与页标题下的短线共用金色点缀，开关选中也从蓝改为琥珀金。QDialog 深色底
``#202024`` 是既有回归契约，保留；真正铺满内容区的是后面的 QStackedWidget 规则。
"""
from __future__ import annotations

from .settings_widgets import _system_dark, BROWSER_CONTROL_STYLESHEET


_DARK_OVERRIDE = """
/* QDialog 的 #202024 是既有回归契约，不能动；内容区真正铺出来的是下面这张
   偏棕紫的桌面，和参考项目的中性灰拉开一点距离。 */
QDialog { background: #202024; color: #f2e8dc; }
QFrame#sidebarPane { background: #27242a; border-right: 1px solid #473b3d; }
QLabel#settingsVersion { color: #a69a91; font-size: 11px; padding-top: 4px; }
QFrame#updateStatusCard, QFrame#updateNotesCard { background: #2e2830; border: 1px solid #473b45; border-radius: 14px; }
QLabel#updateCurrentVersion, QLabel#updateNotesTitle { color: #f7e8c9; font-weight: 600; }
QLabel#updateStatus, QLabel#updateIntro, QLabel#updateNotes { color: #b4a79f; }
QStackedWidget { background: #221e24; }
QLineEdit#settingsSearch {
    background: #302a2e; color: #f6ead4;
    border: 1px solid #5b4a42; border-radius: 16px;
}
QListWidget#settingsSidebar::item { color: #c2b7ae; }
QListWidget#settingsSidebar::item:hover { background: #30292e; color: #f6e5c4; }
/* 选中指示：3px 强调色左条（色值由 SETTINGS_SELECTION_ACCENT 现算）。
   左侧内边距同步减 3px，文字位置与未选中行逐像素一致，选中时不会左右跳。
   声明顺序在 :hover 之后——悬停已选中行时仍按选中态画。 */
QListWidget#settingsSidebar::item:selected {
    background: #443338;
    color: #fff4dc;
    border-left: 3px solid @selection-accent@;
    padding-left: 7px;
}
QWidget#settingsTaskTabBar {
    background: #302a2e;
    border: none;
    border-radius: 10px;
}
QPushButton#settingsTaskTab {
    min-height: 32px;
    padding: 0 16px;
    font-size: 13px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: #b6a9a1;
}
QPushButton#settingsTaskTab:hover { background: #3d3334; color: #f7e8c9; }
QPushButton#settingsTaskTab:checked {
    background: #4a3b35;
    border-color: #6b5545;
    color: #fff4dc;
    font-weight: 600;
}
QPushButton#settingsTaskTab:focus { border: 2px solid #0a84ff; }
QPushButton#settingsPageAnchor {
    min-height: 24px;
    padding: 0 10px;
    font-size: 12px;
    background: #302a2e;
    border: 2px solid transparent;
    border-radius: 12px;
    color: #c2b7ae;
}
QPushButton#settingsPageAnchor:hover { background: #443833; color: #f7e8c9; }
QPushButton#settingsPageAnchor:focus { border-color: #0a84ff; }
QFrame#pageTitleAccent {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #ffd613, stop:1 rgba(255, 214, 19, 0));
    border: none;
    border-radius: 2px;
}
QLabel#pageTitle { color: #f7e8c9; }
QLabel#sectionTitle {
    color: #f3dfb5;
    border-left: 3px solid #a27b45;
    padding-left: 9px;
}
QLabel#sectionDescription { color: #a99c94; }
QFrame#settingsCard {
    background: #2c2730;
    border: 1px solid #463b46;
    border-top: 2px solid #6c5845;
    border-radius: 14px;
}
QFrame#cardSeparator { background: #3b333c; }
QLabel#settingLabel { color: #f0e4d4; }
QLabel#settingHint { color: #b0a29b; }
QLabel#quickLaunchName { color: #f0e4d4; }
QLabel#quickLaunchDetail, QLabel#quickLaunchCount, QLabel#quickLaunchEmpty,
QLabel#menuLayoutEditorLabel, QLabel#menuLayoutPreviewLabel,
QLabel#menuLayoutEditorHint { color: #b4a79f; }
QLabel#quickLaunchEmpty { background: #2a252b; border-color: #4b3e46; }
QFrame#menuLayoutEditorPanel, QFrame#menuLayoutPreviewPanel {
    background: #2a252b; border: 1px solid #4b3e46; border-radius: 12px;
}
QFrame#imagePreviewDrawer {
    background: #282329; border: none; border-left: 1px solid #4d4047;
}
QScrollArea#imagePreviewScroll, QScrollArea#imagePreviewScroll > QWidget > QWidget,
QWidget#imageMasonryFlow { background: transparent; }
QLabel#imagePreviewTitle { color: #f7e8c9; font-size: 16px; font-weight: 600; }
QLabel#imagePreviewCount, QLabel#imagePreviewPath { color: #a99c94; }
QLabel#imagePreviewEmpty { color: #a99c94; }
QPushButton#imagePreviewClose { background: transparent; border: none; font-size: 20px; }
QPushButton#imagePreviewClose:hover { background: #443833; }
QLabel#settingLabel:disabled, QLabel#settingHint:disabled { color: #746a6b; }
SettingRow[searchMatch="true"] { background: #493c36; }
QListWidget#quickLaunchList { background: #2a252b; border: 1px solid #4b3e46; }
QListWidget#quickLaunchList::item:selected { background: #4a3b35; color: #fff4dc; }
QTreeWidget#menuLayoutTree, QTreeWidget#menuLayoutPreview {
    background: #2c2730;
    border-color: #463b46;
}
QTreeWidget#menuLayoutTree::item:hover { background: #3a3036; }
QTreeWidget#menuLayoutTree::item:selected { background: #4a3b35; color: #fff4dc; }
QTreeWidget#menuLayoutTree QHeaderView::section {
    background: #342d34;
    border-bottom-color: #51434a;
    color: #b4a79f;
}
QLabel#menuLayoutPreviewLabel { color: #b4a79f; }
QMenu { background: #2c2730; color: #f2e8dc; border: 1px solid #57464a; }
QMenu::item:selected { background: #4a3b35; }
QPushButton { background: #3a3235; border: 1px solid #5a4b46; color: #f2e8dc; }
QPushButton:hover { background: #4a3e3c; }
QPushButton#advancedSectionToggle {
    min-height: 40px; padding: 0 38px 0 14px; text-align: left;
    background: #2c2730; border: 1px solid #463b46; border-radius: 12px;
    color: #f2e8dc; font-size: 13px; font-weight: 600;
}
QPushButton#advancedSectionToggle:hover { background: #3a3036; border-color: #6b5545; }
QPushButton#advancedSectionToggle:focus { border: 2px solid #0a84ff; }
QLabel#disclosureChevron { color: #c3a86c; font-size: 18px; background: transparent; }
QToolButton { color: #f2e8dc; }
QCheckBox, QRadioButton, QComboBox, QListWidget, QTreeWidget, QTableView { color: #f2e8dc; }
"""

_DARK_BROWSER_OVERRIDE = """
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    background: #302a2e; color: #f6ead4; border: 1px solid #5b4a42;
    border-radius: 8px;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QPlainTextEdit:hover { border-color: #7a6252; }
QSpinBox::up-button, QDoubleSpinBox::up-button { border-left: 1px solid #5b4a42; border-bottom: 1px solid #5b4a42; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #6a5758; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #8a6f63; }
"""

#: 设置窗**选中态**的强调色（选中图标 ink 与侧栏那条 3px 左条共用这一个真值，深浅各一档）。
#:
#: 「暮灯」配色的两档都是琥珀金系：深色用亮金 ``#ffd613``，落在暖棕选中行上约
#: 8.4:1；浅色用压深的琥珀棕 ``#8a7400``，落在 ``#e6e0d5`` 选中行上约 3.5:1，
#: 都高于 WCAG 1.4.11 对图形对象要求的 3:1。两档只作用于**设置窗自己的选中态**：
#: 菜单与聊天窗拿不到 Selected 图元（见 ``context_menus.icons._settings_icon_states``）。
SETTINGS_SELECTION_ACCENT: dict[bool, str] = {False: "#8a7400", True: "#ffd613"}


def settings_selection_accent(dark: bool) -> str:
    """设置窗选中态（图标 ink / 侧栏 3px 左条）的强调色，与 QSS 同源。"""
    return SETTINGS_SELECTION_ACCENT[bool(dark)]


def settings_system_dark() -> bool:
    """设置窗「跟随系统」档的深浅判定。

    设置窗 QSS（``_settings_stylesheet``）与设置窗内的矢量图标共用这一个真值：图标在
    ``ModernSettingsDialog`` 应用主题**之前**就要渲染，那时窗口上还没有 ``settingsDark``，
    只能按本档兜底；两处若各判一次，"跟随系统"下迟早会 QSS/图标不一致。
    """
    return _system_dark()


#: 选中左条强调色在 QSS 字面量里的占位记号：组装时按档替换成 ``SETTINGS_SELECTION_ACCENT``
#: （图标 ink 用的也是这一个真值，两处不可能各说各话）。用 ``str.replace`` 而不是 ``str.format``
#: ——整份 QSS 满是 ``{}``。深浅两档各只有一条 ``::item:selected`` 规则，替换的是**完整规则**
#: 里的一个声明：不新增规则、不改规则顺序。
_SELECTION_BAR_TOKEN = "@selection-accent@"


def _settings_stylesheet(theme: str = "system") -> str:
    """浅色基础 QSS + 显式控件文字色补丁；深色系统时追加深色覆盖段。"""
    light_patch = """
        QPushButton { color: #3a2f24; }
        QToolButton { color: #3a2f24; }
        QCheckBox, QRadioButton, QComboBox, QListWidget, QTreeWidget, QTableView { color: #3a2f24; }
    """
    base = _LIGHT_SETTINGS_STYLESHEET + light_patch
    dark = theme == "dark" or (theme == "system" and _system_dark())
    accent = settings_selection_accent(dark)
    if dark:
        qss = base + _DARK_OVERRIDE + BROWSER_CONTROL_STYLESHEET + _DARK_BROWSER_OVERRIDE
    else:
        qss = base + BROWSER_CONTROL_STYLESHEET
    qss = qss.replace(_SELECTION_BAR_TOKEN, accent)
    # 暮灯风格：焦点环/选中 tab 边框的蓝色规范色统一换成与选中态同一支金系。
    # 深色档用 #ffd613，浅色档用 #8a7400（浅底上对比度够）。
    focus_yellow = "#ffd613" if dark else "#8a7400"
    qss = qss.replace("#0a84ff", focus_yellow).replace("#0a7ae8", focus_yellow)
    return qss


_LIGHT_SETTINGS_STYLESHEET = """
QDialog {
    background: #fffcf7;
    color: #3a2f24;
    font-family: "SF Pro Text", ".AppleSystemUIFont", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
}
QFrame#sidebarPane {
    background: #f7f3ec;
    border: none;
    border-right: 1px solid #e6dac9;
}
QStackedWidget { background: #fffcf7; }
QWidget#aiSettingsContent { background: transparent; }
QLineEdit#settingsSearch {
    min-height: 30px;
    padding: 0 8px;
    background: #f5efe5;
    border: 1px solid #e2d3bd;
    border-radius: 16px;
    color: #3a2f24;
}
QLineEdit#settingsSearch:focus {
    border: 2px solid #0a84ff;
    padding: 0 7px;
}
QLabel#searchStatus {
    padding: 0 5px;
    color: #8a7d70;
    font-size: 11px;
}
QLabel#settingsVersion { color: #9b8d80; font-size: 11px; padding-top: 4px; }
QFrame#updateStatusCard, QFrame#updateNotesCard { background: #fffdf8; border: 1px solid #e7d9c6; border-radius: 14px; }
QLabel#updateCurrentVersion, QLabel#updateNotesTitle { color: #3a2f24; font-weight: 600; }
QLabel#updateStatus, QLabel#updateIntro, QLabel#updateNotes { color: #7d6f62; }
QListWidget#settingsSidebar {
    background: transparent;
    border: none;
    outline: none;
    font-size: 13px;
    font-weight: 500;
}
QListWidget#settingsSidebar::item {
    min-height: 26px;
    padding: 4px 10px;
    border-radius: 9px;
    color: #4e4e4e;
}
QListWidget#settingsSidebar::item:hover {
    /* 悬停只是提示：暖灰底与侧栏（#f7f3ec）只差一档，不和选中态抢视觉权重。 */
    background: #f4f0e8;
    color: #3a2f24;
}
QWidget#settingsTaskTabBar {
    background: #f3ede2;
    border: none;
    border-radius: 10px;
}
QPushButton#settingsTaskTab {
    min-height: 32px;
    padding: 0 16px;
    font-size: 13px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: #7a6c5e;
}
QPushButton#settingsTaskTab:hover { background: #ebe0cf; color: #3a2f24; }
QPushButton#settingsTaskTab:checked {
    background: #fffaf1;
    border-color: #dfcba7;
    color: #3a2f24;
    font-weight: 600;
}
QPushButton#settingsTaskTab:focus { border: 2px solid #0a84ff; }
QPushButton#settingsPageAnchor {
    min-height: 24px;
    padding: 0 10px;
    font-size: 12px;
    background: #f3ede2;
    border: 2px solid transparent;
    border-radius: 12px;
    color: #6d5c4b;
}
QPushButton#settingsPageAnchor:hover { background: #ebe0cf; color: #3a2f24; }
QPushButton#settingsPageAnchor:focus { border-color: #0a84ff; }
QListWidget#settingsSidebar::item:selected {
    background: #e6e0d5;
    color: #33271d;
    /* 选中指示：3px 琥珀金左条，色值由 SETTINGS_SELECTION_ACCENT 现算。
       左侧内边距同步减 3px，文字位置与未选中行逐像素一致，选中时不会左右跳。
       声明顺序在 :hover 之后——悬停已选中行时仍按选中态画。 */
    border-left: 3px solid @selection-accent@;
    padding-left: 7px;
}
QFrame#pageTitleAccent {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #8a7400, stop:1 rgba(138, 116, 0, 0));
    border: none;
    border-radius: 2px;
}
QLabel#pageTitle {
    font-size: 22px;
    font-weight: 600;
    color: #33271d;
}
QLabel#sectionTitle {
    font-size: 15px;
    font-weight: 600;
    padding-top: 6px;
    padding-left: 9px;
    border-left: 3px solid #c69a52;
    color: #463522;
}
QLabel#sectionDescription {
    font-size: 12px;
    color: #8a7d70;
}
QFrame#settingsCard {
    background: #fffdf8;
    border: 1px solid #e7d9c6;
    border-top: 2px solid #dfb97b;
    border-radius: 14px;
}
QFrame#cardSeparator {
    background: #ece1d2;
    border: none;
    margin-left: 14px;
    margin-right: 14px;
}
QLabel#settingLabel {
    font-size: 13px;
    font-weight: 500;
    color: #35291f;
}
QLabel#settingHint {
    font-size: 12px;
    font-weight: 400;
    color: #86786b;
}
QLabel#settingLabel:disabled, QLabel#settingHint:disabled { color: #b5a99c; }
SettingRow[searchMatch="true"] {
    background: #f5e7c4;
    border-radius: 8px;
}
QScrollArea#settingsScroll, QScrollArea#settingsScroll > QWidget > QWidget {
    background: transparent;
}
QLabel#quickLaunchCount, QLabel#menuLayoutEditorLabel, QLabel#menuLayoutPreviewLabel,
QLabel#menuLayoutEditorHint {
    color: #6f7378;
    font-size: 12px;
    font-weight: 500;
    padding-left: 2px;
}
QLabel#quickLaunchName { color: #252525; font-size: 13px; font-weight: 500; }
QLabel#quickLaunchDetail { color: #777777; font-size: 11px; }
QLabel#quickLaunchEmpty {
    color: #777777;
    background: #fbfbfb;
    border: 1px dashed #d9d9d9;
    border-radius: 8px;
}
QListWidget#quickLaunchList {
    background: #fbfbfb;
    border: 1px solid #d9d9d9;
    border-radius: 8px;
    outline: none;
    padding: 3px;
}
QListWidget#quickLaunchList::item {
    min-height: 30px;
    padding: 3px 7px;
    border-radius: 6px;
}
QListWidget#quickLaunchList::item:selected { background: #e8e8e8; color: #202020; }
QLabel#menuLayoutEditorHint { font-weight: 400; }
QFrame#menuLayoutEditorPanel, QFrame#menuLayoutPreviewPanel {
    background: #fbfbfc;
    border: 1px solid #e2e4e8;
    border-radius: 10px;
}
QFrame#imagePreviewDrawer {
    background: #ffffff;
    border: none;
    border-left: 1px solid #d9dce1;
}
QScrollArea#imagePreviewScroll, QScrollArea#imagePreviewScroll > QWidget > QWidget,
QWidget#imageMasonryFlow { background: transparent; }
QLabel#imagePreviewTitle { color: #202124; font-size: 16px; font-weight: 600; }
QLabel#imagePreviewCount, QLabel#imagePreviewPath { color: #777b80; font-size: 11px; }
QLabel#imagePreviewEmpty { color: #777b80; }
QPushButton#imagePreviewClose { background: transparent; border: none; font-size: 20px; }
QPushButton#imagePreviewClose:hover { background: #eceef1; }
QTreeWidget#menuLayoutTree, QTreeWidget#menuLayoutPreview {
    background: #ffffff;
    border: 1px solid #e2e4e8;
    border-radius: 10px;
    outline: none;
    padding: 4px;
}
QTreeWidget#menuLayoutTree::item, QTreeWidget#menuLayoutPreview::item {
    min-height: 28px;
    padding: 1px 5px;
    border-radius: 6px;
}
QTreeWidget#menuLayoutTree::item:hover { background: #f4f5f6; }
QTreeWidget#menuLayoutTree::item:selected {
    background: #e9eef5;
    color: #202020;
}
QTreeWidget#menuLayoutPreview::item:hover { background: transparent; }
QTreeWidget#menuLayoutTree QHeaderView::section {
    min-height: 28px;
    padding: 0 8px;
    background: #f7f7f8;
    border: none;
    border-bottom: 1px solid #e8e9ec;
    color: #6f7378;
    font-size: 12px;
    font-weight: 500;
}
QMenu {
    background: #fffdf8;
    color: #3a2f24;
    border: 1px solid #dccdb7;
    border-radius: 10px;
    padding: 4px;
}
QMenu::item { min-height: 26px; padding: 2px 24px 2px 10px; border-radius: 6px; }
QMenu::item:selected { background: #f3e2c1; }
QMenu::item:disabled { color: #b5a99c; }
QPushButton {
    min-height: 26px;
    padding: 1px 12px;
    background: #fffdf8;
    border: 1px solid #d9c9ad;
    border-radius: 8px;
    font-weight: 500;
}
QPushButton:hover { background: #f5ead8; }
QPushButton:focus {
    border: 2px solid #0a84ff;
    padding: 0 11px;
}
QPushButton[settingsMenuButton="true"] { padding-right: 26px; }
QPushButton[settingsMenuButton="true"]:focus { padding-right: 25px; }
QPushButton#advancedSectionToggle {
    min-height: 40px;
    padding: 0 38px 0 14px;
    text-align: left;
    background: #ffffff;
    border: 1px solid #e2e4e8;
    border-radius: 10px;
    color: #252525;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#advancedSectionToggle:hover { background: #f7f7f8; border-color: #d7d9dd; }
QPushButton#advancedSectionToggle:focus { border: 2px solid #0a84ff; }
QLabel#disclosureChevron { color: #777b80; font-size: 18px; background: transparent; }
"""
