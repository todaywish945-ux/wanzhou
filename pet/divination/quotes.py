# -*- coding: utf-8 -*-
"""每日英文的语录库（纯数据，零依赖）。

**形态（2026-11-23 用户定稿）**：

    英文一句（title） + 中文翻译（reading）

原来的「每日一签」（四句七言签诗 + 白话解签 + 吉凶档位）整块换成英文语录；
抽取机制（同一天同一句、一轮不重复、跨天换新）原样保留。

字段沿用 ``RawQuote`` 的四元组形状以免动到引擎与状态层：

* ``tier``  —— 固定填 ``"每日一句"``（中性占位，无吉凶含义，引擎按它定档/取句）；
* ``title`` —— 英文句子（气泡与播报的主内容）；
* ``verses`` —— 弃用，填空元组；
* ``reading`` —— 中文翻译。

规矩：**序号 = `RAW_QUOTES` 下标 + 1，只许追加、永不重排**——配置里存的是序号
（`divination_state.quote_id` / `drawn`），重排等于把当天那句悄悄换掉。
"""
from __future__ import annotations

from typing import NamedTuple


class RawQuote(NamedTuple):
    """一条语录的原始要素（序号由顺序决定，见模块 docstring）。"""

    tier: str
    title: str
    verses: tuple[str, str, str, str]
    reading: str


#: 每日一句的固定档位（中性，无吉凶含义）
DAILY_TIER = "每日一句"

#: 48 句。顺序＝序号顺序，**只许追加**。
RAW_QUOTES: tuple[RawQuote, ...] = (
    RawQuote(DAILY_TIER, "Carpe diem — seize the day.",
             (), "把握当下——抓住今天。"),
    RawQuote(DAILY_TIER, "The only way to do great work is to love what you do.",
             (), "成就伟业的唯一途径，是热爱你所做的事。"),
    RawQuote(DAILY_TIER, "Believe you can and you're halfway there.",
             (), "相信你能做到，你就已经成功了一半。"),
    RawQuote(DAILY_TIER, "It always seems impossible until it's done.",
             (), "事情在完成之前，看起来总是不可能的。"),
    RawQuote(DAILY_TIER, "Life is what happens when you're busy making other plans.",
             (), "生活就是当你忙于制定其他计划时发生的事。"),
    RawQuote(DAILY_TIER, "Get up, dress up, show up, and never give up.",
             (), "起身、收拾、登场，永不放弃。"),
    RawQuote(DAILY_TIER, "The best time to plant a tree was 20 years ago. The second best time is now.",
             (), "种树最好的时间是二十年前，其次是现在。"),
    RawQuote(DAILY_TIER, "What you do today can improve all your tomorrows.",
             (), "你今天所做的，能让你的每一个明天更好。"),
    RawQuote(DAILY_TIER, "Whether you think you can or you think you can't, you're right.",
             (), "无论你认为自己行还是不行，你都是对的。"),
    RawQuote(DAILY_TIER, "The secret of getting ahead is getting started.",
             (), "前进的秘诀，就是开始行动。"),
    RawQuote(DAILY_TIER, "Don't watch the clock; do what it does. Keep going.",
             (), "别盯着时钟看，学学它——一直向前走。"),
    RawQuote(DAILY_TIER, "Success is not final, failure is not fatal.",
             (), "成功并非终点，失败也非致命。"),
    RawQuote(DAILY_TIER, "It does not matter how slowly you go as long as you do not stop.",
             (), "只要不停下，走得多慢都没关系。"),
    RawQuote(DAILY_TIER, "The future depends on what you do today.",
             (), "未来取决于你今天做什么。"),
    RawQuote(DAILY_TIER, "You miss 100% of the shots you don't take.",
             (), "你不出手的球，百分之百会错过。"),
    RawQuote(DAILY_TIER, "Every day is a second chance.",
             (), "每一天都是一次新的机会。"),
    RawQuote(DAILY_TIER, "Be the change that you wish to see in the world.",
             (), "成为你希望在这个世界上看到的变化。"),
    RawQuote(DAILY_TIER, "The only impossible journey is the one you never begin.",
             (), "唯一不可能的旅程，是你从未启程的那一段。"),
    RawQuote(DAILY_TIER, "Fall seven times, stand up eight.",
             (), "跌倒七次，第八次站起来。"),
    RawQuote(DAILY_TIER, "Dream big and dare to fail.",
             (), "大胆梦想，敢于失败。"),
    RawQuote(DAILY_TIER, "Act as if what you do makes a difference. It does.",
             (), "就当你的所作所为意义重大——事实的确如此。"),
    RawQuote(DAILY_TIER, "Happiness is not something ready made. It comes from your own actions.",
             (), "幸福不是现成的东西，它来自你自己的行动。"),
    RawQuote(DAILY_TIER, "Do what you can, with what you have, where you are.",
             (), "在所处之地，用所有之物，做所能之事。"),
    RawQuote(DAILY_TIER, "Great things are done by a series of small things brought together.",
             (), "伟大的成就，是一件件小事汇聚而成的。"),
    RawQuote(DAILY_TIER, "The way to get started is to quit talking and begin doing.",
             (), "开始的方法，是停止空谈、动手去做。"),
    RawQuote(DAILY_TIER, "If you can dream it, you can do it.",
             (), "如果你能梦想它，你就能做到它。"),
    RawQuote(DAILY_TIER, "Don't let yesterday take up too much of today.",
             (), "别让昨天占据今天的太多时间。"),
    RawQuote(DAILY_TIER, "Everything you can imagine is real.",
             (), "你能想象的一切，都是真实的。"),
    RawQuote(DAILY_TIER, "It's not whether you get knocked down, it's whether you get up.",
             (), "重要的不是你是否被击倒，而是你是否站起来。"),
    RawQuote(DAILY_TIER, "Keep your face to the sunshine and you cannot see a shadow.",
             (), "面向阳光，你就看不见阴影。"),
    RawQuote(DAILY_TIER, "Simplicity is the ultimate sophistication.",
             (), "简约是最终的精致。"),
    RawQuote(DAILY_TIER, "The only person you are destined to become is the person you decide to be.",
             (), "你注定要成为的人，只有你自己决定的那一个。"),
    RawQuote(DAILY_TIER, "Knowledge is power.",
             (), "知识就是力量。"),
    RawQuote(DAILY_TIER, "Stay hungry, stay foolish.",
             (), "求知若饥，虚心若愚。"),
    RawQuote(DAILY_TIER, "Life is short, and it is here to be lived.",
             (), "生命短暂，它本来就是用来活的。"),
    RawQuote(DAILY_TIER, "What lies behind us and what lies before us are tiny matters compared to what lies within us.",
             (), "与内心拥有的力量相比，身后与眼前的一切都微不足道。"),
    RawQuote(DAILY_TIER, "You are never too old to set another goal or to dream a new dream.",
             (), "你永远不会老得不能定下新目标、做一个新的梦。"),
    RawQuote(DAILY_TIER, "Optimism is the faith that leads to achievement.",
             (), "乐观是通往成就的信念。"),
    RawQuote(DAILY_TIER, "There is no substitute for hard work.",
             (), "没有什么能代替努力。"),
    RawQuote(DAILY_TIER, "Whatever you are, be a good one.",
             (), "无论你是什么，都要做个出色的。"),
    RawQuote(DAILY_TIER, "The only limits are, as always, those of vision.",
             (), "唯一的限制，一如既往，是眼界。"),
    RawQuote(DAILY_TIER, "Make each day your masterpiece.",
             (), "把每一天都做成你的杰作。"),
    RawQuote(DAILY_TIER, "Don't wait. The time will never be just right.",
             (), "别等了。时机永远不会刚刚好。"),
    RawQuote(DAILY_TIER, "Where there is a will, there is a way.",
             (), "有志者，事竟成。"),
    RawQuote(DAILY_TIER, "The harder I work, the luckier I get.",
             (), "我越努力，就越幸运。"),
    RawQuote(DAILY_TIER, "Little by little, one travels far.",
             (), "一点一点地走，人能走得很远。"),
    RawQuote(DAILY_TIER, "Once you learn to read, you will be forever free.",
             (), "一旦学会阅读，你将永远自由。"),
    RawQuote(DAILY_TIER, "The best investment you can make is in yourself.",
             (), "你能做的最好的投资，是投资自己。"),
)
