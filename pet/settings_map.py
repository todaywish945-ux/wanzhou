# -*- coding: utf-8 -*-
"""设置「功能地图」：按 域 → 页内标签 → 分组 浏览全部设置，并一键跳到原位置。

**为什么单独一个模块**：``modern_settings_dialog.py`` 有硬行数预算，而这里是一整张
只读浏览窗（模型采集 + 过滤 + 跳转），与对话框的构建/保存链无关。对话框只留一个
按钮、一个快捷键和一次 ``open_map`` 调用。

**为什么不重排设置项本身**：侧栏能力域、页内标签、行 ``objectName`` 与保存分流
都是外部契约（深链、测试、广播都按它们工作）。用户抱怨的是「找不到」，不是「功能
不够」——再叠一层导航比搬动行更安全，也不改变任何配置语义。

口径：

- **只读**：本模块遍历已装配好的页面树，不创建/删除/搬动任何设置控件；搜索过滤只
  改树节点的隐藏态/展开态，关掉窗口不留下状态。
- **首屏收敛**：只展开用户当前所在的侧栏域（有页内标签的只展开当前标签），其余域
  收起。早先一进来 100+ 行铺满树，等于把「地图」又做成了长清单。
- **跳转走既有路径**：切侧栏域 → ``activate_for_descendant`` 切页内标签 →
  ``reveal_settings_row`` 展开折叠 → ``ensureWidgetVisible`` 滚进来。功能地图不另写
  一套显隐逻辑。
- **命令独立成排**：「应用到其他桌宠」「重置」是按钮不是 SettingRow，不塞进域树
  （那会让它看起来像第八个设置域），而是在搜索框下固定一排「常用操作」。点一下
  只定位到原按钮、**不直接执行**——尤其「重置」绝不能因为找功能误触。
- **「功能」总开关页已从侧栏隐藏**：地图只遍历侧栏实际挂载的页，功能卡片不再登记；
  各功能由自己的具体设置行进入。保留卡片扫描只为兼容仍挂出卡片的构建变体。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import settings_page_guide
from .settings_search import ROW_ALIASES, row_key
from .settings_widgets import (
    CollapsibleGroup,
    SettingRow,
    SettingsSection,
    SettingsTabContainer,
    reveal_settings_row,
)

#: 侧栏悬停解释。短域名（「常规」「功能」）在 200px 侧栏里没法写全，tooltip 补上。
DOMAIN_HINTS = {
    "常规": "开机自启、窗口置顶、全屏隐藏等与系统/窗口有关的基础设置",
    "显示": "这只桌宠的大小、透明度与音乐联动",
    "动作与碰撞": "这只桌宠的动作、拖拽、弹射与碰撞参数",
    "互动": "点击反馈、自言自语、天气、抽签与全局快捷键",
    "菜单": "右键菜单显示什么、怎么排序，以及快捷启动与菜单外观",
    "灵动岛": "灵动岛胶囊与网络延迟检测",
    "AI 与对话": "模型与 API、对话风格、记忆、视觉能力和文件解读",
    "语音": "报时与节日提醒的声音设置",
    "更新": "检查并安装新版本",
}

_FEATURE_PREFIX = "featureCard_"
_USER_ROLE = Qt.ItemDataRole.UserRole

#: 命令类控件（按钮而非 SettingRow）：不进搜索索引、不进域树，在地图顶部固定成
#: 一排。getter 收 dialog，构造窗口时才解析——不同构建变体里按钮可能不存在。
COMMAND_SPECS = (
    ("mapCmdApply", "应用到其他桌宠…", "把本宠设置同步给其他桌宠（保留各自角色与位置）",
     lambda dialog: getattr(dialog, "apply_to_others_btn", None)),
    ("mapCmdResetPet", "重置本宠设置", "把这只桌宠的设置恢复为默认值",
     lambda dialog: getattr(dialog, "reset_defaults_btn", None)),
    ("mapCmdResetGlobal", "重置全局设置", "把所有桌宠共用的设置恢复为默认值",
     lambda dialog: getattr(dialog, "reset_global_defaults_btn", None)),
)


def _collect_commands(dialog) -> list[dict]:
    """当前构建里实际存在的命令按钮（不存在就少一格，不放假入口）。"""
    commands = []
    for name, label, hint, getter in COMMAND_SPECS:
        widget = getter(dialog)
        if widget is not None:
            commands.append({"name": name, "label": label, "hint": hint, "widget": widget})
    return commands


def _alias_words_for(key: str) -> list[str]:
    """反查这张表：哪些口语说法指向这个行键。"""
    return [token for token, targets in ROW_ALIASES.items() if key in targets]


def _nearest_section_title(widget: QWidget) -> str:
    node = widget.parentWidget()
    while node is not None:
        if isinstance(node, SettingsSection):
            title = settings_page_guide.section_title(node)
            if title:
                return title
        elif isinstance(node, CollapsibleGroup):
            title = node.toggle.text()
            if title:
                return title
        node = node.parentWidget()
    return ""


def _collect_entries(dialog) -> list[dict]:
    """从已装配的页面树里读出全部可跳转项（每行一条，带路径和搜索词）。"""
    entries: list[dict] = []
    seen: set[int] = set()

    def add(widget: QWidget, label: str, hint: str, parts: list[str]) -> None:
        if widget is None or id(widget) in seen or not label:
            return
        seen.add(id(widget))
        key = row_key(widget) if isinstance(widget, SettingRow) else widget.objectName()
        words = [label, hint, key, " ".join(parts), *_alias_words_for(key)]
        entries.append({
            "widget": widget,
            "label": label,
            "hint": hint,
            "parts": list(parts),
            "keywords": " ".join(str(word) for word in words if word).lower(),
        })

    for index in range(dialog.pages.count()):
        domain = dialog.sidebar.item(index).text()
        page = dialog.pages.widget(index)
        scroll = page.findChild(QScrollArea, "settingsScroll")
        root = scroll.widget() if scroll is not None else page
        if root is None:
            continue

        tabs = root.findChild(SettingsTabContainer, "settingsTaskTabs")
        panes = []
        if tabs is not None:
            for position in range(tabs.stack.count()):
                pane = tabs.stack.widget(position)
                tab_label = tabs.labels()[position] if position < len(tabs.labels()) else ""
                panes.append((pane, [domain, tab_label] if tab_label else [domain]))
        else:
            panes.append((root, [domain]))

        for pane, base_parts in panes:
            for section_title, rows in settings_page_guide.sections_in_layout_order(pane):
                path = [*base_parts, section_title]
                for row in rows:
                    # SettingsSection 也装纯 QWidget（「多宠设置」里的按钮行等）；
                    # 它们不是 SettingRow，命令类入口在下面统一登记，这里跳过。
                    if isinstance(row, SettingRow):
                        add(row, row.label.text(), row.hint_label.text(), path)
            # 没被任何 SettingsSection 收走的行（少数平卡布局）按布局序兜底。
            section_rows = {id(row) for _title, rows in
                            settings_page_guide.sections_in_layout_order(pane) for row in rows}
            for row in pane.findChildren(SettingRow):
                if id(row) not in section_rows:
                    parts = settings_page_guide.location_parts(row, domain)
                    add(row, row.label.text(), row.hint_label.text(), parts)

        # 功能卡片不是 SettingRow：按 objectName 前缀捞，挂回它所在的分组。
        for card in page.findChildren(QWidget):
            if not card.objectName().startswith(_FEATURE_PREFIX):
                continue
            label_widget = getattr(card, "label", None)
            if label_widget is None:
                continue
            section = _nearest_section_title(card)
            parts = [domain, section] if section else [domain]
            hint_widget = getattr(card, "hint_label", None)
            add(card, label_widget.text(),
                hint_widget.text() if hint_widget is not None else "", parts)

    # 命令按钮不进树：它们在窗口顶部固定成「常用操作」一排，见 _collect_commands。
    return entries


class SettingsMapDialog(QDialog):
    """可搜索的设置目录；点条目直接跳到原设置页的对应位置。"""

    def __init__(self, dialog, parent=None):
        super().__init__(parent or dialog)
        self._dialog = dialog
        self.setWindowTitle("功能地图 · 找不到设置就在这里找")
        self.setObjectName("settingsMapDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setModal(False)
        self.resize(720, 520)
        # 继承设置窗主题（深浅两套），树控件沿用 QSS 里的 QTreeWidget 规则。
        self.setStyleSheet(dialog.styleSheet())
        self.setProperty("modernStyle", True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        intro = QLabel("按名字找，或按 域 / 标签 / 分组 逐层展开。双击条目直接跳过去。", self)
        intro.setObjectName("mapIntro")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.search = QLineEdit(self)
        self.search.setObjectName("settingsMapSearch")
        self.search.setPlaceholderText("搜索设置名、分组名，或口语说法（如：网速、开机启动）")
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._jump_first_visible)
        root.addWidget(self.search)

        # 常用操作：固定在搜索框下，不跟设置域混在一棵树里。点击只定位到原按钮，
        # 不触发点击动作（尤其两个「重置」——找功能时误触代价太大）。
        command_row = QWidget(self)
        command_row.setObjectName("mapCommands")
        command_layout = QHBoxLayout(command_row)
        command_layout.setContentsMargins(0, 0, 0, 0)
        command_layout.setSpacing(6)
        command_title = QLabel("常用操作", command_row)
        command_title.setObjectName("mapCommandsTitle")
        command_layout.addWidget(command_title)
        for spec in _collect_commands(dialog):
            button = QPushButton(spec["label"], command_row)
            button.setObjectName(spec["name"])
            button.setProperty("variant", "ghost")
            button.setToolTip(f"{spec['hint']}（点击后定位到原按钮，不会立即执行）")
            button.clicked.connect(
                lambda _checked=False, widget=spec["widget"]: self._jump_to_widget(widget))
            command_layout.addWidget(button)
        command_layout.addStretch(1)
        root.addWidget(command_row)
        self._command_count = len(_collect_commands(dialog))

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("settingsMapTree")
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["设置项", "所属分组"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.itemDoubleClicked.connect(self._jump_from_item)
        self.tree.currentItemChanged.connect(lambda *_: self._sync_jump_button())
        root.addWidget(self.tree, 1)

        self.status = QLabel("", self)
        self.status.setObjectName("settingsMapStatus")
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self.jump_button = QPushButton("跳到选中项", self)
        self.jump_button.setObjectName("settingsMapJump")
        self.jump_button.setEnabled(False)
        self.jump_button.clicked.connect(self._jump_current)
        buttons.addWidget(self.jump_button)
        close_button = QPushButton("关闭", self)
        close_button.setObjectName("settingsMapClose")
        close_button.clicked.connect(self.close)
        buttons.addWidget(close_button)
        root.addLayout(buttons)

        self._total = 0
        self._build_tree()
        self.search.setFocus(Qt.FocusReason.OtherFocusReason)

    def _build_tree(self) -> None:
        self.tree.clear()
        entries = _collect_entries(self._dialog)
        self._total = len(entries)
        root_items: dict[str, QTreeWidgetItem] = {}
        branch_cache: dict[tuple, QTreeWidgetItem] = {}
        #: 默认展开的节点（父在前、子在后），搜索清空后据此复原首屏。
        self._default_expand: list[QTreeWidgetItem] = []

        # 首屏只展开「用户正看的那个域」；有页内标签的域再收窄到当前标签。
        current_domain = ""
        current_tab = ""
        current_row = self._dialog.sidebar.currentRow()
        if current_row >= 0:
            current_item = self._dialog.sidebar.item(current_row)
            current_domain = current_item.text() if current_item is not None else ""
            page = self._dialog.pages.widget(current_row)
            tabs = page.findChild(SettingsTabContainer, "settingsTaskTabs") if page else None
            if tabs is not None and tabs.currentKey() in tabs.keys():
                current_tab = tabs.labels()[tabs.keys().index(tabs.currentKey())]
        self._current_domain = current_domain
        self._current_tab = current_tab
        # 域 → 页内标签名集合：用来区分第 2 段是「标签」还是「分组」。
        tab_labels: dict[str, set[str]] = {}
        for index in range(self._dialog.pages.count()):
            page = self._dialog.pages.widget(index)
            tabs = page.findChild(SettingsTabContainer, "settingsTaskTabs") if page else None
            if tabs is not None and self._dialog.sidebar.item(index) is not None:
                tab_labels[self._dialog.sidebar.item(index).text()] = set(tabs.labels())

        def child(parent: QTreeWidgetItem, key: tuple, text: str,
                  second: str = "", *, expand: bool = False) -> QTreeWidgetItem:
            if key not in branch_cache:
                branch = QTreeWidgetItem([text, second])
                parent.addChild(branch)
                if expand:
                    # 必须先挂到树上，展开态才落得住；同时记下来供清空搜索后复原。
                    branch.setExpanded(True)
                    self._default_expand.append(branch)
                branch_cache[key] = branch
            return branch_cache[key]

        for entry in entries:
            parts = entry["parts"]
            domain = parts[0] if parts else "其他"
            if domain not in root_items:
                root = QTreeWidgetItem([domain, ""])
                root.setToolTip(0, DOMAIN_HINTS.get(domain, ""))
                self.tree.addTopLevelItem(root)
                if domain == current_domain:
                    root.setExpanded(True)
                    self._default_expand.append(root)
                root_items[domain] = root
            parent = root_items[domain]
            # 第 2 段是页内标签（该域有标签时），否则就是分组；再往后都是分组。
            for depth, part in enumerate(parts[1:-1], start=1):
                is_tab = depth == 1 and part in tab_labels.get(domain, ())
                expand = is_tab and domain == current_domain and part == current_tab
                parent = child(parent, (domain, *parts[1:depth + 1]), part, expand=expand)
            path = " › ".join(parts)
            # 第二列只写所属分组名：完整路径已经在树的父子层级里，重复一遍只会
            # 把列宽撑到 240px+ 并挤窄第一列。完整路径挪到 tooltip。
            # parts 本身是路径（不含行名），最后一段就是所属分组。
            section = parts[-1] if parts else ""
            leaf = QTreeWidgetItem([entry["label"], section])
            leaf.setData(0, _USER_ROLE, entry)
            hint = entry["hint"]
            leaf.setToolTip(0, f"{path}\n{hint}" if hint else path)
            leaf.setToolTip(1, path)
            parent.addChild(leaf)

        # 默认最后一列会拉伸着吃掉整个视口，setColumnWidth 在 show 之后被顶掉；
        # 关掉 stretch 才能让第二列真的收窄。
        self.tree.header().setStretchLastSection(False)
        self.tree.resizeColumnToContents(0)
        self.tree.setColumnWidth(1, 150)
        self.status.setText(
            f"共 {self._total} 项设置 · {self._command_count} 个常用操作")
        self._sync_jump_button()

    def _reset_expansion(self) -> None:
        """清空搜索后回到首屏的展开态（当前域 + 当前标签）。"""
        def collapse(item: QTreeWidgetItem) -> None:
            item.setExpanded(False)
            for index in range(item.childCount()):
                collapse(item.child(index))

        for index in range(self.tree.topLevelItemCount()):
            collapse(self.tree.topLevelItem(index))
        for item in getattr(self, "_default_expand", ()):
            item.setExpanded(True)

    def _filter(self, text: str) -> None:
        needle = str(text or "").strip().lower()
        visible = 0
        for index in range(self.tree.topLevelItemCount()):
            if self._filter_item(self.tree.topLevelItem(index), needle):
                visible += 1
        # 每次搜索都从同一份首屏展开态出发：否则改一个字，上一轮命中的分支
        # 还铺在树上，越搜越乱；清空后也靠它复原。
        self._reset_expansion()
        if needle:
            for index in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(index)
                if not item.isHidden():
                    item.setExpanded(True)
                    self._expand_visible(item)
        self.status.setText(
            f"{visible} 项匹配" if needle else
            f"共 {self._total} 项设置 · {self._command_count} 个常用操作")
        self._sync_jump_button()

    def _filter_item(self, item: QTreeWidgetItem, needle: str) -> bool:
        if not needle:
            item.setHidden(False)
            for index in range(item.childCount()):
                self._filter_item(item.child(index), needle)
            return True
        entry = item.data(0, _USER_ROLE)
        if isinstance(entry, dict):
            own = needle in entry["keywords"]
        else:
            own = needle in item.text(0).lower()
        child_visible = False
        for index in range(item.childCount()):
            if self._filter_item(item.child(index), needle):
                child_visible = True
        show = own or child_visible
        item.setHidden(not show)
        if show and child_visible:
            item.setExpanded(True)
        return show

    @staticmethod
    def _expand_visible(item: QTreeWidgetItem) -> None:
        for index in range(item.childCount()):
            child = item.child(index)
            if not child.isHidden():
                child.setExpanded(True)
                SettingsMapDialog._expand_visible(child)

    def _sync_jump_button(self) -> None:
        current = self.tree.currentItem()
        self.jump_button.setEnabled(
            current is not None and isinstance(current.data(0, _USER_ROLE), dict))

    def _jump_first_visible(self) -> None:
        def first(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if item.isHidden():
                return None
            if isinstance(item.data(0, _USER_ROLE), dict):
                return item
            for index in range(item.childCount()):
                found = first(item.child(index))
                if found is not None:
                    return found
            return None

        for index in range(self.tree.topLevelItemCount()):
            target = first(self.tree.topLevelItem(index))
            if target is not None:
                self.tree.setCurrentItem(target)
                self._jump_from_item(target)
                return

    def _jump_current(self) -> None:
        current = self.tree.currentItem()
        if current is not None:
            self._jump_from_item(current)

    def _jump_from_item(self, item: QTreeWidgetItem) -> None:
        entry = item.data(0, _USER_ROLE)
        if isinstance(entry, dict):
            self._jump_to_widget(entry["widget"])

    def _jump_to_widget(self, widget) -> None:
        """切域/切标签/露出原控件并关窗；命令按钮也走这里，但绝不点它。"""
        if widget is None:
            return
        dialog = self._dialog
        target_page = None
        focus_target = None
        page_index = -1
        for index in range(dialog.pages.count()):
            page = dialog.pages.widget(index)
            if page is widget or page.isAncestorOf(widget):
                target_page = page
                page_index = index
                break
        if target_page is not None:
            dialog.sidebar.setCurrentRow(page_index)
            tabs = target_page.findChild(SettingsTabContainer, "settingsTaskTabs")
            if tabs is not None:
                tabs.activate_for_descendant(widget)
            if isinstance(widget, SettingRow):
                reveal_settings_row(widget, target_page)
                dialog._clear_search_matches()
                widget.setProperty("searchMatch", True)
                widget.style().unpolish(widget)
                widget.style().polish(widget)
            scroll = target_page.findChild(QScrollArea, "settingsScroll")
            if scroll is not None:
                scroll.ensureWidgetVisible(widget, 0, 24)
        else:
            # 侧栏命令：不在页面堆栈里，关窗后把焦点送过去（accept 会恢复旧焦点，
            # 所以必须放在 accept 之后设，否则会被那一步覆盖）。
            focus_target = widget
        self.accept()
        if focus_target is not None:
            # accept() 的焦点恢复排在事件循环末尾，直接 setFocus 会被它盖掉。
            QTimer.singleShot(0, lambda: focus_target.setFocus(
                Qt.FocusReason.OtherFocusReason))


def open_map(dialog) -> SettingsMapDialog:
    """打开（或唤回）设置窗对应的功能地图；返回窗口，调用方可拿它做测试。"""
    existing = getattr(dialog, "_settings_map_window", None)
    if existing is not None and existing.isVisible():
        existing.raise_()
        existing.activateWindow()
        return existing
    window = SettingsMapDialog(dialog, dialog)
    dialog._settings_map_window = window
    window.show()
    return window
