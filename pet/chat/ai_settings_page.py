# -*- coding: utf-8 -*-
"""Modern settings AI 设置页 _AiSettingsPage。

从 modern_settings_dialog.py 纯机械搬移。现位于 pet/chat/ 下，原 `from .chat.xxx`
相对导入改为 `from .xxx`（级别变化）。
"""
from __future__ import annotations

import threading
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import ROLEPLAY_CAST_MAX_CHARS, ROLEPLAY_SCENE_MAX_CHARS
from .episodic_memory import EpisodicMemory, clarity_of, FUZZY_CLARITY
from ..settings_widgets import (
    ModernSelect,
    _line_edit,
    BrowserSpinBox,
    BrowserDoubleSpinBox,
    ToggleSwitch,
    ResponsiveActionRow,
    SettingsSection,
    SettingRow,
    SettingsCard,
)
from .memory import LAYERS, ChatMemory, layer_of, memory_path
from .memory_recall import LAYER_LABELS, is_archived
from .utils import _safe_emit


class _AiSettingsPage(QWidget):
    test_done = Signal(bool, str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setObjectName("aiSettingsContent")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # No-chat bundles exclude pet.chat and never construct this optional page.
        from .models import ProviderConfig, SecretStore, WEB_SEARCH_KEYED_ENGINES
        from .providers import test_connection
        from .web_search import ENGINE_LABELS

        self.config = config
        self._provider_config_type = ProviderConfig
        self._secret_store_type = SecretStore
        self._test_connection = test_connection
        self.settings = config.chat_settings()
        provider = self.settings.active_config
        self._test_thread = None
        self._provider_drafts: dict[str, dict] = {}
        self._deleted_provider_ids: set[str] = set()
        self._loading_provider = False
        self.test_done.connect(self._on_test_done)

        self.provider_combo = ModernSelect(self, width=230)
        self.add_provider_btn = QPushButton("添加", self)
        self.delete_provider_btn = QPushButton("删除", self)
        for pid, provider_item in self.settings.providers.items():
            self.provider_combo.addItem(self._provider_label(provider_item), pid)
        self.provider_combo.setCurrentData(self.settings.active_provider)

        self.name = _line_edit(provider.name)
        self.url = _line_edit(provider.base_url)
        self.model = _line_edit(provider.model)
        self.key = _line_edit(password=True)
        self.prompt = QPlainTextEdit(self.settings.default_system_prompt)
        self.prompt.setMinimumSize(240, 80)
        self.timeout = BrowserSpinBox()
        self.timeout.setRange(1, 600)
        self.timeout.setSuffix(" 秒")
        self.timeout.setValue(int(provider.timeout))
        self.temperature = BrowserDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(provider.temperature)
        self.tokens = BrowserSpinBox()
        self.tokens.setRange(1, 131072)
        self.tokens.setValue(provider.max_tokens)
        self.skip_ssl = ToggleSwitch()
        self.skip_ssl.setChecked(not provider.verify_ssl)
        # 深度思考（按 provider 保存）
        self.thinking_mode = ModernSelect(self, width=230)
        self.thinking_mode.addItem("跟随模型默认", "auto")
        self.thinking_mode.addItem("开启深度思考", "enabled")
        self.thinking_mode.addItem("关闭深度思考", "disabled")
        self.thinking_mode.setCurrentData(provider.thinking)
        self.reasoning_effort = ModernSelect(self, width=230)
        self.reasoning_effort.addItem("低（更快）", "low")
        self.reasoning_effort.addItem("高（默认）", "high")
        self.reasoning_effort.addItem("最大（最慢、最深入）", "max")
        self.reasoning_effort.setCurrentData(provider.reasoning_effort)
        # 联网搜索（全局，所有 provider 共用）
        self._web_keyed_engines = WEB_SEARCH_KEYED_ENGINES
        web = self.settings.web_search
        self.web_search_enabled = ToggleSwitch()
        self.web_search_enabled.setChecked(bool(web.enabled))
        self.web_search_engine = ModernSelect(self, width=230)
        for engine_id, engine_label in ENGINE_LABELS.items():
            self.web_search_engine.addItem(engine_label, engine_id)
        self.web_search_engine.setCurrentData(web.engine)
        self.web_search_key = _line_edit(password=True)
        self.web_search_key.setPlaceholderText("已保存则留空；输入新值将覆盖")
        self.web_search_results = BrowserSpinBox()
        self.web_search_results.setRange(1, 10)
        self.web_search_results.setSuffix(" 条")
        self.web_search_results.setValue(int(web.max_results))
        self.web_search_fetch = ToggleSwitch()
        self.web_search_fetch.setChecked(bool(web.fetch_pages))
        # 助手回复朗读（全局，默认关）：复用语音报时那条音频通道，只念对话不念歌词。
        self.chat_reply_voice = ToggleSwitch()
        self.chat_reply_voice.setChecked(bool(config.get("chat_reply_voice_enabled", False)))
        # 对话全局记忆（档 A 手动钉，全局，默认开）：注入总开关 + 记忆管理入口。
        self.chat_memory_enabled = ToggleSwitch()
        self.chat_memory_enabled.setChecked(bool(config.get("chat_memory_enabled", True)))
        # 档 B 自动提炼（默认开：被动形成；文案如实写明会多用模型调用）。
        self.chat_memory_auto_extract = ToggleSwitch()
        self.chat_memory_auto_extract.setChecked(bool(config.get("chat_memory_auto_extract", True)))
        self.chat_memory_extract_interval = QSpinBox()
        self.chat_memory_extract_interval.setRange(1, 20)
        self.chat_memory_extract_interval.setValue(int(config.get("chat_memory_extract_interval", 5) or 5))
        self.chat_memory_manage_btn = QPushButton("查看与管理…", self)
        self.chat_memory_manage_btn.setProperty("variant", "ghost")
        self.chat_memory_manage_btn.clicked.connect(self._open_memory_manager)
        self.system_notify_check = ToggleSwitch()
        # 系统通知键：构造期快照无条件回写会把打开期间外部（老聊天设置即存入口
        # settings_dialog.py:437）对该键的改动静默回滚，所以只在用户实际拨动过
        # （脏标记）时才写；toggled 连接晚于这里的 setChecked，构造期不会误标。
        self._system_notify_dirty = False
        self.system_notify_check.setChecked(bool(config.get("system_notifications_enabled", True)))
        self.vision_same = ToggleSwitch()
        self.vision_same.setChecked(bool(provider.vision_same_as_chat))
        self.vision_model = _line_edit(provider.vision_model)
        self.vision_url = _line_edit(provider.vision_base_url)
        self.vision_key = _line_edit(password=True)
        # 场景扮演（每宠键）：人设决定「它是谁」，场景卡决定「在哪演」，两组互独立。
        # 真值走 config.get/set 的每宠路由，不塞进 chat 全局段。
        self.roleplay_enabled = ToggleSwitch()
        self.roleplay_enabled.setChecked(bool(config.get("roleplay_enabled", False)))
        self._roleplay_scene = str(config.get("roleplay_scene") or "")
        self._roleplay_cast = str(config.get("roleplay_cast") or "")
        self.roleplay_scene_btn = QPushButton("场景卡…", self)
        self.roleplay_scene_btn.clicked.connect(self._edit_roleplay_scene)

        self.test_button = QPushButton("测试连接")
        self.test_button.clicked.connect(self._run_test)
        self.test_result = QLabel("验证当前 Provider、API 地址和凭据是否可用。")
        self.test_result.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)
        provider_row = ResponsiveActionRow(
            self.provider_combo,
            [self.add_provider_btn, self.delete_provider_btn],
        )
        root.addWidget(SettingsSection("API 列表", [
            SettingRow(
                "provider_list", "API 列表",
                "选择要编辑/切换的模型服务；保存后当前选中项会作为 active_provider 生效。",
                provider_row,
            ),
        ], self))
        root.addWidget(SettingsSection("模型与连接", [
            SettingRow("provider_name", "Provider 名称", "用于区分当前使用的模型服务。", self.name),
            SettingRow("api_url", "API 地址", "OpenAI Chat Completions 兼容服务地址。", self.url),
            SettingRow("model", "模型", "发送请求时使用的模型标识。", self.model),
            SettingRow("api_key", "API Key", "凭据优先保存到系统钥匙串。", self.key),
            SettingRow("system_prompt", "System Prompt", "定义桌宠对话时的身份、语气和行为。", self.prompt, stacked=True),
            SettingRow("connection_test", "连接测试", self.test_result.text(), self.test_button),
        ], self))
        root.addWidget(SettingsSection("场景扮演", [
            SettingRow(
                "roleplay_enabled", "场景扮演",
                "开启后 AI 会演这个场景：动作 + 台词，并且自己带出环境细节、在场其他人的动静和"
                "场景推进，不再只是你一句我一句。场景卡约定在哪演、现场有谁；人设决定它是谁，"
                "两组互不影响。",
                self.roleplay_enabled,
            ),
            SettingRow(
                "roleplay_scene", "场景卡",
                "留空则只开启扮演格式，不约束设定。",
                self.roleplay_scene_btn,
            ),
        ], self))
        thinking_web_rows = [
            SettingRow(
                "thinking_mode", "深度思考",
                "支持思考的模型会先推理再回答，思考过程显示在回复上方（可折叠）。"
                "「跟随模型默认」不额外发送参数；开启后建议把「最大输出 Token」调到 8192 以上。",
                self.thinking_mode,
            ),
            SettingRow("reasoning_effort", "思考强度", "仅在「开启深度思考」时发送；强度越高越慢、越耗 Token。", self.reasoning_effort),
            SettingRow(
                "web_search_enabled", "联网搜索",
                "回答前先由模型判断是否需要查资料，需要时自动搜索并阅读网页，再结合结果回答；闲聊不会触发搜索。",
                self.web_search_enabled,
            ),
            SettingRow(
                "web_search_engine", "搜索引擎",
                "百度适合国内直连，DuckDuckGo 通常需要代理，两者互为备用；免 Key 引擎搜索过于频繁会被要求人机验证。需要稳定联网请选博查或 Tavily（付费 API）。",
                self.web_search_engine,
            ),
            SettingRow("web_search_key", "搜索 API Key", "博查 / Tavily 的 API Key，优先保存到系统钥匙串。", self.web_search_key),
            SettingRow("web_search_max_results", "每次搜索结果数", "单次搜索交给模型的结果条数。", self.web_search_results),
            SettingRow("web_search_fetch_pages", "允许阅读网页正文", "搜索摘要不够时，允许模型打开网页读取正文（更准，但更慢）。", self.web_search_fetch),
        ]
        root.addWidget(SettingsSection("深度思考与联网", thinking_web_rows, self))
        self._reasoning_effort_row = thinking_web_rows[1]
        self._web_detail_rows = thinking_web_rows[3:]
        self._web_key_row = thinking_web_rows[4]
        self.thinking_mode.currentIndexChanged.connect(self._update_thinking_web_visibility)
        self.web_search_enabled.toggled.connect(self._update_thinking_web_visibility)
        self.web_search_engine.currentIndexChanged.connect(self._update_thinking_web_visibility)
        self._update_thinking_web_visibility()
        root.addWidget(SettingsSection("系统通知", [
            SettingRow(
                "system_notifications_enabled", "系统通知",
                "对话完成 / 生成失败 / 需要授权时，即使切走窗口也会在桌面右下角提醒。",
                self.system_notify_check,
            ),
        ], self))
        root.addWidget(SettingsSection("助手回复朗读", [
            SettingRow(
                "chat_reply_voice_enabled", "念出回复",
                "AI 回复到达后按句念出来（含识图提问的回答）。与语音报时共用同一条"
                "音频通道，因此不会叠音；只念对话内容，不念歌词与代码。默认关闭。",
                self.chat_reply_voice,
            ),
        ], self))
        root.addWidget(SettingsSection("记忆", [
            SettingRow(
                "chat_memory_enabled", "记住用户的事",
                "开启后，每次对话都会带上你的记忆：偏好恒注，事实/教训/话题按需命中。"
                "对话里可说「记住：……」（事实）、「记住偏好：……」「记住教训：……」"
                "「记住话题：……」，或点消息气泡上的图钉添加；关闭只是不再带入，"
                "已存的记忆保留。默认开启。",
                self.chat_memory_enabled,
            ),
            SettingRow(
                "chat_memory_auto_extract", "自动整理记忆",
                "回复后自动整理记忆（会多用一点模型调用）：每轮对话后在后台静默提炼"
                "值得长期记住的事，不打断对话、失败不打扰；关闭后只保留手动钉的记忆。默认开启。",
                self.chat_memory_auto_extract,
            ),
            SettingRow(
                "chat_memory_extract_interval", "提炼频率",
                "每几轮回复整理一次记忆：1 = 每轮都整理，5 = 每 5 轮整理一次（默认，"
                "模型调用更少）；几轮里的内容会合在一起提炼，不影响记忆效果。",
                self.chat_memory_extract_interval,
            ),
            SettingRow(
                "chat_memory_manage", "记忆管理",
                "按角色保存在本地（最多 100 条 / 4000 字），按四层分组；可单条改层、"
                "删除、恢复已归档的话题，或一键清空全部四层。",
                self.chat_memory_manage_btn,
            ),
        ], self))
        vision_rows = [
            SettingRow("vision_same", "视觉模型复用聊天模型", "开启后自动选择兼容的视觉模型，用于“看看屏幕”。", self.vision_same, parent=self),
            SettingRow("vision_model", "视觉模型", "关闭复用后使用的多模态模型标识；留空则自动推导。", self.vision_model, parent=self),
            SettingRow("vision_url", "视觉 API 地址", "留空复用聊天服务地址。", self.vision_url, parent=self),
            SettingRow("vision_key", "视觉 API Key", "留空复用聊天服务凭据。", self.vision_key, parent=self),
        ]
        root.addWidget(SettingsSection("视觉能力", vision_rows, self))
        self._vision_override_rows = vision_rows[1:]
        self.vision_same.toggled.connect(self._update_vision_visibility)
        self._update_vision_visibility(self.vision_same.isChecked())
        # 用户拨动系统通知开关才置脏；连接晚于构造期 setChecked，程序化赋值不置脏。
        self.system_notify_check.toggled.connect(self._on_system_notify_edited)
        self._test_row = self.findChild(SettingRow, "settingRow_connection_test")
        if self._test_row is not None:
            self.test_result = self._test_row.hint_label
        root.addWidget(SettingsSection("生成参数（高级）", [
            SettingRow("timeout", "请求超时", "等待模型服务响应的最长时间。", self.timeout),
            SettingRow("temperature", "Temperature", "数值越高，回答越随机。", self.temperature),
            SettingRow("max_tokens", "最大输出 Token", "限制模型单次回复的最大长度；开启深度思考时思考过程也计入，建议 8192 以上。", self.tokens),
            SettingRow("skip_ssl", "跳过 SSL 证书验证", "仅用于本地网关或自签名证书。", self.skip_ssl),
        ], self, advanced=True))
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self.add_provider_btn.clicked.connect(self._add_provider)
        self.delete_provider_btn.clicked.connect(self._delete_provider)
        self._update_provider_buttons()
        root.addStretch(1)

    def _on_system_notify_edited(self, _checked: bool = False) -> None:
        """用户拨动系统通知开关 → 该键落盘脏标记（未拨动则保留外部即存值）。"""
        self._system_notify_dirty = True

    def _update_thinking_web_visibility(self, *_args) -> None:
        self._reasoning_effort_row.setVisible(self.thinking_mode.currentData() == "enabled")
        web_on = self.web_search_enabled.isChecked()
        for row in self._web_detail_rows:
            row.setVisible(web_on)
        self._web_key_row.setVisible(web_on and self.web_search_engine.currentData() in self._web_keyed_engines)
        card = self._reasoning_effort_row.parentWidget()
        if isinstance(card, SettingsCard):
            card.refresh_separators()

    def _update_vision_visibility(self, reuse_chat_model: bool) -> None:
        for row in self._vision_override_rows:
            row.setVisible(not reuse_chat_model)
        card = self._vision_override_rows[0].parentWidget() if self._vision_override_rows else None
        if isinstance(card, SettingsCard):
            card.refresh_separators()

    # ------------------------------------------------------------ API 列表管理
    @staticmethod
    def _provider_label(p) -> str:
        name = str(p.name or p.provider_id)
        model = str(p.model or '').strip()
        return f"{name} · {model}" if model else name

    def _capture_current_draft(self) -> None:
        pid = self.settings.active_provider
        if not pid or pid not in self.settings.providers:
            return
        existing = self._provider_drafts.get(pid, {})
        key_text = self.key.text()
        vkey_text = self.vision_key.text()
        self._provider_drafts[pid] = {
            "name": self.name.text().strip(),
            "base_url": self.url.text().strip(),
            "model": self.model.text().strip(),
            # 输入框为空表示“不修改/不覆盖”，保留草稿里已录入但尚未保存的 Key；
            # 否则 _load_provider_ui() 清空输入框后会把草稿 Key 覆盖成空。
            "key": key_text if key_text else existing.get("key", ""),
            "timeout": float(self.timeout.value()),
            "temperature": float(self.temperature.value()),
            "max_tokens": int(self.tokens.value()),
            "vision_model": self.vision_model.text().strip(),
            "vision_same_as_chat": self.vision_same.isChecked(),
            "vision_base_url": self.vision_url.text().strip(),
            "vision_key": vkey_text if vkey_text else existing.get("vision_key", ""),
            "verify_ssl": not self.skip_ssl.isChecked(),
            "thinking": str(self.thinking_mode.currentData() or "auto"),
            "reasoning_effort": str(self.reasoning_effort.currentData() or "high"),
        }

    def _load_provider_ui(self, provider_id: str) -> None:
        p = self.settings.providers.get(provider_id)
        if p is None:
            return
        draft = self._provider_drafts.get(provider_id, {})
        self.settings.active_provider = provider_id
        self.name.setText(draft.get("name") if draft.get("name") is not None else p.name)
        self.url.setText(draft.get("base_url") if draft.get("base_url") is not None else p.base_url)
        self.model.setText(draft.get("model") if draft.get("model") is not None else p.model)
        self.key.clear()
        self.timeout.setValue(int(draft.get("timeout", p.timeout)))
        self.temperature.setValue(float(draft.get("temperature", p.temperature)))
        self.tokens.setValue(int(draft.get("max_tokens", p.max_tokens)))
        self.vision_model.setText(draft.get("vision_model", p.vision_model))
        self.vision_same.setChecked(bool(draft.get("vision_same_as_chat", p.vision_same_as_chat)))
        self.vision_url.setText(draft.get("vision_base_url", p.vision_base_url))
        self.vision_key.clear()
        self.skip_ssl.setChecked(not bool(draft.get("verify_ssl", p.verify_ssl)))
        self.thinking_mode.setCurrentData(draft.get("thinking", p.thinking))
        self.reasoning_effort.setCurrentData(draft.get("reasoning_effort", p.reasoning_effort))
        self._update_thinking_web_visibility()
        self._update_provider_buttons()

    def _on_provider_changed(self, _index: int = -1) -> None:
        if self._loading_provider:
            return
        self._capture_current_draft()
        pid = self.provider_combo.currentData()
        if pid and pid in self.settings.providers:
            self._load_provider_ui(pid)

    def _new_provider_id(self) -> str:
        # 避免复用已删除的 provider_id：否则保存合并时新建项会被删除集合过滤掉。
        used = set(self.settings.providers) | set(self._deleted_provider_ids)
        i = len(self.settings.providers) + 1
        while f"api-{i}" in used:
            i += 1
        return f"api-{i}"

    def _add_provider(self) -> None:
        self._capture_current_draft()
        base = self.settings.active_config
        new_id = self._new_provider_id()
        new = self._provider_config_type(
            new_id,
            name=f"{base.name} 副本",
            base_url=base.base_url,
            chat_path=base.chat_path,
            model=base.model,
            api_key_ref=f"provider/{new_id}",
            timeout=base.timeout,
            temperature=base.temperature,
            max_tokens=base.max_tokens,
            vision_model=base.vision_model,
            vision_same_as_chat=base.vision_same_as_chat,
            vision_base_url=base.vision_base_url,
            vision_api_key_ref=f"provider/{new_id}/vision",
            verify_ssl=base.verify_ssl,
            thinking=base.thinking,
            reasoning_effort=base.reasoning_effort,
        )
        self.settings.providers[new_id] = new
        self._provider_drafts[new_id] = {
            "name": new.name,
            "base_url": new.base_url,
            "model": new.model,
            "key": "",
            "timeout": new.timeout,
            "temperature": new.temperature,
            "max_tokens": new.max_tokens,
            "vision_model": new.vision_model,
            "vision_same_as_chat": new.vision_same_as_chat,
            "vision_base_url": new.vision_base_url,
            "vision_key": "",
            "verify_ssl": new.verify_ssl,
            "thinking": new.thinking,
            "reasoning_effort": new.reasoning_effort,
        }
        self._loading_provider = True
        try:
            self.provider_combo.addItem(self._provider_label(new), new_id)
            self.provider_combo.setCurrentIndex(self.provider_combo.count() - 1)
        finally:
            self._loading_provider = False
        self.settings.active_provider = new_id
        self._load_provider_ui(new_id)
        self._update_provider_buttons()

    def _delete_provider(self) -> None:
        if len(self.settings.providers) <= 1:
            return
        pid = self.provider_combo.currentData()
        if not pid or pid not in self.settings.providers:
            return
        self.settings.providers.pop(pid, None)
        self._provider_drafts.pop(pid, None)
        self._deleted_provider_ids.add(pid)
        self._loading_provider = True
        try:
            self.provider_combo.clear()
            for p in self.settings.providers.values():
                self.provider_combo.addItem(self._provider_label(p), p.provider_id)
            self.settings.active_provider = next(iter(self.settings.providers))
            self.provider_combo.setCurrentData(self.settings.active_provider)
        finally:
            self._loading_provider = False
        self._load_provider_ui(self.settings.active_provider)
        self._update_provider_buttons()

    def _update_provider_buttons(self) -> None:
        self.delete_provider_btn.setEnabled(len(self.settings.providers) > 1)

    def _apply_draft_to_provider(self, provider_id: str) -> None:
        p = self.settings.providers.get(provider_id)
        draft = self._provider_drafts.get(provider_id)
        if p is None or not draft:
            return
        if draft.get("name"):
            p.name = draft["name"]
        p.base_url = draft.get("base_url") or p.base_url
        p.model = draft.get("model") or p.model
        p.timeout = float(draft.get("timeout", p.timeout))
        p.temperature = float(draft.get("temperature", p.temperature))
        p.max_tokens = int(draft.get("max_tokens", p.max_tokens))
        p.vision_model = draft.get("vision_model", p.vision_model)
        p.vision_same_as_chat = bool(draft.get("vision_same_as_chat", p.vision_same_as_chat))
        p.vision_base_url = draft.get("vision_base_url", p.vision_base_url)
        p.verify_ssl = bool(draft.get("verify_ssl", p.verify_ssl))
        p.thinking = str(draft.get("thinking", p.thinking) or "auto")
        p.reasoning_effort = str(draft.get("reasoning_effort", p.reasoning_effort) or "high")
        key = str(draft.get("key") or "")
        if key:
            p.api_key_ref = p.api_key_ref or f"provider/{provider_id}"
            if not self._secret_store_type().set(p.api_key_ref, key):
                p.api_key = key
                QMessageBox.warning(self, "安全存储不可用", "无法使用系统安全存储，Key 仅本次运行保留，重启需重输。")
        vkey = str(draft.get("vision_key") or "")
        if vkey:
            p.vision_api_key_ref = p.vision_api_key_ref or f"provider/{provider_id}/vision"
            if not self._secret_store_type().set(p.vision_api_key_ref, vkey):
                p.vision_api_key = vkey
                QMessageBox.warning(self, "安全存储不可用", "无法使用系统安全存储，Key 仅本次运行保留，重启需重输。")

    def _apply_web_search_settings(self) -> None:
        web = self.settings.web_search
        web.enabled = self.web_search_enabled.isChecked()
        web.engine = str(self.web_search_engine.currentData() or "baidu")
        web.max_results = int(self.web_search_results.value())
        web.fetch_pages = self.web_search_fetch.isChecked()
        key = self.web_search_key.text().strip()
        if key:
            web.api_key_ref = web.api_key_ref or "websearch/api"
            if self._secret_store_type().set(web.api_key_ref, key):
                web.api_key = ""
            else:
                web.api_key = key
                QMessageBox.warning(self, "安全存储不可用", "无法使用系统安全存储，搜索 API Key 仅本次运行保留，重启需重输。")
            self.web_search_key.clear()
        self.settings.attach_runtime()

    def provisional_config(self):
        provider = self.settings.active_config
        return self._provider_config_type(
            provider.provider_id,
            self.name.text().strip() or provider.name,
            self.url.text().strip(),
            provider.chat_path,
            self.model.text().strip(),
            provider.api_key_ref,
            # 表单未填时回退钥匙串：凭据默认存系统钥匙串，直接读 api_key 为空
            self.key.text() or provider.api_key or self._secret_store_type().get(provider.api_key_ref),
            float(self.timeout.value()),
            float(self.temperature.value()),
            int(self.tokens.value()),
            verify_ssl=not self.skip_ssl.isChecked(),
            thinking=str(self.thinking_mode.currentData() or "auto"),
            reasoning_effort=str(self.reasoning_effort.currentData() or "high"),
        )

    def _run_test(self) -> None:
        if self._test_thread is not None and self._test_thread.is_alive():
            return
        self.test_button.setEnabled(False)
        self.test_button.setText("测试中…")
        self.test_result.setText("正在连接模型服务…")
        self._test_thread = threading.Thread(
            target=self._run_test_worker,
            args=(self.provisional_config(),),
            daemon=True,
            name="pet-modern-settings-connection-test",
        )
        self._test_thread.start()

    def _run_test_worker(self, provider) -> None:
        result = self._test_connection(provider, timeout=10.0)
        # 对话框可能在测试在飞时被关闭销毁（WA_DeleteOnClose）：直接
        # self.test_done.emit 会对已删 C++ 对象 RuntimeError。
        _safe_emit(self, "test_done", *result)

    def _on_test_done(self, ok: bool, message: str) -> None:
        self.test_button.setEnabled(True)
        self.test_button.setText("测试连接")
        self.test_result.setText(message)
        self.test_result.setStyleSheet("color: #16843b;" if ok else "color: #c9362b;")
        self._test_thread = None

    def _edit_roleplay_scene(self) -> None:
        """打开场景卡编辑窗；结果先留在本页，随宿主的 save() 一起按每宠键落盘。"""
        dialog = RoleplaySceneDialog(self._roleplay_scene, self._roleplay_cast, self)
        accepted = dialog.exec()
        if accepted == QDialog.DialogCode.Accepted:
            self._roleplay_scene, self._roleplay_cast = dialog.values()
        dialog.deleteLater()

    def save(self) -> None:
        # 保存前基于磁盘最新配置重取快照：另一个设置窗口（AI 设置/桌宠设置 AI 页）
        # 可能在本窗口打开期间改过 Provider 结构；先保留本窗口的 provider 草稿/
        # 新增/删除，再与磁盘快照合并，避免覆盖其它窗口新增的结构。
        old_settings = self.settings
        self._capture_current_draft()
        self.settings = self.config.chat_settings()
        for pid in list(self.settings.providers):
            if pid in self._deleted_provider_ids:
                self.settings.providers.pop(pid, None)
        for pid, provider in old_settings.providers.items():
            if pid not in self.settings.providers and pid not in self._deleted_provider_ids:
                self.settings.providers[pid] = provider
        active_pid = self.provider_combo.currentData()
        if active_pid in self.settings.providers:
            self.settings.active_provider = active_pid
        elif self.settings.providers:
            self.settings.active_provider = next(iter(self.settings.providers))
        for pid in list(self.settings.providers):
            self._apply_draft_to_provider(pid)
        self.settings.default_system_prompt = self.prompt.toPlainText().strip()
        # 场景扮演三键是每宠键：SlotRoutedConfig 会把它们写进这只宠的 slot 档案。
        self.config.set("roleplay_enabled", self.roleplay_enabled.isChecked())
        self.config.set("roleplay_scene", self._roleplay_scene)
        self.config.set("roleplay_cast", self._roleplay_cast)
        self._apply_web_search_settings()
        # 系统通知按脏标记合并：未拨动开关保持磁盘最新值（宿主 save 前已 reload），
        # 打开期间外部（老聊天设置即存）对该键的改动不被构造期快照回滚。
        if self._system_notify_dirty:
            self.config.set("system_notifications_enabled", self.system_notify_check.isChecked())
        self.config.set("chat_reply_voice_enabled", self.chat_reply_voice.isChecked())
        self.config.set("chat_memory_enabled", self.chat_memory_enabled.isChecked())
        self.config.set("chat_memory_auto_extract", self.chat_memory_auto_extract.isChecked())
        self.config.set("chat_memory_extract_interval", int(self.chat_memory_extract_interval.value()))
        self.config.set_chat_settings(self.settings)

    def _chat_memory(self) -> ChatMemory:
        """当前角色的对话全局记忆（与聊天窗同一份文件；设置页常是独立进程，
        跨进程互斥在 ChatMemory 的 QLockFile 层）。"""
        character = str(self.config.get("character") or "")
        return ChatMemory(memory_path(self.config.dir, getattr(self.config, "instance_id", ""), character))

    def _open_memory_manager(self):
        # 情景记忆卡与关键词记忆卡同目录，文件名 episodic-memory.json
        character = str(self.config.get("character") or "")
        ep_path = memory_path(
            self.config.dir,
            getattr(self.config, "instance_id", ""),
            character,
        ).with_name("episodic-memory.json")
        dialog = ChatMemoryDialog(
            self._chat_memory(), self, episodic_path=ep_path, character=character,
            config=self.config, instance_id=getattr(self.config, "instance_id", ""))
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.show()
        return dialog


class RoleplaySceneDialog(QDialog):
    """场景卡编辑窗：场景描述多行 + 在场人物多行（每行一个「名字：描述」）。"""

    SCENE_PLACEHOLDER = "示例：雨夜的便利店，灯管忽明忽暗，货架上只剩最后一盒草莓牛奶。"
    CAST_PLACEHOLDER = "示例：店员阿澈：总在擦同一个杯子，说话前先叹口气。"

    def __init__(self, scene: str = "", cast: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("roleplay-scene-dialog")
        self.setWindowTitle("场景卡")
        self.setMinimumWidth(520)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        intro = QLabel(
            "场景卡决定「在哪演」，人设决定「它是谁」，两组互不影响。"
            "留空则只开启扮演格式，不约束设定。",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        scene_label = QLabel(f"场景描述（时间 / 地点 / 氛围，≤{ROLEPLAY_SCENE_MAX_CHARS} 字）", self)
        root.addWidget(scene_label)
        self.scene_edit = QPlainTextEdit(self)
        self.scene_edit.setPlaceholderText(self.SCENE_PLACEHOLDER)
        self.scene_edit.setPlainText(str(scene or ""))
        self.scene_edit.setMinimumHeight(100)
        root.addWidget(self.scene_edit)
        self.scene_counter = QLabel(self)
        self.scene_counter.setObjectName("roleplay-scene-counter")
        root.addWidget(self.scene_counter)

        cast_label = QLabel(
            f"在场人物（每行一个「名字：一句辨识度描述」，≤{ROLEPLAY_CAST_MAX_CHARS} 字）",
            self,
        )
        root.addWidget(cast_label)
        self.cast_edit = QPlainTextEdit(self)
        self.cast_edit.setPlaceholderText(self.CAST_PLACEHOLDER)
        self.cast_edit.setPlainText(str(cast or ""))
        self.cast_edit.setMinimumHeight(120)
        root.addWidget(self.cast_edit)
        self.cast_counter = QLabel(self)
        self.cast_counter.setObjectName("roleplay-cast-counter")
        root.addWidget(self.cast_counter)

        self.truncation_hint = QLabel(self)
        self.truncation_hint.setObjectName("roleplay-truncation-hint")
        self.truncation_hint.setWordWrap(True)
        self.truncation_hint.setStyleSheet("color: #c9362b;")
        self.truncation_hint.hide()
        root.addWidget(self.truncation_hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._on_save_clicked)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._truncated = False       # 本次 values() 是否发生了截断（防御分支用）
        self.scene_edit.textChanged.connect(self._on_edited)
        self.cast_edit.textChanged.connect(self._on_edited)
        self._update_counters()

    @staticmethod
    def _truncate_scene(text: str) -> tuple[str, bool]:
        """场景按字符截断，保留末尾 ``…``（总长仍不超过上限）。"""
        if len(text) <= ROLEPLAY_SCENE_MAX_CHARS:
            return text, False
        return text[: ROLEPLAY_SCENE_MAX_CHARS - 1] + "…", True

    @staticmethod
    def _truncate_cast(text: str) -> tuple[str, bool]:
        """人物按整行截断：放不下的整行直接不要，绝不从某一行中间切断。"""
        kept: list[str] = []
        used = 0
        for line in text.split("\n"):
            extra = len(line) + (1 if kept else 0)
            if used + extra > ROLEPLAY_CAST_MAX_CHARS:
                return "\n".join(kept), True
            kept.append(line)
            used += extra
        return text, False

    @staticmethod
    def _set_counter(label: QLabel, length: int, limit: int) -> bool:
        label.setText(f"{length}/{limit}")
        over = length > limit
        label.setStyleSheet("color: #c9362b;" if over else "color: rgba(128,128,128,0.9);")
        return over

    def _update_counters(self) -> None:
        # 计数与禁用判据必须和 values() 的落盘口径一致：先 strip 再算长度。
        # 否则尾随空行会让计数超限、保存按钮被锁死，而 values() 实际存的是合规内容。
        scene_over = self._set_counter(
            self.scene_counter, len(self.scene_edit.toPlainText().strip()),
            ROLEPLAY_SCENE_MAX_CHARS)
        cast_over = self._set_counter(
            self.cast_counter, len(self.cast_edit.toPlainText().strip()),
            ROLEPLAY_CAST_MAX_CHARS)
        over = scene_over or cast_over
        if over:
            # 超限就不让保存：用户看得见红计数与这句话，自己删到范围内。
            # 不做「保存时静默截断」——那是把用户写的内容无声丢掉。
            self.truncation_hint.setText("超出上限，请删减到上限以内再保存（不会自动截断）")
            self.truncation_hint.show()
        else:
            self.truncation_hint.hide()
        self.save_button.setEnabled(not over)

    def _on_edited(self) -> None:
        self._update_counters()

    def _show_truncation(self, scene_cut: bool, cast_cut: bool) -> None:
        parts: list[str] = []
        if scene_cut:
            parts.append(f"场景描述超出 {ROLEPLAY_SCENE_MAX_CHARS} 字，已截断并补「…」。")
        if cast_cut:
            parts.append(
                f"在场人物超出 {ROLEPLAY_CAST_MAX_CHARS} 字，已按整行截断（没有切断某一行）。")
        self.truncation_hint.setText(" ".join(parts))
        self.truncation_hint.show()

    def _on_save_clicked(self) -> None:
        """保存。内容超限时保存按钮是禁用的（见 ``_update_counters``），点不动。

        下面这条 ``_truncated`` 分支只是防御：万一外部代码绕开按钮直接 accept，
        也不会把截断后的内容当成用户原样内容静默存下去。
        """
        self.values()
        if self._truncated:
            return
        self.accept()

    def values(self) -> tuple[str, str]:
        """返回 (场景描述, 在场人物)，多行内部换行原样保留。

        正常路径（用户在对话框里操作）不会走到截断：超限时保存按钮禁用，用户必须先删。
        这里的截断只是**防御性兜底**（外部代码直接调 values 时），场景按字符截断并补
        ``…``、人物按整行截断，一旦发生就把提示摆出来。
        """
        scene_raw = self.scene_edit.toPlainText().strip()
        cast_raw = self.cast_edit.toPlainText().strip()
        scene, scene_cut = self._truncate_scene(scene_raw)
        cast, cast_cut = self._truncate_cast(cast_raw)
        self._truncated = scene_cut or cast_cut
        if self._truncated:
            self._show_truncation(scene_cut, cast_cut)
        return scene, cast


class ChatMemoryDialog(QDialog):
    """「记忆管理」对话框：四层分组 / 单条改层 / 删除 / 归档 topic 恢复 / 全部清空。

    每次操作后从 ChatMemory 重读重排：本对话框（可能在独立设置进程）与主进程
    聊天窗的「记住：……」/「钉为记忆」写同一个 memory.json，展示以盘上为准。
    """

    def __init__(self, memory: ChatMemory, parent=None, episodic_path=None, character="",
                 config=None, instance_id=""):
        super().__init__(parent)
        self.memory = memory
        self.character = str(character or "")
        self.config = config
        self.instance_id = str(instance_id or "")
        # 叶瞬光式情景记忆卡路径（可选）：有则显示「情景回忆」标签页
        from pathlib import Path
        self.episodic = EpisodicMemory(Path(episodic_path)) if episodic_path else None
        self._rows: list[QWidget] = []  # 只数条目行（组标题不计），兼容旧测试口径
        self.setObjectName("chat-memory-dialog")
        self.setWindowTitle("记忆管理")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # 角色切换下拉：可查看三只桌宠各自的记忆（各自独立、互不共享）
        self._ROLE_IDS = ("角色A", "角色B", "角色C")
        if self.config is not None:
            top = QHBoxLayout()
            hint = QLabel("查看谁的记忆：", self)
            hint.setStyleSheet("color: rgba(160,160,160,0.95); font-size: 12px;")
            top.addWidget(hint)
            self.role_combo = QComboBox(self)
            self.role_combo.setObjectName("chat-memory-role-combo")
            for cid in self._ROLE_IDS:
                self.role_combo.addItem(self.config.character_display_name(cid), cid)
            idx = self.role_combo.findData(self.character)
            if idx >= 0:
                self.role_combo.setCurrentIndex(idx)
            self.role_combo.currentIndexChanged.connect(self._on_role_changed)
            top.addWidget(self.role_combo)
            top.addStretch(1)
            root.addLayout(top)
            self._update_title()

        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs, 1)

        # --- 标签1：长期记忆（关键词四层，原有逻辑不变）---
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(180)
        self.scroll.setMaximumHeight(380)
        self.host = QWidget()
        self.host_layout = QVBoxLayout(self.host)
        self.host_layout.setContentsMargins(0, 0, 0, 0)
        self.host_layout.setSpacing(6)
        self.scroll.setWidget(self.host)
        self.tabs.addTab(self.scroll, "长期记忆")

        # --- 标签2：情景回忆（叶瞬光式"她记住的更早对话"）---
        if self.episodic is not None:
            self.ep_scroll = QScrollArea(self)
            self.ep_scroll.setWidgetResizable(True)
            self.ep_scroll.setMinimumHeight(180)
            self.ep_scroll.setMaximumHeight(380)
            self.ep_host = QWidget()
            self.ep_layout = QVBoxLayout(self.ep_host)
            self.ep_layout.setContentsMargins(0, 0, 0, 0)
            self.ep_layout.setSpacing(8)
            self.ep_scroll.setWidget(self.ep_host)
            self.tabs.addTab(self.ep_scroll, "情景回忆")
            self._reload_episodic()

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        self.count_label = QLabel(self)
        self.count_label.setObjectName("chat-memory-count")
        footer.addWidget(self.count_label)
        footer.addStretch(1)
        self.clear_btn = QPushButton("全部清空…", self)
        self.clear_btn.setProperty("variant", "ghost")
        self.clear_btn.clicked.connect(self._clear_all)
        footer.addWidget(self.clear_btn)
        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)
        self._reload()

    def _update_title(self) -> None:
        if self.config is not None and self.character:
            name = self.config.character_display_name(self.character)
            self.setWindowTitle(f"记忆管理 - {name}")
        else:
            self.setWindowTitle("记忆管理")

    def _on_role_changed(self, index: int) -> None:
        """切换查看的角色：按角色重算记忆卡路径（三只各自独立目录）。"""
        if self.config is None or index < 0:
            return
        cid = str(self.role_combo.itemData(index) or "")
        if not cid:
            return
        self.character = cid
        base = memory_path(self.config.dir, cid, cid)  # instance 与角色同名
        self.memory = ChatMemory(base)
        if self.episodic is not None:
            self.episodic = EpisodicMemory(base.with_name("episodic-memory.json"))
        self._update_title()
        self._reload()
        if hasattr(self, "ep_layout"):
            self._reload_episodic()

    def _reload_episodic(self) -> None:
        """渲染「情景回忆」标签页：叶瞬光式事后回忆（日期 + 清晰度状态）。"""
        if self.episodic is None:
            return
        while self.ep_layout.count():
            item = self.ep_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        episodes = self.episodic.all_episodes()
        if not episodes:
            empty = QLabel(
                "还没有情景回忆。聊过一阵、静默一会儿后，她会把值得记住的对话"
                "压成一条「事后回忆」存这里——这是她能想起更早对话的依据。",
                self.ep_host,
            )
            empty.setWordWrap(True)
            self.ep_layout.addWidget(empty)
            self.ep_layout.addStretch(1)
            return
        head_row = QWidget(self.ep_host)
        head_layout = QHBoxLayout(head_row)
        head_layout.setContentsMargins(0, 0, 0, 0)
        header = QLabel(f"共 {len(episodes)} 条（越旧越模糊，太久的会自然忘记）", head_row)
        header.setStyleSheet("font-weight: 600; color: rgba(160,160,160,0.95);")
        head_layout.addWidget(header)
        head_layout.addStretch(1)
        clear_btn = QPushButton("全部清空…", head_row)
        clear_btn.setProperty("variant", "ghost")
        clear_btn.clicked.connect(self._clear_episodes)
        head_layout.addWidget(clear_btn)
        self.ep_layout.addWidget(head_row)
        # 新的在前：一条一条，每条带日期/清晰度标记 + 删除按钮
        for ep in reversed(episodes):
            fuzzy = clarity_of(ep) < FUZZY_CLARITY
            date = str(ep.get("date", ""))
            text = str(ep.get("text", ""))
            badge = "模糊" if fuzzy else "清晰"
            ep_id = str(ep.get("id", ""))
            row = QWidget(self.ep_host)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            text_label = QLabel(f"（{date} · {badge}）{text}", row)
            text_label.setWordWrap(True)
            text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if fuzzy:
                text_label.setStyleSheet("color: rgba(140,140,140,0.85);")
            row_layout.addWidget(text_label, 1)
            del_btn = QPushButton("删除", row)
            del_btn.setProperty("variant", "ghost")
            del_btn.setObjectName(f"chat-episode-delete-{ep_id}")
            del_btn.clicked.connect(
                lambda _checked=False, eid=ep_id: self._delete_episode(eid))
            row_layout.addWidget(del_btn, 0, Qt.AlignmentFlag.AlignTop)
            self.ep_layout.addWidget(row)
        self.ep_layout.addStretch(1)

    def _delete_episode(self, episode_id: str) -> None:
        if self.episodic is None:
            return
        if not self.episodic.remove(episode_id):
            QMessageBox.warning(self, "删除失败", "记忆文件正被占用，请稍后再试。")
        self._reload_episodic()

    def _clear_episodes(self) -> None:
        if self.episodic is None:
            return
        n = len(self.episodic.all_episodes())
        if n == 0:
            return
        reply = QMessageBox.question(
            self, "清空情景回忆",
            f"确定清空全部 {n} 条情景回忆？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.episodic.clear()
        self._reload_episodic()

    def _row_count(self) -> int:
        return len(self._rows)

    def _reload(self) -> None:
        # 清空所有布局项（含上一次的 stretch），避免反复改层/恢复后残留 spacer。
        while self.host_layout.count():
            item = self.host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = []
        groups = self.memory.load_grouped()
        now = datetime.now().astimezone()
        total = sum(len(entries) for entries in groups.values())
        if not total:
            empty = QLabel(
                "还没有记忆。在对话里说「记住：……」「记住偏好：……」「记住教训：……」"
                "「记住话题：……」，或点消息气泡上的图钉添加。",
                self.host,
            )
            empty.setWordWrap(True)
            self.host_layout.addWidget(empty)
            self._rows.append(empty)
        for layer in LAYERS:
            entries = groups[layer]
            if not entries:
                continue
            header = QLabel(f"{LAYER_LABELS[layer]}（{len(entries)}）", self.host)
            header.setObjectName(f"chat-memory-group-{layer}")
            header.setStyleSheet(
                "font-weight: 600; color: rgba(160,160,160,0.95); margin-top: 4px;")
            self.host_layout.addWidget(header)
            for entry in entries:
                row = self._entry_row(entry, layer, now)
                self.host_layout.addWidget(row)
                self._rows.append(row)
        self.host_layout.addStretch(1)
        self.count_label.setText(
            f"共 {total} 条（上限 100 条 / 4000 字）" if total else "")
        self.clear_btn.setEnabled(total > 0)

    def _entry_row(self, entry: dict, layer: str, now: datetime) -> QWidget:
        row = QWidget(self.host)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        # 来源标记：manual = 手动钉（档 A），auto = 回复后自动提炼（档 B）
        source_badge = QLabel("自动" if str(entry.get("source")) == "auto" else "手动", row)
        source_badge.setObjectName("chat-memory-source")
        source_badge.setStyleSheet(
            "color: rgba(128,128,128,0.9); font-size: 11px;"
            "border: 1px solid rgba(128,128,128,0.35); border-radius: 4px; padding: 0 4px;")
        layout.addWidget(source_badge, 0, Qt.AlignmentFlag.AlignTop)
        archived = layer == "topic" and is_archived(entry, now)
        text = QLabel(str(entry.get("text", "")), row)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if archived:
            text.setStyleSheet("color: rgba(128,128,128,0.6);")
        layout.addWidget(text, 1)
        entry_id = str(entry.get("id", ""))
        if not archived:
            # 单条改层：四层下拉（改层立即落盘并重排）。归档行不渲染层下拉
            # （v2b E：`update_layer` 会清 archived，等于第二条静默恢复通道），
            # 只保留「恢复」按钮。
            layer_combo = QComboBox(row)
            layer_combo.setObjectName(f"chat-memory-layer-{entry_id}")
            layer_combo.setFixedWidth(92)
            for name in LAYERS:
                layer_combo.addItem(LAYER_LABELS[name], name)
            layer_combo.setCurrentIndex(LAYERS.index(layer_of(entry)))
            layer_combo.currentIndexChanged.connect(
                lambda _index, eid=entry_id, combo=layer_combo: self._change_layer(
                    eid, str(combo.currentData())))
            layout.addWidget(layer_combo, 0, Qt.AlignmentFlag.AlignTop)
        if archived:
            restore_btn = QPushButton("恢复", row)
            restore_btn.setObjectName(f"chat-memory-restore-{entry_id}")
            restore_btn.setProperty("variant", "ghost")
            restore_btn.clicked.connect(
                lambda _checked=False, eid=entry_id: self._restore_entry(eid))
            layout.addWidget(restore_btn, 0, Qt.AlignmentFlag.AlignTop)
        delete_btn = QPushButton("删除", row)
        delete_btn.setProperty("variant", "ghost")
        delete_btn.clicked.connect(lambda _checked=False, eid=entry_id: self._delete_entry(eid))
        layout.addWidget(delete_btn)
        return row

    def _change_layer(self, entry_id: str, layer: str) -> None:
        if not self.memory.update_layer(entry_id, layer):
            QMessageBox.warning(self, "改层失败", "记忆文件正被占用，请稍后再试。")
        self._reload()

    def _restore_entry(self, entry_id: str) -> None:
        if not self.memory.restore_topic(entry_id):
            QMessageBox.warning(self, "恢复失败", "记忆文件正被占用，请稍后再试。")
        self._reload()

    def _delete_entry(self, entry_id: str) -> None:
        if not self.memory.remove(entry_id):
            QMessageBox.warning(self, "删除失败", "记忆文件正被占用，请稍后再试。")
        self._reload()

    def _clear_all(self) -> None:
        entries = self.memory.load()
        if not entries:
            return
        answer = QMessageBox.question(
            self,
            "清空全部记忆",
            f"确定删除全部 {len(entries)} 条记忆吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        # clear() 返回本次是否真的清空：拿不到跨进程锁（主进程正在写）= 这次没清，
        # 必须如实提示，不能无条件报"已清空"（同 proactive_memory 设置页口径）。
        if not self.memory.clear():
            QMessageBox.warning(self, "记忆清空失败", "记忆文件正被占用，请稍后再试。")
        self._reload()
