# -*- coding: utf-8 -*-
"""灵动岛「桌宠恢复条」的**纯布局层**（零 Qt）。

岛在桌宠隐藏时才出现，内容区换成一条三段的恢复条：每段对应一只桌宠，
隐藏的那一段**亮起**（有名字、有「点击显示」提示、占更宽），可见的那一段
收成窄条（只留一个头像圆点）。所以隐藏的宠越多，展开的段越多，岛越长。

纯函数口径（与 ``island/layout.py`` 同一纪律）：度量对象由调用方注入，本模块
只算「一段多宽、摆在哪、可见段集是什么」。任何状态（哪只隐藏）都通过入参
传进来，不读配置、不碰窗口——测试可在没有 QApplication 的情况下验宽度与命中。

对外两个函数：

- :func:`plan_pet_bar`：给段列表 + 预算，返回自然宽与命中盒；
- :func:`apply_pet_shrink`：窄屏时只压缩隐藏段的提示文字，可见段永不消失
  （三段是产品契约：少一段就等于少一只宠的恢复入口，绝不允许折叠）。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 三段之间的槽位（含 1px 竖线）：与 ``layout._SEG_SLOT_PX`` 同口径。
SEG_SLOT_PX = 19.0
#: 内容区左右内边距（与 ``layout._CONTENT_PAD_PX`` 一致）。
CONTENT_PAD_PX = 19.0
#: 头像圆点直径 / 与名字的间距。
AVATAR_PX = 22.0
AVATAR_GAP_PX = 6.0
#: 隐藏段的提示文案（「点击显示」）；可见段只画头像与名字，不画这段。
HIDDEN_HINT = "已隐藏 · 点击显示"
#: 名字与提示之间的固定间距。
NAME_HINT_GAP_PX = 8.0
#: 「全部显示」chip 的最小宽与左右内边距。
ALL_CHIP_MIN_W = 62
ALL_CHIP_PAD_PX = 6.0
#: 窄屏预算不足时提示省略到的上限（比完整提示短，但仍表达可点）。
HINT_ELIDE_PX = 44


@dataclass(frozen=True)
class PetBarSegment:
    """一只桌宠在恢复条上的一段。

    ``pet_id`` 是稳定 id（``角色A/B/C``），同时是命中与恢复请求的键；
    ``hidden`` 决定这一段是展开（亮）还是收起（暗）；``label`` 是角色名；
    ``width`` 由调用方按注入的度量算好后填进来（本模块不 import Qt）。
    """

    pet_id: str
    label: str
    hidden: bool
    width: int = 0  # 占位：真实宽度由 plan_pet_bar 按注入的度量算出，调用方不填


@dataclass(frozen=True)
class PetBarPlacement:
    """一段的落位（x 为相对内容区左缘的坐标）。"""

    seg: PetBarSegment
    x: float
    width: int
    hint: str
    divider_x: float | None = None


@dataclass(frozen=True)
class PetBarPlan:
    """一条恢复条的计算结果。"""

    placements: tuple[PetBarPlacement, ...]
    width: int
    elided_hint: bool
    all_chip_x: float | None = None
    all_chip_w: int = 0

    def hit_test(self, x: float) -> tuple[str, str] | None:
        """命中测试：返回 ``("pet", pet_id)`` / ``("all", "")`` / ``None``。

        ``x`` 是相对窗口左缘的横坐标（调用方从 ``event.position().x()`` 取）。
        点击竖线槽位归给右侧那一段（更宽容，且不会点不到邻段）。
        """
        for place in self.placements:
            if place.x - SEG_SLOT_PX / 2 <= x < place.x + place.width:
                return "pet", place.seg.pet_id
        if self.all_chip_x is not None and (
                self.all_chip_x <= x < self.all_chip_x + self.all_chip_w):
            return "all", ""
        return None


def _hint_for(seg: PetBarSegment, *, hint_fm, elide: bool) -> str:
    """隐藏段的提示文案（窄屏时右省略到 :data:`HINT_ELIDE_PX`）。"""
    if not seg.hidden:
        return ""
    if not elide:
        return HIDDEN_HINT
    from .layout import elide_to_width  # 延迟导入：纯逻辑、无 Qt
    return elide_to_width(HIDDEN_HINT, HINT_ELIDE_PX, hint_fm)


def _seg_width(seg: PetBarSegment, hint: str, *, name_fm, hint_fm,
               metrics_fm) -> int:
    """一段的自然宽：头像 + 名字 +（隐藏时）提示 + 槽位。"""
    name_w = int(metrics_fm.horizontalAdvance(seg.label)) if seg.label else 0
    hint_w = int(hint_fm.horizontalAdvance(hint)) if hint else 0
    body = AVATAR_PX + AVATAR_GAP_PX + name_w
    if hint:
        body += NAME_HINT_GAP_PX + hint_w
    # 名字用 name 层度量，头像与提示用 label 层：两者取最大，避免字高不一致时
    # 段宽算小（布局层只负责宽度包络，具体字体在绘制层用对应层）。
    return int(max(body, AVATAR_PX + AVATAR_GAP_PX +
                   int(name_fm.horizontalAdvance(seg.label)) if seg.label else body)
               + SEG_SLOT_PX)


def plan_pet_bar(segments: list[PetBarSegment], *, lead_w: float,
                 trail_w: float, available_w: float, name_fm, hint_fm,
                 metrics_fm, show_hint: bool = True) -> PetBarPlan:
    """算一条恢复条的宽度与落位（纯函数，同输入恒同输出）。

    ``available_w`` ≤ 0 表示拿不到屏信息 → 不收缩。窄屏时只省略隐藏段的提示
    文字；三段一个都不折（恢复入口是核心操作，不可被收缩吃掉）。

    ``show_hint=False``：隐藏段不留「已隐藏 · 点击显示」的文字宽度（调用方
    也不画它时必传，否则隐藏段留下大块空白——用户截图「隐藏了留这么大空白」）。
    """
    if not segments:
        return PetBarPlan((), max(1, int(round(lead_w + trail_w))), False)
    # 首轮按**完整提示**算（正常屏宽下用户看到的就是完整「已隐藏 · 点击显示」）。
    hints = [_hint_for(seg, hint_fm=hint_fm, elide=False) if show_hint else ""
             for seg in segments]
    widths = [_seg_width(seg, hint, name_fm=name_fm, hint_fm=hint_fm,
                         metrics_fm=metrics_fm)
              for seg, hint in zip(segments, hints)]
    total = lead_w + sum(widths) + trail_w
    # 只有超预算才退化到省略提示（一次决策，不做逐段循环）。拿不到屏信息
    # （available_w<=0）时不收缩——与 island/layout.plan_info_row 同口径。
    elided = False
    if available_w > 0 and total > available_w and any(hints):
        elided = True
        hints = [_hint_for(seg, hint_fm=hint_fm, elide=True) if show_hint else ""
                 for seg in segments]
        widths = [_seg_width(seg, hint, name_fm=name_fm, hint_fm=hint_fm,
                             metrics_fm=metrics_fm)
                  for seg, hint in zip(segments, hints)]
        total = lead_w + sum(widths) + trail_w
    placements: list[PetBarPlacement] = []
    x = float(lead_w)
    for index, (seg, width, hint) in enumerate(zip(segments, widths, hints)):
        divider = x + (SEG_SLOT_PX - 1) / 2 if index > 0 else None
        placements.append(PetBarPlacement(
            seg=seg, x=x, width=width, hint=hint, divider_x=divider))
        x += width
    # 「全部显示」chip 紧跟三段（只在有隐藏段时由调用方决定要不要给这个段）。
    chip_w = 0
    chip_x: float | None = None
    if any(seg.hidden for seg in segments):
        chip_w = ALL_CHIP_MIN_W
        chip_x = x
        total += chip_w
    return PetBarPlan(
        placements=tuple(placements), width=max(1, int(round(total))),
        elided_hint=elided, all_chip_x=chip_x, all_chip_w=chip_w)
