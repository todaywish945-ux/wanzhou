# -*- coding: utf-8 -*-
"""测试设置界面控件状态、保存/读取 round-trip 以及内置 Agent 音效资源存在与格式有效性。"""
from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from pet.click_sound import resolve_builtin_sound
from pet.config import Config
from pet.modern_settings_dialog import ModernSettingsDialog, SettingRow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_modern_settings_dialog_round_trip(qapp, tmp_path: Path):
    """验证现代设置面板：初始化正确读取 Config，修改后 _write_config 写入 Config 并能准确读回。"""
    cfg_root = tmp_path / "appdata"
    # 生产形态：当前宠的设置页拿 slot0 的路由视图（每宠键 → config-slot-0.json）
    from pet.settings_slot_config import route_settings_config

    cfg = route_settings_config(Config(cfg_root, instance_id="slot-0"))

    # 1. 初始状态断言
    dialog = ModernSettingsDialog(cfg, include_ai=False)
    try:
        assert dialog.slingshot_check.isChecked() is True
        assert dialog.throw_strength_select.currentData() == "standard"
        assert dialog.click_sound_check.isChecked() is True
        assert dialog.click_sound_volume_spin.value() == 70
        assert not hasattr(dialog, "agent_sound_check"), "Agent 联动功能已删除"
        assert not hasattr(dialog, "spawn_inherit_size_check"), "生小桌宠功能已删除"
        assert not hasattr(dialog, "spawn_scale_combo")
        assert not hasattr(dialog, "clear_spawned_pets_btn")

        # 2. 模拟用户修改各个设置项
        dialog.slingshot_check.setChecked(False)
        dialog.throw_strength_select.setCurrentData("crazy")
        dialog.click_sound_volume_spin.setValue(85)
        dialog.click_sound_picker.set_pack({"kind": "builtin", "id": "duck", "path": ""})

        # 3. 触发写入
        ok = dialog._write_config()
        assert ok is True
    finally:
        dialog.deleteLater()

    # 4. 新建 Config 实例重载验证持久化 round-trip
    reloaded_cfg = route_settings_config(Config(cfg_root, instance_id="slot-0"))
    assert reloaded_cfg.get("slingshot_enabled") is False
    assert reloaded_cfg.get("throw_strength") == "crazy"
    assert reloaded_cfg.get("click_sound_volume") == 0.85
    assert reloaded_cfg.get("click_sound_pack") == {"kind": "builtin", "id": "duck", "path": ""}


def test_import_dialogue_template_reads_entries_and_top_level_phrases(tmp_path, monkeypatch):
    """导入模板必须同时读取顶层 phrases 与 entries[].phrases（既有 bug 回归）。"""
    import json

    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    cfg = Config(tmp_path / "appdata")
    dialog = ModernSettingsDialog(cfg, include_ai=False)
    try:
        # 1) 只改了 entries[].phrases（顶层缺失/为空）的模板也要生效
        entries_only = {
            "template": "persona-phrases/v1",
            "mode": "custom",
            "phrases": {},
            "entries": [
                {"key": "thinking", "description": "思考中", "sources": [], "parameters": [],
                 "displayHint": "", "phrases": ["entries 里的台词 {name}"]},
                {"key": "done.success", "description": "done", "sources": [], "parameters": [],
                 "displayHint": "", "phrases": []},
            ],
        }
        dialog.dialogue_template_import_edit.setPlainText(json.dumps(entries_only, ensure_ascii=False))
        dialog._import_dialogue_template_json()
        assert dialog.dialogue_phrase_edits["thinking"].toPlainText() == "entries 里的台词 {name}"
        assert dialog.dialogue_mode_select.currentData() == "custom"

        # 2) 顶层 phrases 有内容时以顶层为准，不被 entries 覆盖
        both = {
            "template": "persona-phrases/v1",
            "mode": "custom",
            "phrases": {"thinking": ["顶层台词 {name}"]},
            "entries": [
                {"key": "thinking", "description": "思考中", "sources": [], "parameters": [],
                 "displayHint": "", "phrases": ["entries 不应覆盖"]},
            ],
        }
        dialog.dialogue_template_import_edit.setPlainText(json.dumps(both, ensure_ascii=False))
        dialog._import_dialogue_template_json()
        assert dialog.dialogue_phrase_edits["thinking"].toPlainText() == "顶层台词 {name}"


    finally:
        dialog.deleteLater()



def test_dialogue_key_params_match_runtime_call_sites():
    """设置页每 key 的“可用参数”提示直接派生自 PARAMETERS（单一真相源）。

    上游重构曾让设置页提示与运行时注入漂移；现在 DIALOGUE_KEY_PARAMS 由
    persona_template.PARAMETERS 派生，这里验证派生关系与代表性条目。"""
    from pet.modern_settings_dialog import DIALOGUE_KEY_PARAMS, DIALOGUE_PARAMS
    from pet.persona_template import PARAMETERS

    assert DIALOGUE_KEY_PARAMS == dict(PARAMETERS)
    # 展示名必须覆盖全部宣称的参数（对话框 hint 渲染用 DIALOGUE_PARAMS[item]）
    advertised = {f for fields in PARAMETERS.values() for f in fields}
    assert advertised <= set(DIALOGUE_PARAMS), sorted(advertised - set(DIALOGUE_PARAMS))
    # activity 组字段以桥接 tool/call 真实记录为准：target/ok 不在 tool/call 里，
    # 不得宣称（活动气泡渲染时拿不到，写了就是永不替换的占位符）
    assert "callId" in DIALOGUE_KEY_PARAMS["activity.read"]
    assert "target" not in DIALOGUE_KEY_PARAMS["activity.read"]
    assert "ok" not in DIALOGUE_KEY_PARAMS["activity.read"]
    assert {"errorCode", "errorMessage", "consecutiveRetryCount", "retry"} <= set(
        DIALOGUE_KEY_PARAMS["model_access.one"])
    assert "dsh.writeback.failed" not in DIALOGUE_KEY_PARAMS, "回写链已删，其文案键不得残留"


def test_dialogue_template_export_is_blank_without_current_phrases(qapp, tmp_path):
    """导出 = 纯字段参考模板：不携带当前已配置的台词（phrases 一律留空）。"""
    cfg = Config(tmp_path / "appdata")
    dialog = ModernSettingsDialog(cfg, include_ai=False)
    try:
        dialog.dialogue_phrase_edits["thinking"].setPlainText("当前已配置的台词不应出现在导出里")
        data = dialog._current_dialogue_template()
        assert all(not v for v in data["phrases"].values())
        assert all(not e["phrases"] for e in data["entries"])
        assert data["mode"] == dialog.dialogue_mode_select.currentData()
    finally:
        dialog.deleteLater()


def _nav_item_indexes(dialog) -> dict[str, int]:
    """返回 sidebar 标签 → pages 栈索引 的映射。"""
    return {
        dialog.sidebar.item(i).text(): i
        for i in range(dialog.sidebar.count())
    }


def test_dialogue_rows_live_in_ai_domain(qapp, tmp_path):
    """文案风格/台词行随 AI 域走：include_ai=True 挂在 AI 域；
    纯桌宠变体（include_ai=False）无对话功能，这些行不出现在任何域页。"""
    from pet.settings_widgets import SettingRow

    for include_ai in (True, False):
        cfg = Config(tmp_path / f"appdata-{include_ai}")
        dialog = ModernSettingsDialog(cfg, include_ai=include_ai)
        try:
            nav = _nav_item_indexes(dialog)
            page_rows = []
            for i in range(dialog.sidebar.count()):
                page_rows += [r.objectName() for r in dialog.pages.widget(i).findChildren(SettingRow)
                              if r.objectName().startswith("settingRow_dialogue_")]
            if include_ai:
                assert "AI 与对话" in nav
                assert "settingRow_dialogue_mode" in page_rows
                assert "settingRow_dialogue_thinking" in page_rows
            else:
                assert "AI 与对话" not in nav
                assert page_rows == [], page_rows
        finally:
            dialog.deleteLater()


def test_automation_domain_removed_after_feature_cleanup(qapp, tmp_path):
    """「自动化与联动」「文件识别」域已删除：免打扰归互动、文案/文件解读归 AI。"""
    from pet.settings_widgets import SETTINGS_DOMAIN_NAV, SettingRow

    labels = [label for label, _ in SETTINGS_DOMAIN_NAV]
    assert "自动化与联动" not in labels
    assert "文件识别" not in labels
    assert "Agent 联动" not in labels

    cfg = Config(tmp_path / "appdata")
    dialog = ModernSettingsDialog(cfg, include_ai=True)
    try:
        nav = _nav_item_indexes(dialog)
        interaction = dialog.pages.widget(nav["互动"])
        assert interaction.findChild(SettingRow, "settingRow_quiet_minutes_default") is not None
        ai = dialog.pages.widget(nav["AI 与对话"])
        assert ai.findChild(SettingRow, "settingRow_file_interpret_enabled") is not None
        assert ai.findChild(SettingRow, "settingRow_dialogue_mode") is not None
    finally:
        dialog.deleteLater()


def test_dialogue_global_edits_read_and_preserve_unified_preset(qapp, tmp_path):
    """global 逐事件编辑读取/写回统一预设：编辑 global.thinking 只改 global，agents delta 保留。

    Agent 联动删除后只有 thinking 一行可见；老数据里的 agents 层
    原样保留，不被写回破坏。
    """
    cfg = Config(tmp_path / "appdata")
    cfg.set("dialogue_mode", "custom")
    cfg.set("dialogue_phrases", {
        "global": {"start": ["全局默认 start"], "thinking": ["全局默认 thinking"]},
        "agents": {"dsh": {"thinking": ["DSH thinking"]}},
    })
    cfg.save()

    dialog = ModernSettingsDialog(cfg, include_ai=False)
    try:
        # 编辑区初始展示 global 层内容
        assert dialog.dialogue_phrase_edits["thinking"].toPlainText() == "全局默认 thinking"

        # 修改 global.thinking；保存后 agents delta 不受影响
        dialog.dialogue_phrase_edits["thinking"].setPlainText("新的全局 thinking")
        ok = dialog._write_config()
        assert ok is True
    finally:
        dialog.deleteLater()

    reloaded = Config(tmp_path / "appdata")
    phrases = reloaded.get("dialogue_phrases")
    # start 事件已不在可编辑行里，写回不再触碰它（老值保留与否都允许）
    assert phrases["global"].get("start", ["全局默认 start"]) == ["全局默认 start"]
    assert phrases["global"]["thinking"] == ["新的全局 thinking"]
    assert phrases["agents"]["dsh"]["thinking"] == ["DSH thinking"]


def test_agent_specific_phrase_layers_removed(qapp, tmp_path):
    """Agent 联动删除后，专属文案层没有消费者：下拉只剩全局，设置行也不再露出。"""
    cfg = Config(tmp_path / "appdata")
    cfg.set("dialogue_mode", "custom")
    cfg.save()

    dialog = ModernSettingsDialog(cfg, include_ai=False)
    try:
        assert [dialog.dialogue_scope_select.itemText(i)
                for i in range(dialog.dialogue_scope_select.count())] == ["默认（全局文案）"]
        assert dialog.dialogue_scope_select.currentData() == ""
        assert dialog.findChild(SettingRow, "settingRow_dialogue_scope") is None
        assert set(dialog.dialogue_phrase_edits) == {"thinking"}
    finally:
        dialog.deleteLater()


def test_import_dialogue_template_ignores_agent_layers(qapp, tmp_path, monkeypatch):
    """模板里老版本的 agents 层仍可读入数据，但不再产生可切换的专属编辑层。"""
    import json

    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)

    cfg = Config(tmp_path / "appdata")
    cfg.set("dialogue_mode", "custom")
    dialog = ModernSettingsDialog(cfg, include_ai=False)
    try:
        template = {
            "template": "persona-phrases/v1",
            "mode": "custom",
            "phrases": {"thinking": ["全局 thinking"]},
            "agents": {"dsh": {"thinking": ["导入的 DSH thinking"]}},
        }
        dialog.dialogue_template_import_edit.setPlainText(json.dumps(template, ensure_ascii=False))
        dialog._import_dialogue_template_json()

        assert dialog.dialogue_phrase_edits["thinking"].toPlainText() == "全局 thinking"
        assert [dialog.dialogue_scope_select.itemText(i)
                for i in range(dialog.dialogue_scope_select.count())] == ["默认（全局文案）"]
    finally:
        dialog.deleteLater()


def test_old_agent_scope_falls_back_to_global(qapp, tmp_path):
    """老配置里残留的 dialogue_last_scope=agent 不再可选，统一回落全局层。"""
    cfg = Config(tmp_path / "appdata08")
    cfg.set("dialogue_mode", "custom")
    cfg.set("dialogue_phrases", {
        "global": {"thinking": ["全局 thinking"]},
        "agents": {"dsh": {"thinking": ["DSH thinking"]}},
    })
    cfg.set("dialogue_last_scope", "dsh")
    assert cfg.save() is True

    dialog = ModernSettingsDialog(cfg, include_ai=False)
    try:
        assert dialog.dialogue_scope_select.currentData() == ""
        assert dialog.dialogue_phrase_edits["thinking"].toPlainText() == "全局 thinking"
        assert dialog._write_config() is True
    finally:
        dialog.deleteLater()

    reloaded = Config(tmp_path / "appdata08")
    assert reloaded.get("dialogue_phrases")["agents"]["dsh"]["thinking"] == ["DSH thinking"]


def test_export_dialogue_template_mentions_agents_separator(qapp, tmp_path):
    """导出模板结构：顶层 phrases 为 global 参考，新增 agents 占位说明不影响导出。"""
    import json as json_mod

    cfg = Config(tmp_path / "appdata")
    dialog = ModernSettingsDialog(cfg, include_ai=False)
    try:
        data = dialog._current_dialogue_template()
        # 导出仍是纯字段参考模板：phrases 留空；Agent 专属层已删除，无 agents 脚手架
        assert all(not v for v in data["phrases"].values())
        text = json_mod.dumps(data, ensure_ascii=False)
        assert "persona-phrases/v1" in text
        assert not data.get("agents"), "Agent 联动已删除，不应再导出 agents 专属层"
        # entries.description 给出一句话语义，不再是 key 占位（AI 可读）
        assert any(
            entry["description"] and entry["description"] != entry["key"]
            for entry in data["entries"]
        )
    finally:
        dialog.deleteLater()


def test_subfish_settings_save_sets_user_customized(qapp, tmp_path: Path):
    """批 C：子桌宠自己的设置界面保存会置位 user_customized=True。"""
    cfg_root = tmp_path / "appdata"
    cfg = Config(cfg_root, instance_id="slot-1")
    dialog = ModernSettingsDialog(cfg, include_ai=False)
    try:
        ok = dialog._write_config()
        assert ok is True
    finally:
        dialog.deleteLater()
    assert cfg.get("user_customized") is True
    reloaded = Config(cfg_root, instance_id="slot-1")
    assert reloaded.get("user_customized") is True


def test_main_settings_save_does_not_set_user_customized(qapp, tmp_path: Path):
    """批 C：主配置（slot 0/主身份）保存不置位 user_customized（保持默认假）。"""
    cfg_root = tmp_path / "appdata"
    cfg = Config(cfg_root)
    dialog = ModernSettingsDialog(cfg, include_ai=False)
    try:
        ok = dialog._write_config()
        assert ok is True
    finally:
        dialog.deleteLater()
    assert cfg.get("user_customized") is False
    reloaded = Config(cfg_root)
    assert reloaded.get("user_customized") is False


def test_position_autosave_does_not_set_user_customized(tmp_path):
    """批 C：位置自动保存等后台写盘不得置位 user_customized（保留默认假）。"""
    cfg_root = tmp_path / "appdata"
    cfg = Config(cfg_root, instance_id="slot-2")
    # 模拟窗口 _save_position：写位置键 + save()，不经过设置界面。
    cfg.set("rx", 0.5)
    cfg.set("ry", 0.5)
    cfg.set("screen_name", "X")
    cfg.set("facing", "right")
    cfg.save()
    assert cfg.get("user_customized") is False
    reloaded = Config(cfg_root, instance_id="slot-2")
    assert reloaded.get("user_customized") is False








