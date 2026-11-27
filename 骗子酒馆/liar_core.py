# -*- coding: utf-8 -*-
"""骗子酒馆（Liar's Bar 单机版）规则引擎

规则与 AI 概率模型移植自 GameNest 项目（github.com/absswds/GameNest，Apache-2.0），
按许可证要求保留来源声明；本实现为 Python 移植并做了桌宠定制（人格化 AI）。

牌库 29 张：J/Q/K × 4花色 × 2副 + 万能牌★×4 + 幽灵牌👻×1
每轮：随机目标牌(J/Q/K)，每人发 5 张，按逆时针轮流出 1~3 张暗置牌并声明为目标牌。
下家可【继续出牌】或【质疑】：翻牌后——
  含幽灵牌 → 除出牌者外所有活人各开一枪
  全是真牌（目标牌或万能）→ 质疑者开枪
  有假牌 → 出牌者开枪
左轮枪：每人隐藏弹巢位置(1~6)，被罚开枪时 fired+1，恰好撞上弹位即淘汰。
手牌空的玩家跳过出牌（只剩质疑/被轮空），直至有人质疑或全部出完被迫质疑。
最后存活者获胜。
"""
import random

RANKS = ['J', 'Q', 'K']
SUITS = ['s', 'h', 'c', 'd']
SUIT_SYMBOL = {'s': '♠', 'h': '♥', 'c': '♣', 'd': '♦'}
DECK_SIZE = 29                # 24 数字牌 + 4 万能 + 1 幽灵
TOTAL_VALID_BASE = 8 + 4      # 目标rank 8张 + 万能 4张（AI 概率用）


def create_deck():
    deck = []
    for copy in range(2):
        for r in RANKS:
            for s in SUITS:
                deck.append({'rank': r, 'suit': s, 'id': '%s%s-%d' % (r, s, copy)})
    for i in range(4):
        deck.append({'rank': '★', 'suit': 'wild', 'id': 'wild-%d' % i})
    deck.append({'rank': '👻', 'suit': 'ghost', 'id': 'ghost'})
    return deck


def _turn_order(player_count):
    # 0=你(下), 1=德蕾琪娜(右), 2=林德薇恩(左), 3=艾尔妲(上)。
    return (0, 1, 3, 2) if player_count == 4 else tuple(range(player_count))


def next_alive(state, from_index):
    order = _turn_order(len(state['alive']))
    start = order.index(from_index)
    for offset in range(1, len(order) + 1):
        idx = order[(start + offset) % len(order)]
        if state['alive'][idx]:
            return idx
    return from_index


def next_turn(state, from_index):
    """下一个出牌者：逆时针跳过空手牌玩家；若无人有牌，轮到下一个活人（必须质疑）"""
    order = _turn_order(len(state['alive']))
    start = order.index(from_index)
    for offset in range(1, len(order) + 1):
        idx = order[(start + offset) % len(order)]
        if state['alive'][idx] and state['hands'][idx]:
            return idx
    return next_alive(state, from_index)


def start_new_round(state):
    deck = create_deck()
    random.shuffle(deck)
    state['hands'] = []
    for i in range(len(state['alive'])):
        if state['alive'][i]:
            state['hands'].append(deck[:5])
            deck = deck[5:]
        else:
            state['hands'].append([])
    state['theme_rank'] = random.choice(RANKS)
    state['pile_cards'] = []
    state['last_claimant'] = -1
    state['last_played_cards'] = []
    state['phase'] = 'playing'
    state['round_message'] = ''
    state['round_number'] = state.get('round_number', 0) + 1
    state['current_player'] = next_alive(state, state.get('round_starter', 0))
    state['round_starter'] = state['current_player']


def create_state(player_count):
    state = {
        'hands': [],
        'current_player': 0,
        'theme_rank': 'J',
        'pile_cards': [],
        'last_claimant': -1,
        'last_played_cards': [],
        'alive': [True] * player_count,
        'fired_shots': [0] * player_count,
        'round_starter': random.randrange(player_count),
        'round_message': '',
        'phase': 'playing',
        'winner': None,
        'shoot_queue': [],
        'current_shooter': -1,
        '_bullet_chamber': [random.randint(1, 6) for _ in range(player_count)],
    }
    start_new_round(state)
    return state


def fire(state, pi):
    """扣一次扳机：第 count 次开枪撞上隐藏弹位则死亡"""
    state['fired_shots'][pi] += 1
    count = state['fired_shots'][pi]
    dead = count == state['_bullet_chamber'][pi]
    if dead:
        state['alive'][pi] = False
    return {'player': pi, 'dead': dead, 'fired_count': count}


def handle_play(state, pi, card_ids):
    """出牌：card_ids 为手牌 id 列表（1~3 张）。返回错误码或 None"""
    if state.get('winner') is not None:
        return 'g_game_over'
    if not state['alive'][pi]:
        return 'lb_you_are_out'
    if state['phase'] != 'playing':
        return 'lb_wrong_phase'
    if pi != state['current_player']:
        return 'g_not_your_turn'
    if not card_ids or len(card_ids) > 3:
        return 'lb_select_a_card'
    hand = state['hands'][pi]
    if len(set(card_ids)) != len(card_ids):
        return 'lb_card_not_in_hand'
    by_id = {c['id']: c for c in hand}
    if not all(cid in by_id for cid in card_ids):
        return 'lb_card_not_in_hand'
    played = [by_id[cid] for cid in card_ids]
    state['hands'][pi] = [c for c in hand if c['id'] not in set(card_ids)]
    state['pile_cards'].extend(played)
    state['last_played_cards'] = [dict(c) for c in played]
    state['last_claimant'] = pi
    state['current_player'] = next_turn(state, pi)
    return None


def handle_suspect(state, pi):
    """质疑上家。返回错误码或 None；质疑后进入 shooting 阶段"""
    if state.get('winner') is not None:
        return 'g_game_over'
    if not state['alive'][pi]:
        return 'lb_you_are_out'
    if state['phase'] != 'playing':
        return 'lb_wrong_phase'
    if pi != state['current_player']:
        return 'g_not_your_turn'
    if state['last_claimant'] < 0:
        return 'lb_nothing_to_challenge'
    if state['last_claimant'] == pi:
        return 'lb_cannot_challenge_self'

    played = state['last_played_cards']
    claimed = state['theme_rank']
    has_ghost = any(c['suit'] == 'ghost' for c in played)
    has_lie = any(c['suit'] not in ('wild', 'ghost') and c['rank'] != claimed
                  for c in played)
    if has_ghost:
        shooters = [i for i in range(len(state['alive']))
                    if state['alive'][i] and i != state['last_claimant']]
        state['round_message'] = '是幽灵牌👻！除了出牌者，所有人都要开一枪'
    elif not has_lie:
        shooters = [pi]
        state['round_message'] = '质疑失败！出的都是 %s（含万能牌）' % claimed
    else:
        shooters = [state['last_claimant']]
        liar_card = next(c for c in played
                         if c['suit'] not in ('wild', 'ghost') and c['rank'] != claimed)
        state['round_message'] = '质疑成功！出的是 %s%s，不是 %s' % (
            SUIT_SYMBOL.get(liar_card['suit'], ''), liar_card['rank'], claimed)
    state['shoot_queue'] = shooters
    state['current_shooter'] = shooters[0] if shooters else -1
    state['phase'] = 'shooting'
    return None


def handle_shoot(state, pi):
    """shooting 阶段：当前射手扣扳机。全部打完后自动进入下一轮或结束"""
    if state['phase'] != 'shooting' or state['current_shooter'] != pi:
        return 'lb_not_your_shot'
    fire(state, pi)
    state['shoot_queue'] = [i for i in state['shoot_queue'] if i != pi]
    if state['shoot_queue']:
        state['current_shooter'] = state['shoot_queue'][0]
        return None
    state['current_shooter'] = -1
    alive_now = [i for i, a in enumerate(state['alive']) if a]
    if len(alive_now) <= 1:
        state['winner'] = alive_now[0] if alive_now else -1
        state['phase'] = 'round_end'
        return None
    state['round_starter'] = next_alive(state, max(0, state['last_claimant']))
    start_new_round(state)
    return None


# ---------- AI（移植自 GameNest bots/liarsbar.js，Apache-2.0） ----------

def _choose(n, k):
    if k < 0 or k > n:
        return 0
    r = 1.0
    for i in range(1, k + 1):
        r = r * (n - k + i) / i
    return r


def _hyper(pop, valid, h, j):
    """从剩牌 pop 张（其中 valid 张有效）中抽 h 张恰好 j 张有效的概率"""
    if h > pop:
        h = pop
    d = _choose(pop, h)
    if d == 0:
        return 0.0
    return _choose(valid, j) * _choose(pop - valid, h - j) / d


def lie_probability(state, me, my_valid):
    """估算上家最后声明是谎言的概率（假设对手诚实优先：有真牌全出，没牌才诈 1 张）"""
    claim = state['last_played_cards']
    k = max(1, len(claim))
    hands = state['hands']
    claimant_left = len(hands[state['last_claimant']]) if state['last_claimant'] >= 0 else 0
    earlier = max(0, len(state['pile_cards']) - k)
    my_hand = len(hands[me])
    pop = max(1, DECK_SIZE - my_hand - earlier)
    valid = max(0, min(pop, TOTAL_VALID_BASE - my_valid - round(earlier * 0.75)))
    h0 = claimant_left + k
    if k == 1:
        p0 = _hyper(pop, valid, h0, 0)
        p1 = _hyper(pop, valid, h0, 1)
        return 0.3 if p0 + p1 == 0 else p0 / (p0 + p1)
    if k == 2:
        return 0.12 + 0.5 * _hyper(pop, valid, h0, 0)
    return 0.18


def death_risk(state, pi):
    """下一次扣扳机的死亡概率：弹位均匀分布在未开过的弹巢中"""
    fired = state['fired_shots'][pi]
    return 1.0 if fired >= 5 else 1.0 / (6 - fired)


def should_suspect(state, me, my_valid, personality):
    """是否质疑：期望值比较（质疑收益 3 倍权重）+ 人格偏好"""
    if state['last_claimant'] < 0 or state['last_claimant'] == me:
        return False
    k = len(state['last_played_cards'])
    if k > TOTAL_VALID_BASE - my_valid:
        return True   # 声明的张数超过场上可能存在的有效牌数，必假
    p = lie_probability(state, me, my_valid)
    risk_me = death_risk(state, me)
    risk_c = death_risk(state, state['last_claimant'])
    if personality.get('difficulty') == 'normal':
        p = min(1.0, max(0.0, p + (random.random() - 0.5) * 0.35))
        return p * risk_c * 4 > (1 - p) * risk_me
    gain = p * risk_c * 3 * personality.get('call_bonus', 1.0)
    loss = (1 - p) * risk_me
    forced = 0.03 if my_valid == 0 else 0.0
    return gain + forced > loss


def future_value(card, hand):
    """弃牌未来价值（越低越适合拿去诈唬）"""
    value = 0
    for other in hand:
        if other['id'] == card['id']:
            continue
        if other['suit'] == card['suit'] and other['rank'] == card['rank']:
            value += 2
        if other['rank'] == card['rank']:
            value += 3
        if other['suit'] == 'wild':
            value += 1
    return value


def bot_move(state, pi, personality):
    """AI 决策：返回 {action: play/suspect/shoot, card_ids?}"""
    if state['phase'] == 'shooting':
        return {'action': 'shoot'}
    hand = state['hands'][pi]
    if not hand:
        return {'action': 'suspect'}   # 没牌只能质疑
    theme = state['theme_rank']
    exact = [c for c in hand if c['rank'] == theme]
    wilds = [c for c in hand if c['suit'] == 'wild']
    ghost = next((c for c in hand if c['suit'] == 'ghost'), None)
    my_valid = len(exact) + len(wilds)

    if should_suspect(state, pi, my_valid, personality):
        return {'action': 'suspect'}

    # 诚实优先：真牌最多出 3 张（人格影响诈唬倾向）
    bluff_ratio = personality.get('bluff', 0.0)
    if exact and random.random() > bluff_ratio * 0.5:
        return {'action': 'play', 'card_ids': [c['id'] for c in exact[:3]]}
    if wilds and (not exact or random.random() > bluff_ratio * 0.5):
        return {'action': 'play', 'card_ids': [c['id'] for c in (exact + wilds)[:3]]}

    # 必须诈唬：幽灵牌最安全（被质疑时全场其他人开枪），留到手里牌少时用
    if ghost and (personality.get('difficulty') == 'hard' or len(hand) <= 2):
        return {'action': 'play', 'card_ids': [ghost['id']]}

    lies = [c for c in hand if c['suit'] != 'ghost']
    if lies:
        # B 型激进人格：诈唬时敢扣 2 张，扣未来价值最低的
        n = 2 if (personality.get('bluff', 0) > 0.5 and len(lies) >= 2) else 1
        chosen = sorted(lies, key=lambda c: future_value(c, hand))[:n]
        return {'action': 'play', 'card_ids': [c['id'] for c in chosen]}
    return {'action': 'play', 'card_ids': [hand[0]['id']]}


# ---------- 自测 ----------
if __name__ == '__main__':
    random.seed(3)
    # 基础流转：4 人随机策略打到分胜负
    state = create_state(4)
    steps = 0
    while state['winner'] is None and steps < 3000:
        steps += 1
        if state['phase'] == 'shooting':
            handle_shoot(state, state['current_shooter'])
            continue
        pi = state['current_player']
        mv = bot_move(state, pi, {'difficulty': 'hard', 'bluff': 0.5})
        if mv['action'] == 'shoot':
            handle_shoot(state, pi)
        elif mv['action'] == 'suspect':
            err = handle_suspect(state, pi)
            assert err is None, (err, steps)
        else:
            err = handle_play(state, pi, mv['card_ids'])
            assert err is None, (err, steps)
    assert state['winner'] is not None, '对局未分出胜负'
    print('对局结束: 胜者=P%d, 总步数=%d' % (state['winner'], steps))
    # 质疑判定单元断言
    s = create_state(4)
    s['theme_rank'] = 'Q'
    s['phase'] = 'playing'
    s['hands'] = [[], [], [], []]
    s['alive'] = [True] * 4
    s['last_claimant'] = 1
    s['last_played_cards'] = [{'rank': 'J', 'suit': 's', 'id': 'x1'}]
    s['pile_cards'] = [dict(s['last_played_cards'][0])]
    s['current_player'] = 2
    err = handle_suspect(s, 2)
    assert err is None and s['phase'] == 'shooting' and s['shoot_queue'] == [1]
    assert '质疑成功' in s['round_message']

    turn_state = create_state(4)
    turn_state['alive'] = [True] * 4
    turn_state['hands'] = [[{'id': 'p%d' % i}] for i in range(4)]
    current = 0
    visited = []
    for _ in range(4):
        visited.append(current)
        current = next_turn(turn_state, current)
    assert visited == [0, 1, 3, 2], visited
    turn_state['hands'][1] = []
    assert next_turn(turn_state, 0) == 3
    turn_state['alive'][3] = False
    assert next_turn(turn_state, 0) == 2
    turn_state['alive'] = [True] * 4
    turn_state['hands'] = [[], [], [], []]
    assert next_turn(turn_state, 0) == 1
    turn_state['round_starter'] = 0
    start_new_round(turn_state)
    assert turn_state['current_player'] == 1
    print('ALL TESTS PASSED')
