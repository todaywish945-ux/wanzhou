"""Action registration and tree rendering for the shared Menu Action Model."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QWidgetAction

from ..config import DEFAULT_MENU_EASTER_EGG
from .. import features as features_mod
from ..weather.menu import (
    WEATHER_DISABLED_REASON,
    add_show_weather,
    add_weather_cities,
    weather_menu_enabled,
)
from .fun_entry import add_wanzhou_entry
from .icons import custom_file_menu_icon, vector_menu_icon
from .quick_launch import add_quick_launch_menu, configured_quick_apps
from .shared import (
    BAIDU_PAN_URL,
    NETWORK_INFO_DISABLED_REASON,
    REPO_URL,
    add_action,
    add_autostart,
    add_drag_physics,
    add_edge_probe,
    add_golden_spin,
    add_hide_pet,
    add_look_screen,
    add_memory_trim,
    add_on_top,
    add_quiet_mode_menu,
    add_quit,
    add_return_corner,
    add_screen_capture_menu,
    add_submenu,
    add_network_info,
    network_info_menu_enabled,
    build_animation_categories,
    build_size_menu,
    build_speed_menu,
)


ACTION_LABELS = {
    "wanzhou": "彩蛋", "chat": "AI 对话", "look_screen": "看看屏幕",
    "screen_capture": "截图提问",
    "animations_hub": "播放动画", "character": "切换角色", "playback_speed": "播放速率",
    "size": "大小", "drag_physics": "拖动物理",
    "on_top": "窗口置顶", "autostart": "开机自启",
    "return_corner": "回到右下角", "hide_pet": "隐藏桌宠",
    "golden_spin": "黄金回旋", "edge_probe": "边缘探头",
    "quick_launch": "快捷启动",
    "zzz_launcher": "启动绝区零",
    "memory_trim": "回收内存",
    "check_update": "检查更新", "github_project": "GitHub 项目页",
    "baidu_download": "百度网盘下载",
    "author_info": "作者信息",
    "reminders": "提醒事项",
    "voice_chime_settings": "设置报时",
    "quiet_mode": "免打扰",
    "weather": "查看天气", "weather_cities": "天气城市",
    "network_info": "网络信息",
    "modern_settings": "桌宠设置", "quit": "退出",
}


Builder = Callable[[QMenu, object], object]
Availability = Callable[[object], bool]
Enablement = Callable[[object], bool]


ACTION_ICONS = {
    "wanzhou": "pet", "chat": "chat", "look_screen": "screen",
    "screen_capture": "size",
    "animations_hub": "play", "character": "character", "playback_speed": "speed",
    "size": "size", "drag_physics": "physics",
    "on_top": "pin", "autostart": "autostart",
    "return_corner": "corner", "hide_pet": "hide",
    "golden_spin": "play", "edge_probe": "corner",
    "quick_launch": "application",
    "zzz_launcher": "play",
    "memory_trim": "clear",
    "check_update": "update", "github_project": "web",
    "baidu_download": "download", "author_info": "pet",
    "reminders": "todo",
    "quiet_mode": "pause",
    "weather": "weather", "weather_cities": "weather",
    "network_info": "web",
    "modern_settings": "settings", "quit": "quit",
    "voice_chime_now": "chat", "voice_chime_toggle": "chat",
    "voice_chime_settings": "settings",
    "divination_draw": "todo",
}

CUSTOM_ICON_CHOICES = (
    ("默认图标", "default"), ("无图标", "none"),
    ("对话", "chat"), ("屏幕", "screen"), ("播放", "play"),
    ("角色", "character"), ("速度", "speed"), ("尺寸", "size"),
    ("桌宠", "pet"), ("交互", "interaction"), ("置顶", "pin"),
    ("隐藏", "hide"), ("应用", "application"), ("余额", "balance"),
    ("清除", "clear"), ("网页", "web"), ("下载", "download"), ("更新", "update"),
    ("自动化", "automation"), ("设置", "settings"), ("待办", "todo"),
)


@dataclass(frozen=True)
class MenuActionSpec:
    build: Builder
    available: Availability = lambda _pet: True
    enabled: Enablement = lambda _pet: True
    disabled_reason: str = "当前功能未启用"


def _callback_available(name: str) -> Availability:
    return lambda pet: callable(getattr(pet, name, None))


def _add_liar_bar(menu, pet) -> None:
    """骗子酒馆入口（挽昼桌宠联动）：启动牌局，牌局经联动事件.json 请各桌宠入座。"""
    act = menu.addAction("🃏 骗子酒馆")
    act.triggered.connect(lambda checked=False, p=pet: p.on_launch_liar_bar())


def _add_zzz_launcher(menu, pet) -> None:
    """启动绝区零入口：子菜单展示解析到的游戏位置，支持手动指路。

    探测在右键建造菜单时跑一次（注册表/账本扫描毫秒级），结果只影响展示；
    点「启动」仍走 on_launch_zzz 完整链路（缓存/Job 降级/指路闭环都在那边），
    展示与执行不共享状态，两处独立失败互不拖累。
    """
    from ..zzz_launcher import discover_game

    submenu = add_submenu(menu, "🎮 启动绝区零", "play")
    cfg = getattr(pet, "cfg", None)
    configured = str(cfg.get("zzz_game_path", "") or "") if cfg is not None else ""
    try:
        exe, _source = discover_game(configured)
    except Exception:  # noqa: BLE001 - 探测失败只降级展示，不能挡住菜单弹出
        exe = None
    if exe is not None:
        launch_act = submenu.addAction("🎮 启动")
        launch_act.triggered.connect(lambda checked=False, p=pet: p.on_launch_zzz())
        # 地址展示（只读）：用户点名要看"它到底从哪启动"；全路径放 tooltip。
        path_act = submenu.addAction(f"📍 {exe}")
        path_act.setEnabled(False)
        path_act.setToolTip(str(exe))
    else:
        hint = submenu.addAction("（还没找到游戏）")
        hint.setEnabled(False)
    pick_act = submenu.addAction("📁 手动指定路径…")
    pick_act.triggered.connect(lambda checked=False, p=pet: p.on_pick_zzz_path())


def _memory_trim_available(_pet) -> bool:
    """「回收内存」只对 Windows 显示：其它平台没有 EmptyWorkingSet。

    判定走 ``pet/memory_trim.py::is_supported``（与执行层同一判据），不另写一份
    ``sys.platform`` 比较——菜单给不给看和执行能不能跑必须是同一个真相。
    """
    from .. import memory_trim

    return memory_trim.is_supported()


# 「查看天气 / 天气城市」的判据与原因文案收在共享建造器模块（`weather_menu`），
# 这里只做转发：开关真值只有一份，注册表的 enabled 与建造器写的 tooltip 同源。
# （历史背景：旧版扁平菜单曾直调建造器绕过注册表，门只写在注册表上就会漏；
# 旧版菜单已于 2026-10-08 退役，但"判定收在建造器里"的口径保持不动。）
_WEATHER_DISABLED_REASON = WEATHER_DISABLED_REASON
_weather_enabled = weather_menu_enabled


def _build_chat(menu, pet):
    return add_action(menu, "AI 对话", "chat", pet.on_open_chat, close_on_trigger=True)


def _build_animations(menu, pet):
    submenu = add_submenu(menu, "播放动画", "play")
    build_animation_categories(submenu, pet, icons=False, leaf_role_icons=True)
    return submenu


def _build_settings(menu, pet):
    return add_action(menu, "桌宠设置", "settings", pet.on_open_modern_settings, close_on_trigger=True)


def _build_reminders(menu, pet):
    """提醒事项（本项目新实现）：打开进程级管理窗（闹钟/倒计时/单次）。"""
    return add_action(menu, "⏰ 提醒事项", "todo", pet.on_open_reminders, close_on_trigger=True)


def _build_voice_chime_now(menu, pet):
    return add_action(menu, "立即报时", "chat", pet.on_voice_chime_now, close_on_trigger=True)


def _build_voice_chime_settings(menu, pet):
    """设置报时：打开轻量报时设置窗（节奏/时间点/音量）。"""
    return add_action(menu, "设置报时…", "settings", pet.on_chime_settings,
                      close_on_trigger=True)


def _flag_toggle_spec(key: str, on_label: str, off_label: str, icon: str,
                      callback: str):
    """布尔开关菜单项的规约工厂：按配置当前值翻转标签，点击回回调。

    语音报时开关与节日提醒开关此前逐字同构，这里把「读配置 → 选标签 →
    add_action」收成一处；标签翻转、图标、回调与 close_on_trigger 语义逐点
    不变。注意 `enabled` 只影响展示标签，不影响回调可用性（可用性仍由
    `MenuActionSpec.available` 的 `_callback_available` 判定）。
    """
    def _build(menu, pet):
        cfg = getattr(pet, "cfg", None)
        enabled = bool(cfg.get(key, False)) if cfg is not None else False
        return add_action(
            menu, on_label if enabled else off_label, icon,
            getattr(pet, callback), close_on_trigger=True,
        )

    return _build


def _network_info_enabled(pet) -> bool:
    """「网络信息」入口的运行时启用态：设置里开着才可用（默认开）。

    **只影响 enabled，不影响 available**：关掉开关时入口保留布局位置、渲染成
    "灰掉 + 说明"（CONTEXT.md 的 Runtime Disabled），不把节点从菜单树里过滤掉——
    过滤只用于"能力不可用"，本例里就是回调缺失（纯桌宠变体）。
    """
    return network_info_menu_enabled(pet)


_build_voice_chime_toggle = _flag_toggle_spec(
    "voice_chime_enabled", "关闭语音报时", "启用语音报时", "chat",
    "on_toggle_voice_chime",
)

def _build_divination_draw(menu, pet):
    """「每日英文」：每天一句英文+译文，点开即出（当天再点显示同一句）。"""
    return add_action(menu, "每日英文", "todo", pet.on_divination_draw, close_on_trigger=True)


def _build_check_update(menu, pet):
    return add_action(menu, "检查更新", "update", lambda: pet.on_check_update(pet), close_on_trigger=True)


def _build_github(menu, _pet):
    return add_action(
        menu,
        "GitHub 项目页",
        "web",
        lambda: QDesktopServices.openUrl(QUrl(REPO_URL)),
        close_on_trigger=True,
    )


def _build_author_info(menu, pet):
    """作者信息：只读弹窗（文案 + 照片），不写 Config。"""
    from ..author_info import show_author_info
    from .shared import _dialog_parent

    return add_action(
        menu, "作者信息", "pet",
        lambda: show_author_info(_dialog_parent(pet)),
        close_on_trigger=True,
    )


def _build_baidu_pan(menu, _pet):
    """百度网盘直链：URL 已带 pwd 参数，网页端自动填提取码，无需另开说明。"""
    return add_action(
        menu,
        "百度网盘下载",
        "download",
        lambda: QDesktopServices.openUrl(QUrl(BAIDU_PAN_URL)),
        close_on_trigger=True,
    )


class MenuActionRegistry:
    """Resolve capability-aware action IDs and render a resolved menu tree."""

    def __init__(self) -> None:
        self._specs = {
            "wanzhou": MenuActionSpec(
                lambda menu, pet: add_wanzhou_entry(
                    menu, pet.cfg.get("menu_easter_egg", DEFAULT_MENU_EASTER_EGG)
                ),
                enabled=lambda pet: bool(
                    pet.cfg.get("menu_easter_egg", DEFAULT_MENU_EASTER_EGG).get("enabled", True)
                ),
                disabled_reason="彩蛋入口已在设置中停用",
            ),
            "chat": MenuActionSpec(_build_chat, _callback_available("on_open_chat")),
            "liar_bar": MenuActionSpec(_add_liar_bar, _callback_available("on_launch_liar_bar")),
            "zzz_launcher": MenuActionSpec(
                _add_zzz_launcher, _callback_available("on_launch_zzz")),
            "look_screen": MenuActionSpec(add_look_screen, _callback_available("on_look_screen")),
            # 「截图」单一入口（框选识屏）：动作在覆盖层松手后的动作条上选，
            # 注册表这一层只表达"宿主有没有这套面"。
            "screen_capture": MenuActionSpec(
                add_screen_capture_menu, _callback_available("on_screen_capture")
            ),
            "animations_hub": MenuActionSpec(_build_animations),
            # 「切换角色」入口已移除（2026-11-23）：三只桌宠各由独立启动脚本固定角色。
            "playback_speed": MenuActionSpec(lambda menu, pet: build_speed_menu(menu, pet)),
            "size": MenuActionSpec(lambda menu, pet: build_size_menu(menu, pet)),
            "drag_physics": MenuActionSpec(add_drag_physics),
            "on_top": MenuActionSpec(add_on_top),
            "autostart": MenuActionSpec(lambda menu, pet: add_autostart(menu, pet)),
            "return_corner": MenuActionSpec(add_return_corner),
            "hide_pet": MenuActionSpec(add_hide_pet),
            # 平台门在 menu_layout 的 available_actions 过滤里生效（非 Windows
            # 整条不出现）；builder 自身也有同一道门，legacy 扁平布局直接调它。
            "memory_trim": MenuActionSpec(add_memory_trim, _memory_trim_available),
            "golden_spin": MenuActionSpec(
                add_golden_spin,
                _callback_available("trigger_golden_spin"),
            ),
            "edge_probe": MenuActionSpec(add_edge_probe),
            "quick_launch": MenuActionSpec(
                lambda menu, pet: add_quick_launch_menu(menu, pet.cfg),
                enabled=lambda pet: bool(configured_quick_apps(pet.cfg)),
                disabled_reason="尚未配置快捷启动应用",
            ),
            "check_update": MenuActionSpec(_build_check_update, _callback_available("on_check_update")),
            "github_project": MenuActionSpec(_build_github),
            "author_info": MenuActionSpec(_build_author_info),
            "baidu_download": MenuActionSpec(_build_baidu_pan, lambda _pet: sys.platform == "win32"),
            # 免打扰：进程级状态，任何宿主（PetWindow / SpriteMenuFacade）都可用，
            # 不做能力判定——菜单里永远给得出入口，用户不必先找开关。
            "quiet_mode": MenuActionSpec(add_quiet_mode_menu),
            "modern_settings": MenuActionSpec(
                _build_settings, _callback_available("on_open_modern_settings")
            ),
            # 提醒事项：新实现的核心工具，回调在 PetWindow 上恒绑定（与已删的 todo 空壳分开）。
            "reminders": MenuActionSpec(
                _build_reminders, _callback_available("on_open_reminders")
            ),
            "voice_chime_now": MenuActionSpec(
                _build_voice_chime_now, _callback_available("on_voice_chime_now")
            ),
            "voice_chime_settings": MenuActionSpec(
                _build_voice_chime_settings, _callback_available("on_chime_settings")
            ),
            "voice_chime_toggle": MenuActionSpec(
                _build_voice_chime_toggle, _callback_available("on_toggle_voice_chime")
            ),
            "divination_draw": MenuActionSpec(
                _build_divination_draw, _callback_available("on_divination_draw")
            ),
            # 天气：回调缺失 = 能力不可用（隐藏）；开关关掉 = 运行时置灰、位置保留
            # （CONTEXT.md 的 Capability Unavailable / Runtime Disabled 口径）。
            "weather": MenuActionSpec(
                add_show_weather,
                _callback_available("on_show_weather"),
                enabled=_weather_enabled,
                disabled_reason=_WEATHER_DISABLED_REASON,
            ),
            "weather_cities": MenuActionSpec(
                add_weather_cities,
                _callback_available("on_show_weather"),
                enabled=_weather_enabled,
                disabled_reason=_WEATHER_DISABLED_REASON,
            ),
            "network_info": MenuActionSpec(
                add_network_info,
                _callback_available("on_network_info"),
                enabled=_network_info_enabled,
                disabled_reason=NETWORK_INFO_DISABLED_REASON,
            ),
            "quit": MenuActionSpec(add_quit),
        }

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self._specs)

    def available_ids(self, pet) -> frozenset[str]:
        # 功能模块投影：未激活模块的动作直接从「可用集」剔除——布局解析会
        # 顺带丢空子菜单、规整分隔线，且不写回用户的自定义布局（重开即恢复）。
        # 快照未冻结（测试/工具）时 is_active 恒 True，行为与旧版一致。
        from .. import feature_activation

        return frozenset(
            action_id
            for action_id, spec in self._specs.items()
            if spec.available(pet)
            and feature_activation.is_active(
                features_mod.feature_for_action(action_id) or ""
            )
        )

    def enabled_ids(self, pet) -> frozenset[str]:
        return frozenset(
            action_id
            for action_id, spec in self._specs.items()
            if spec.available(pet) and spec.enabled(pet)
        )

    def disabled_reason(self, action_id: str) -> str:
        spec = self._specs.get(action_id)
        return spec.disabled_reason if spec is not None else "当前不可用"

    def default_icon(self, action_id: str) -> str:
        return ACTION_ICONS.get(action_id, "")

    def label(self, action_id: str) -> str:
        return ACTION_LABELS.get(action_id, action_id)

    def icon(self, widget, action_id: str, override=None) -> QIcon:
        """Resolve semantic or local-file presentation with a safe fallback."""
        if isinstance(override, dict) and override.get("kind") == "file":
            custom = custom_file_menu_icon(widget, override)
            if not custom.isNull():
                return custom
            override = None
        if override == "none":
            return QIcon()
        name = str(override or self.default_icon(action_id) or "")
        return vector_menu_icon(widget, name) if name else QIcon()

    def populate(self, menu: QMenu, pet, nodes, *, enabled_actions=None) -> None:
        enabled = frozenset(enabled_actions) if enabled_actions is not None else self.enabled_ids(pet)
        explicit_separators = any(node.get("type") == "separator" for node in nodes)
        previous_section = None
        rendered = 0
        for node in nodes:
            if node.get("type") == "separator":
                if rendered and menu.actions() and not menu.actions()[-1].isSeparator():
                    menu.addSeparator()
                previous_section = None
                continue
            section = node.get("section")
            if (
                not explicit_separators
                and rendered and section and previous_section and section != previous_section
            ):
                menu.addSeparator()
            built = None
            if node.get("type") == "submenu":
                submenu = add_submenu(
                    menu,
                    str(node.get("alias") or node.get("label") or ""),
                )
                self.populate(
                    submenu, pet, node.get("children", ()), enabled_actions=enabled,
                )
                built = submenu
                if "icon" in node:
                    submenu.menuAction().setIcon(
                        self.icon(menu, str(node.get("id") or ""), node.get("icon"))
                    )
            else:
                action_id = str(node.get("id") or "")
                spec = self._specs.get(action_id)
                if spec is not None:
                    built = spec.build(menu, pet)
                    action = built.menuAction() if isinstance(built, QMenu) else built
                    alias = str(node.get("alias") or "").strip()
                    if alias and action is not None:
                        action.setText(alias)
                        if isinstance(action, QWidgetAction):
                            widget = action.defaultWidget()
                            setter = getattr(widget, "set_title", None)
                            if callable(setter):
                                setter(alias)
                    if action is not None and "icon" in node:
                        action.setIcon(self.icon(menu, action_id, node.get("icon")))
                    if action is not None and action_id not in enabled:
                        action.setEnabled(False)
                        action.setToolTip(self.disabled_reason(action_id))
                        if isinstance(action, QWidgetAction) and action.defaultWidget() is not None:
                            action.defaultWidget().setEnabled(False)
            rendered += 1
            if section:
                previous_section = section


MENU_ACTIONS = MenuActionRegistry()
