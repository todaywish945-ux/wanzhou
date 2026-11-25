# -*- coding: utf-8 -*-
"""功能模块激活层（期 1）：启用集合的迁移判定 + 进程级快照。

设计见 ``.scratch/feature-modules/SPEC.md``。本模块只管三件事：

1. **一次性迁移判定**：``feature_activation`` 为 ``None``（未判定）时，区分
   新装/升级写回初始启用集合——升级继承 ``MIGRATION_BASELINE``（全模块），
   新装默认纯核心（``PURE_CORE_FOR_NEW_INSTALL = True``，全部模块已过
   「不出现、不启动、不写回」验收后于 2026-10-21 生效）。
2. **本次运行快照**：主进程在创建任何可选服务之前 ``decide_and_freeze`` 一次，
   之后 ``is_active`` 只读快照——功能页写盘（下次启动生效）绝不影响本次运行。
3. **写下次启动值**：``write_enabled`` 给功能管理页用，校验后整值提交。

快照未冻结时（测试、工具脚本、独立设置进程）``is_active`` 一律 True——
门控是调用点可选接入的，旧行为默认不变。

本模块禁止 import Qt（启动早期使用，import 必须便宜）。
"""
from __future__ import annotations

import logging
import os

from .features import (
    FEATURES,
    MIGRATION_BASELINE,
    RETIRED_FEATURES,
    normalize_enabled,
)

log = logging.getLogger(__name__)

#: 启用集合结构的当前版本（不认识的高版本按损坏处理：保留原数据 + 诊断）。
CURRENT_VERSION = 1

#: 新装与升级一律默认开启全部可移植模块（2026-11-24 改）：设置侧栏的「功能」
#: 总开关页已隐藏，改由各功能自己的具体设置行控制；若新装仍拿到空集，用户
#: 既看不到模块又没有入口开启。门控机制保留在后台，盘上已有的 feature_activation
#: 值仍被尊重（工具/老配置手改的关闭状态依旧生效），只是不再有 UI 入口改它。
PURE_CORE_FOR_NEW_INSTALL = False

#: 主进程拉起独立设置进程时透传本次冻结快照的环境变量（空串 = 纯核心，
#: 与「未设置」可区分）。盘上未判定时设置进程以它为准——新装用户在主进程
#: 首次自然保存前打开设置，不会拿到全激活基线（盲审存疑 B）。
ENV_FEATURE_SNAPSHOT = "DSH_PET_FEATURE_SNAPSHOT"

#: 本次运行冻结的启用集合；None = 未冻结（is_active 一律 True）。
_snapshot: frozenset[str] | None = None


def _is_upgrade_install(config) -> bool:
    """升级安装判定：有任一既有数据痕迹即按升级处理（继承全部模块）。

    「config.json 缺失但 slot 档案/会话目录在」不能判新装（SPEC §4）。
    """
    if config.path.is_file():
        return True
    try:
        if any(config.dir.glob("config-slot-*.json")):
            return True
        if (config.dir / "sessions").is_dir():
            return True
    except OSError:
        # 目录不可读时按升级处理（保守：宁可多激活，不可藏掉用户在用的功能）
        return True
    # 已知限制（盲审存疑 A，2026-10-21 决议）：从未留下任何痕迹的老用户
    # （没保存过配置、没聊过天）会被判成新装拿到纯核心。不能用日志当痕迹——
    # 新装第二次启动也会有自己的历史日志，会误判成升级（实测推演）；此类
    # 用户可在「功能」页一键全部开启，发版说明需写明。
    return False


#: 晚昼桌宠移植保留集：overlay/灵动岛/音乐/待办/节日/主动识屏/Agent 联动未随
#: 移植携带，无论配置怎么写都不激活（防止设置页误开导致懒构建崩溃）。
_PORT_FEATURES = frozenset({
    "weather", "divination", "zzz_launcher", "voice", "chat", "vision", "file_interpret",
    "quick_launch", "system_tools", "dynamic_island",
})


def _freeze_enabled(enabled) -> frozenset[str]:
    """冻结前与移植保留集取交集（移植裁剪的 feature 永不激活）。"""
    return _PORT_FEATURES.intersection(enabled)


def without_retired(enabled) -> list[str]:
    """剔除已退役的模块 id（老配置里可能还留着 5 个永不生效的入口）。"""
    return [fid for fid in enabled if fid not in RETIRED_FEATURES]


def _master_activation_value(config):
    """返回 feature_activation 的**全局真值**（主 config.json）及其存在性。

    ``feature_activation`` 是全局键：设置页（独立进程）经 ``SlotRoutedConfig``
    的非分流路由写主 config.json，而三角色桌宠各读 ``config-角色X.json``。
    若启动冻结只读实例配置，就会出现「设置页关掉灵动岛 → 重启后岛照样在」
    （实例那份还留着旧值，永远等不到同步）。此处与
    :func:`freeze_for_settings_process` 同口径：有主配置且其中明确写了该功能键，
    一律以主配置为准；主配置缺失/损坏/未写该键时回退调用方传入的配置，保持
    单实例场景与既有测试行为逐位不变。仅读盘，不写盘。
    """
    try:
        main_path = config.dir / "config.json"
        if main_path.is_file():
            import json
            data = json.loads(main_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "feature_activation" in data:
                return data["feature_activation"], True
    except (OSError, ValueError, AttributeError):
        pass
    return config.data.get("feature_activation"), False


def decide_and_freeze(config) -> frozenset[str]:
    """启动早期调用一次：完成迁移判定（若需要）并冻结本次运行快照。

    - 已判定（盘上有合法值）：直接冻结，未知 ID 进不了快照但保留在盘上；
    - 未判定（None）：按新装/升级置出初始集合——**只进内存草稿，不主动落盘**：
      判定是确定性的（同一份磁盘痕迹必然判出同一结果），进程死掉重判无妨；
      草稿随下一次自然配置保存落盘。启动链上主动 save 会过早触发 slot-0
      档案引导（`Config.save` 的 pet_profiles  bootstrap），破坏「AppShell
      构造前零配置副作用」的启动不变量（tests/test_overlay_instance_gate.py）；
    - 损坏（非 dict / 版本不认识 / enabled 不是 list）：保留原数据、打诊断，
      保守冻结全模块——绝不拿默认值覆盖用户数据；
    - 合法空列表是明确选择，原样冻结（绝不回退成全激活）。

    feature_activation 是全局键：实例进程启动冻结读主 config.json 的真值
    （见 :func:`_master_activation_value`），避免设置页关掉的模块在重启后复活。
    """
    global _snapshot
    raw, from_master = _master_activation_value(config)
    if from_master:
        log.debug("功能模块激活：实例进程按主配置冻结启用集（全局键）")
    if raw is None:
        upgrade = _is_upgrade_install(config)
        enabled = [] if (not upgrade and PURE_CORE_FOR_NEW_INSTALL) else list(MIGRATION_BASELINE)
        config.set("feature_activation", {"version": CURRENT_VERSION, "enabled": enabled})
        log.info("功能模块激活：%s安装，初始启用集合 %d 项（随下次配置保存落盘）",
                 "升级" if upgrade else "新装", len(enabled))
        _snapshot = _freeze_enabled(enabled)
        return _snapshot
    if not isinstance(raw, dict) or raw.get("version") != CURRENT_VERSION \
            or not isinstance(raw.get("enabled"), list):
        log.warning("功能模块激活：配置值损坏或版本不认识（保留原数据，本次按全模块运行）: %r",
                    type(raw).__name__)
        _snapshot = _freeze_enabled(MIGRATION_BASELINE)
        return _snapshot
    try:
        enabled, unknown = normalize_enabled(raw["enabled"])
    except ValueError:
        # 元素级损坏（如 ["weather", 3]）：同整体损坏口径——保留原数据 + 诊断，
        # 保守冻结全模块，不拿默认值覆盖
        log.warning("功能模块激活：启用列表元素损坏（保留原数据，本次按全模块运行）")
        _snapshot = _freeze_enabled(MIGRATION_BASELINE)
        return _snapshot
    # 老配置里残留的退役模块（todo/festival/music/proactive/agent_link）在下次
    # 自然保存时一并清掉；本次运行它们本就被 _PORT_FEATURES 挡在外面。
    kept = without_retired(enabled)
    if len(kept) != len(enabled):
        log.info("功能模块激活：清理 %d 个已退役模块 id", len(enabled) - len(kept))
        config.set("feature_activation", {"version": CURRENT_VERSION,
                                          "enabled": [*kept, *unknown]})
        enabled = kept
    if unknown:
        log.info("功能模块激活：%d 个未知模块 ID 保留在盘上但不激活: %s", len(unknown), unknown)
    _snapshot = _freeze_enabled(enabled)
    return _snapshot


def is_active(feature_id: str) -> bool:
    """本次运行该模块是否可用（激活快照 ∧ 硬依赖满足）。

    快照未冻结（测试/工具/独立设置进程）恒 True。只勾了模块但没勾它的
    硬依赖（如只开 file_interpret 不开 chat）时按不可用计——门控三层
    （菜单/设置/执行）共用这个判据，不会出现「入口在、点了没反应」。
    不在清单里的 id（核心能力、空串）不受门控，恒 True。
    """
    if feature_id not in FEATURES:
        return True
    if _snapshot is None:
        return True
    from .features import resolve_dependencies

    return feature_id in resolve_dependencies(_snapshot).active


def snapshot() -> frozenset[str] | None:
    """当前冻结的快照（诊断/测试用）；None = 未冻结。"""
    return _snapshot


def snapshot_env_value() -> str | None:
    """主进程拉起设置进程时透传的快照串（``ENV_FEATURE_SNAPSHOT`` 的值）；
    未冻结返回 None（不注入，设置进程走自己的判定链）。"""
    if _snapshot is None:
        return None
    return ",".join(sorted(_snapshot))


def pending_enabled(config) -> list[str]:
    """功能页展示的「下次启动」启用集：盘上已判定的值；未判定时预览跟随
    **有效判定**——本进程已冻结的快照（主进程=启动判定结果；设置进程=
    透传快照/自己的判定），未冻结才给迁移基线预览。
    否则新装用户的功能页会显示全模块勾选，任何一次保存都把全激活写进盘，
    纯核心名存实亡（2026-10-21 复审补漏：is_active 投影与 pending 预览必须同源）。"""
    raw = config.data.get("feature_activation")
    if isinstance(raw, dict) and isinstance(raw.get("enabled"), list):
        try:
            enabled, _ = normalize_enabled(raw["enabled"])
        except ValueError:
            return list(MIGRATION_BASELINE)
        return without_retired(enabled)
    snap = snapshot()
    if snap is not None:
        return without_retired(sorted(snap))
    return list(MIGRATION_BASELINE)


def write_enabled(config, enabled: list[str]) -> bool:
    """功能页保存入口：校验后整值提交「下次启动」启用集；返回是否落盘成功。

    未知/非法 ID 直接拒绝（调用方是 UI，给的是清单内的 id）；合法空列表允许。
    只写盘，不动本次运行快照——重启才生效。
    """
    unknown = [fid for fid in enabled if fid not in FEATURES]
    if unknown:
        log.warning("功能模块激活：拒绝写入未知模块 ID: %s", unknown)
        return False
    deduped = list(dict.fromkeys(enabled))
    config.set("feature_activation", {"version": CURRENT_VERSION, "enabled": deduped})
    return bool(config.save())


def reset_snapshot_for_tests() -> None:
    """测试专用：解除冻结，恢复 is_active 恒 True 的默认态。"""
    global _snapshot
    _snapshot = None


def freeze_for_settings_process(config) -> None:
    """独立设置进程：按全局 config.json 的「下次启动」集合冻结快照。

    设置 UI 必须反映**待生效**状态（主进程的运行快照是它启动时冻结的，
    两边本来就不必相同）。本进程不运行功能服务，is_active 只影响设置层
    投影（哪些标签/组/页出现）与预览入口。
    传入的可能是 slot 实例配置（feature_activation 是全局键，真值只在
    主 config.json），所以一律直读主文件；**不写盘**——落盘是主进程启动时
    的职责。盘上未判定时在内存里做同一套新装/升级判定（与主进程同一份
    磁盘痕迹必然同结论）：否则新装用户在主进程首次自然保存前打开设置，
    会拿到全激活基线，一次保存就把「全部启用」写进盘（盲审存疑 B）。
    读不到/值损坏就冻结迁移基线（全激活=旧行为，保守方向）。
    """
    import json

    global _snapshot
    raw = None
    try:
        main_path = config.dir / "config.json"
        if main_path.is_file():
            data = json.loads(main_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                raw = data.get("feature_activation")
    except (OSError, ValueError):
        raw = None
    if raw is None:
        env = os.environ.get(ENV_FEATURE_SNAPSHOT)
        if env is not None:
            # 主进程透传的本次冻结快照（空串 = 纯核心）：与主进程判定同源，
            # 新装不会在「首次自然保存前开设置」拿到全激活基线（盲审存疑 B）
            try:
                enabled, _ = normalize_enabled([s for s in env.split(",") if s.strip()])
            except ValueError:
                enabled = list(MIGRATION_BASELINE)
        else:
            # 无主进程透传（直接跑 --settings）：与主进程同一套新装/升级判定
            upgrade = _is_upgrade_install(config)
            enabled = [] if (not upgrade and PURE_CORE_FOR_NEW_INSTALL) else list(MIGRATION_BASELINE)
    elif isinstance(raw, dict) and isinstance(raw.get("enabled"), list):
        try:
            enabled, _ = normalize_enabled(raw["enabled"])
        except ValueError:
            enabled = list(MIGRATION_BASELINE)
    else:
        enabled = list(MIGRATION_BASELINE)
    _snapshot = _freeze_enabled(enabled)


def freeze_snapshot_for_tests(enabled) -> None:
    """测试专用：直接冻结成指定启用集（门控用例的开关）。"""
    global _snapshot
    _snapshot = frozenset(enabled)
