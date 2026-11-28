# -*- coding: utf-8 -*-
"""官方厂商预设（按厂商添加）：预设表数据 + 设置页交互 + 落盘回归。

预设表是纯数据契约（models.PROVIDER_PRESETS）；交互链在 _AiSettingsPage。
不访问任何真实厂商端点。
"""
from __future__ import annotations

import pytest

from pet.chat.models import PROVIDER_PRESETS, ChatSettings, ProviderConfig


# ---------------------------------------------------------------- 预设表数据契约
def test_preset_table_shape():
    """每条预设必须有 label/base_url/chat_path/model，且 URL 是合法 https(s)。"""
    from urllib.parse import urlsplit

    assert len(PROVIDER_PRESETS) >= 6, "厂商预设不应缩水"
    for pid, preset in PROVIDER_PRESETS.items():
        for field in ("label", "base_url", "chat_path", "model", "models", "key_hint"):
            assert preset.get(field), f"{pid} 缺 {field}"
        parts = urlsplit(preset["base_url"])
        assert parts.scheme in ("https", "http"), f"{pid} base_url 非法"
        assert parts.hostname, f"{pid} base_url 缺主机名"
        assert preset["chat_path"].startswith("/"), f"{pid} chat_path 必须以 / 开头"


def test_preset_urls_match_known_official_endpoints():
    """官方地址白名单：改这里之前先确认厂商文档没变（地址错=用户 Key 全 401）。"""
    expected = {
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",
        "siliconflow": "https://api.siliconflow.cn/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "moonshot": "https://api.moonshot.cn/v1",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
        "local": "http://127.0.0.1:11434/v1",
    }
    for pid, url in expected.items():
        assert PROVIDER_PRESETS[pid]["base_url"] == url


def test_preset_endpoints_normalize_to_chat_completions():
    """每条预设经 normalize_chat_endpoint 后都落在该厂商的 chat/completions 上。"""
    from pet.chat.providers import normalize_chat_endpoint

    for pid, preset in PROVIDER_PRESETS.items():
        endpoint = normalize_chat_endpoint(preset["base_url"], preset["chat_path"])
        assert endpoint.endswith("chat/completions"), f"{pid} 归一化后异常：{endpoint}"


def test_preset_feeds_provider_config():
    """预设字段与 ProviderConfig 构造兼容（名字对得上，防止改字段名后预设悄悄失效）。"""
    p = ProviderConfig(
        "t",
        name=PROVIDER_PRESETS["zhipu"]["label"],
        base_url=PROVIDER_PRESETS["zhipu"]["base_url"],
        chat_path=PROVIDER_PRESETS["zhipu"]["chat_path"],
        model=PROVIDER_PRESETS["zhipu"]["model"],
        api_key_ref="provider/t",
    )
    assert p.base_url.startswith("https://open.bigmodel.cn")
    assert ChatSettings.from_dict(ChatSettings.defaults().to_dict()).active_config.model


# ---------------------------------------------------------------- 设置页交互
@pytest.fixture
def page_env(tmp_path, monkeypatch):
    """隔离钥匙串 + 最小 Qt 环境 + 干净配置的设置页。"""
    from pet.chat import models
    from pet.config import Config

    stored = {}
    monkeypatch.setattr(models.SecretStore, "set",
                        lambda self, ref, value: stored.__setitem__(ref, value) or True)
    monkeypatch.setattr(models.SecretStore, "get", lambda self, ref: stored.get(ref, ""))
    qapp_mod = pytest.importorskip("PySide6.QtWidgets")
    app = qapp_mod.QApplication.instance() or qapp_mod.QApplication([])
    cfg = Config(tmp_path)
    from pet.chat.ai_settings_page import _AiSettingsPage
    page = _AiSettingsPage(cfg)
    yield page, cfg, stored
    page.close()
    app.processEvents()


def test_preset_combo_lists_all_presets(page_env):
    page, cfg, _stored = page_env
    labels = [page.preset_combo.itemText(i) for i in range(page.preset_combo.count())]
    assert len(labels) == len(PROVIDER_PRESETS)
    assert "智谱 GLM" in labels and "DeepSeek" in labels


def test_add_preset_creates_provider_with_preset_values(page_env):
    """点「按厂商添加」→ 新 Provider 的 URL/模型/路径来自预设，并成为当前编辑项。"""
    page, cfg, _stored = page_env
    page.preset_combo.setCurrentData("deepseek")
    before = len(page.settings.providers)
    page._add_preset_provider()

    assert len(page.settings.providers) == before + 1
    new_pid = page.settings.active_provider
    assert new_pid != "openai-main", "新建后应切到新 Provider"
    p = page.settings.providers[new_pid]
    assert p.name == "DeepSeek"
    assert p.base_url == "https://api.deepseek.com/v1"
    assert p.chat_path == "/chat/completions"
    assert p.model == "deepseek-chat"
    assert p.api_key_ref == f"provider/{new_pid}"
    # UI 已切到新项（用户直接贴 Key）
    assert page.url.text() == "https://api.deepseek.com/v1"
    assert page.model.text() == "deepseek-chat"
    assert "deepseek" in page.key.placeholderText().lower() or \
           "平台" in page.key.placeholderText() or "Key" in page.key.placeholderText()


def test_add_preset_local_marks_no_key_needed(page_env):
    """本地模型预设：占位文案明说无需 Key。"""
    page, cfg, _stored = page_env
    page.preset_combo.setCurrentData("local")
    page._add_preset_provider()
    assert "无需" in page.key.placeholderText() or "留空" in page.key.placeholderText()


def test_add_preset_then_paste_key_and_save_roundtrip(page_env):
    """完整用户路径：预设添加 → 贴 Key → 保存 → 重读后 URL/模型/路径无损。"""
    page, cfg, stored = page_env
    page.preset_combo.setCurrentData("siliconflow")
    page._add_preset_provider()
    pid = page.settings.active_provider
    page.key.setText("sk-sf-test-123")
    page.save()
    assert cfg.save(), "设置页保存后必须落盘"

    reloaded = cfg.chat_settings()
    p = reloaded.providers[pid]
    assert p.base_url == "https://api.siliconflow.cn/v1"
    assert p.chat_path == "/chat/completions"
    assert p.model == "Qwen/Qwen2.5-7B-Instruct"
    assert reloaded.active_provider == pid
    # Key 进钥匙串不落盘（Provider 用 api_key_ref 直查 SecretStore）
    assert p.api_key == ""
    from pet.chat.models import SecretStore
    assert SecretStore().get(p.api_key_ref) == "sk-sf-test-123"


def test_plain_add_still_copies_active_provider(page_env):
    """原「添加」（副本语义）不受预设改造影响。"""
    page, cfg, _stored = page_env
    original_name = page.settings.active_config.name
    original_url = page.settings.active_config.base_url
    page._add_provider()
    new_p = page.settings.active_config
    assert new_p.name == f"{original_name} 副本"
    assert new_p.base_url == original_url


def test_first_open_shows_keyring_state_in_placeholder(page_env):
    """构造路径（首次打开设置）必须按钥匙串实况显示 Key 占位文案。

    2026-11-28 实机误报：Key 已入钥匙串，重开设置只见空框无任何提示，
    用户以为 Key 丢了——占位文案此前只在切换 Provider 时设置。
    """
    page, cfg, stored = page_env
    p = page.settings.active_config
    # 未存：明确说"尚未保存"
    assert "尚未保存" in page.key.placeholderText()
    # 存了：明确说"已保存"（Key 永不回显，但状态必须可见）
    stored[p.api_key_ref] = "sk-xyz"
    page._refresh_key_display(p)
    assert "已保存" in page.key.placeholderText()
    # 视觉 Key 同口径
    assert "尚未保存" in page.vision_key.placeholderText()


def test_refresh_placeholders_survives_keyring_failure(page_env, monkeypatch):
    """钥匙串读失败按未存提示，不能崩设置页。"""
    page, cfg, _stored = page_env
    from pet.chat import models
    def _boom(self, ref):
        raise OSError("keyring 不可用")
    monkeypatch.setattr(models.SecretStore, "get", _boom)
    page._refresh_key_display(page.settings.active_config)
    assert "尚未保存" in page.key.placeholderText()


# ---------------------------------------------------------------- Key 掩码显示
def test_stored_key_shows_mask_not_blank(page_env):
    """用户要求：Key 已存时输入框显示掩码，不许空白。"""
    from pet.chat.ai_settings_page import KEY_MASK
    page, cfg, stored = page_env
    p = page.settings.active_config
    stored[p.api_key_ref] = "sk-real-key"
    stored[p.vision_api_key_ref] = "sk-vision-key"
    page._refresh_key_display(p)
    assert page.key.text() == KEY_MASK, "已存 Key 必须显示掩码而不是空框"
    assert page.vision_key.text() == KEY_MASK
    stored.clear()
    page._refresh_key_display(p)
    assert page.key.text() == "", "未存 Key 保持空白（占位文案负责引导）"


def test_mask_never_persisted_as_real_key(page_env):
    """只动别的字段就保存：掩码不得覆盖钥匙串真值，草稿也不得吸入掩码。"""
    from pet.chat.ai_settings_page import KEY_MASK
    page, cfg, stored = page_env
    p = page.settings.active_config
    stored[p.api_key_ref] = "sk-real-key"
    page._refresh_key_display(p)
    assert page.key.text() == KEY_MASK
    page.model.setText("glm-4.6")
    page.save()
    assert stored[p.api_key_ref] == "sk-real-key", "掩码被当成新 Key 存走 = 灾难"
    assert page.settings.active_config.model == "glm-4.6"


def test_typing_new_key_over_mask_replaces(page_env, monkeypatch):
    """掩码上直接粘贴新 Key → 覆盖保存（sk- 配智谱地址会触发嗅探，桩掉确认）。"""
    page, cfg, stored = page_env
    p = page.settings.active_config
    stored[p.api_key_ref] = "sk-old-key"
    page._refresh_key_display(p)
    page.key.setText("sk-brand-new")
    monkeypatch.setattr(page, "_confirm_key_mismatch", lambda text: True)
    page.save()
    assert stored[p.api_key_ref] == "sk-brand-new"


# ---------------------------------------------------------------- 跨厂商嗅探
def test_key_provider_mismatch_detection():
    from pet.chat.models import key_provider_mismatch
    zhipu_key = "a" * 32 + ".ABCDEFGHIJKLMNOP"  # 智谱 id.secret 形态
    assert key_provider_mismatch(zhipu_key, "https://api.siliconflow.cn/v1"), \
        "智谱格式 Key 配硅基流动 = 必须警告（2026-11-28 实机翻车场景）"
    assert not key_provider_mismatch(zhipu_key, "https://open.bigmodel.cn/api/paas/v4")
    assert not key_provider_mismatch("sk-abc123", "https://api.siliconflow.cn/v1"), \
        "sk- 各家通用，不得断言归属"
    assert key_provider_mismatch("sk-abc123", "https://open.bigmodel.cn/api/paas/v4"), \
        "智谱地址配 sk- Key 也要提示"
    assert not key_provider_mismatch("", "https://api.siliconflow.cn/v1")
    assert not key_provider_mismatch("sk-abc123", "")


def test_save_warns_on_mismatch_and_respects_choice(page_env, monkeypatch):
    """保存错位 Key 时弹确认：拒绝则零落盘，坚持则照存。"""
    from pet.chat.ai_settings_page import KEY_MASK
    page, cfg, stored = page_env
    p = page.settings.active_config
    page.url.setText("https://api.siliconflow.cn/v1")
    zhipu_key = "b" * 32 + ".ABCDEFGHIJKLMNOP"
    page.key.setText(zhipu_key)
    asked = []
    monkeypatch.setattr(page, "_confirm_key_mismatch",
                        lambda text: asked.append(text) or False)
    page.save()
    assert len(asked) == 1 and "智谱" in asked[0]
    assert zhipu_key not in stored.values(), "用户选「返回修改」后不得写钥匙串"
    monkeypatch.setattr(page, "_confirm_key_mismatch", lambda text: True)
    page.save()
    assert stored[p.api_key_ref] == zhipu_key, "用户坚持后照存"


# ---------------------------------------------------------------- 401 人话翻译
def test_auth_error_translated_not_raw_json(monkeypatch):
    """聊天发送路径遇 401 必须给出人话（钥匙和锁不是一家），不甩原始 JSON。"""
    import io
    import urllib.error
    from pet.chat.models import ProviderConfig
    from pet.chat.providers import OpenAICompatibleProvider, ProviderError

    def _fake_urlopen(req, timeout, context):
        raise urllib.error.HTTPError(
            "https://api.siliconflow.cn/v1/chat/completions", 401,
            "Unauthorized", {},
            io.BytesIO(b'{"code":30014,"message":"Token is invalid."}'))

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    cfg = ProviderConfig("t", base_url="https://api.siliconflow.cn/v1",
                         chat_path="/chat/completions", model="m", api_key="sk-x")
    provider = OpenAICompatibleProvider()
    with pytest.raises(ProviderError) as excinfo:
        provider._open({"messages": []}, cfg, "application/json")
    message = str(excinfo.value)
    assert "HTTP 401" in message
    assert "不是一家" in message, "必须点破 Key/服务商错位这个头号原因"
    assert "核对" in message, "必须给出去哪里核对的指引"
    assert "30014" not in message, "原始 JSON 错误码不应再甩给用户"
