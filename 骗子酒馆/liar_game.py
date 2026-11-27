# -*- coding: utf-8 -*-
"""骗子酒馆 · 自适应桌面牌局

透明桌面画布承载牌桌，牌面、弹巢风险与回合状态都有明确反馈。
规则引擎：liar_core.py（移植自 GameNest，Apache-2.0）
"""
import json
import math
import os
import random
import socket
import sys
import time

if not os.environ.get('LIAR_NO_LOCK'):
    try:
        _single = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _single.bind(('127.0.0.1', 51515))
        _single.listen(0)
    except OSError:
        os._exit(0)

from PySide6.QtCore import (Qt, QRect, QRectF, QPoint, QPointF, QPropertyAnimation,
                            QEasingCurve, QTimer, Signal)
from PySide6.QtGui import (QFont, QColor, QPainter, QPainterPath, QPen,
                           QBrush, QRegion, QLinearGradient, QPolygonF,
                           QShortcut, QIcon)
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout,
                               QVBoxLayout, QLabel, QPushButton, QFrame,
                               QMessageBox, QMenu, QGraphicsDropShadowEffect)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liar_core
from liar_core import SUIT_SYMBOL

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_ICON = os.path.join(ROOT, 'assets', 'liar_bar.ico')

def _resolve_event_file():
    """联动事件文件统一放 %APPDATA%/wanzhou-pet/（与桌宠侧 game_link 同源）。

    源码开发时桌宠仓库根可能有旧位置文件，作为回退兼容；
    写入永远走 APPDATA，两侧路径在源码/打包两种形态下都一致。
    """
    appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
    new_path = os.path.join(appdata, 'wanzhou-pet', '联动事件.json')
    if os.path.isfile(new_path):
        return new_path
    legacy = os.path.join(os.path.dirname(ROOT), '晚昼桌宠', '联动事件.json')
    if os.path.isfile(legacy):
        return legacy
    return new_path


EVENT_FILE = _resolve_event_file()

# 桌宠进程监视：源码运行时桌宠仓库就在同级目录，可 import；
# 打包成独立 exe 后收 pet.quit_all 进包（构建脚本 --paths），收不到就降级。
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), '晚昼桌宠'))
try:
    from pet.quit_all import find_pet_processes
except ImportError:
    def find_pet_processes():
        return []

PLAYER_IDS = ['你', '角色A', '角色B', '角色C']
PLAYER_NAMES = ['你', '德蕾琪娜', '林德薇恩', '艾尔妲']
PERSONALITIES = [
    None,
    {'difficulty': 'normal', 'bluff': 0.15, 'call_bonus': 1.0, 'tell': 0.18},
    {'difficulty': 'hard', 'bluff': 0.75, 'call_bonus': 1.5, 'tell': 0.0},
    {'difficulty': 'hard', 'bluff': 0.40, 'call_bonus': 1.0, 'tell': 0.28},
]
EMOTIONS = {
    '角色A': {'lie_caught': '开心', 'call_ok': '开心', 'survive': '开心',
             'win': '欢呼', 'bad': '犯困'},
    '角色B': {'lie_caught': '生气', 'call_ok': '大笑', 'survive': '大笑',
             'win': '大笑', 'bad': '震惊'},
    '角色C': {'lie_caught': '汗颜', 'call_ok': '微笑', 'survive': '微笑',
             'win': '微笑', 'bad': '不满'},
}
SEAT_COLORS = ['#e5484d', '#f5c518', '#3b82f6', '#22a565']
BASE_WIDTH = 1120
BASE_HEIGHT = 760


def ms(value):
    return max(1, int(value))


def notify_pets(events):
    try:
        data = {'ts': time.time(), 'events': events}
        os.makedirs(os.path.dirname(EVENT_FILE), exist_ok=True)
        tmp = EVENT_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False)
        os.replace(tmp, EVENT_FILE)
    except OSError:
        pass


def pet_emotion(name, kind):
    mapping = EMOTIONS.get(name)
    return mapping.get(kind) if mapping else None


def shadow(widget, blur=16):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setColor(QColor(0, 0, 0, 185))
    effect.setOffset(0, 3)
    widget.setGraphicsEffect(effect)


def font(size, bold=False):
    return QFont('Microsoft YaHei', max(8, int(size)),
                 QFont.Weight.Bold if bold else QFont.Weight.Normal)


def rounded_path(rect, radius):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def draw_star(painter, center, outer, inner, color):
    points = QPolygonF()
    for index in range(10):
        angle = -90 + index * 36
        radius = outer if index % 2 == 0 else inner
        radians = math.radians(angle)
        points.append(QPointF(center.x() + math.cos(radians) * radius,
                              center.y() + math.sin(radians) * radius))
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(points)


def draw_card(painter, rect, card=None, back=False, selected=False):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    radius = max(6, rect.width() * 0.10)
    if back:
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor('#3e4778'))
        gradient.setColorAt(1, QColor('#20263e'))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor('#7882b5'), max(1.0, rect.width() * 0.022)))
        painter.drawRoundedRect(rect, radius, radius)
        inset = rect.adjusted(5, 5, -5, -5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(218, 190, 105, 180), 1))
        painter.drawRoundedRect(inset, max(3, radius - 3), max(3, radius - 3))
        painter.save()
        painter.setClipPath(rounded_path(inset, max(3, radius - 3)))
        painter.setPen(QPen(QColor(151, 163, 219, 32), 1))
        step = max(12, rect.width() * 0.20)
        x = inset.left() - rect.height()
        while x < inset.right():
            painter.drawLine(QPointF(x, inset.top()),
                             QPointF(x + rect.height(), inset.bottom()))
            painter.drawLine(QPointF(x, inset.bottom()),
                             QPointF(x + rect.height(), inset.top()))
            x += step
        painter.restore()
        center = rect.center()
        draw_star(painter, center, rect.width() * 0.18,
                  rect.width() * 0.08, QColor(224, 196, 112, 220))
        painter.setPen(QColor('#f3e8c8'))
        painter.setFont(QFont('Georgia', max(14, int(rect.width() * 0.30)),
                              QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, '?')
        painter.restore()
        return

    if card['suit'] == 'ghost':
        background = QColor('#202a36')
        foreground = QColor('#a9f0ed')
        border = QColor('#5ac8c7')
    elif card['suit'] == 'wild':
        background = QColor('#fbf6e9')
        foreground = QColor('#8a5cf6')
        border = QColor('#a984f3')
    else:
        background = QColor('#f7f5ef')
        foreground = (QColor('#c43b43') if card['suit'] in ('h', 'd')
                      else QColor('#202b36'))
        border = (QColor('#f5c518') if selected
                  else QColor('#dfd9ca'))
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0, background.lighter(106))
    gradient.setColorAt(1, background)
    painter.setBrush(QBrush(gradient))
    painter.setPen(QPen(border, max(1.5, rect.width() * (0.040 if selected else 0.018))))
    painter.drawRoundedRect(rect, radius, radius)

    if card['suit'] == 'ghost':
        cx = rect.center().x()
        top = rect.top() + rect.height() * 0.27
        width = rect.width() * 0.43
        height = rect.height() * 0.43
        body = QPainterPath()
        body.moveTo(cx - width / 2, top + height)
        body.lineTo(cx - width / 2, top + height * 0.42)
        body.cubicTo(cx - width / 2, top, cx + width / 2, top,
                     cx + width / 2, top + height * 0.42)
        body.lineTo(cx + width / 2, top + height)
        body.lineTo(cx + width * 0.25, top + height * 0.82)
        body.lineTo(cx, top + height)
        body.lineTo(cx - width * 0.25, top + height * 0.82)
        body.closeSubpath()
        painter.setBrush(foreground)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(body)
        painter.setBrush(QColor('#20303b'))
        eye_y = top + height * 0.36
        painter.drawEllipse(QPointF(cx - width * 0.16, eye_y),
                            width * 0.07, height * 0.11)
        painter.drawEllipse(QPointF(cx + width * 0.16, eye_y),
                            width * 0.07, height * 0.11)
        painter.setPen(foreground)
        painter.setFont(font(max(8, rect.width() * 0.13), True))
        painter.drawText(rect, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                         'GHOST')
        painter.restore()
        return

    if card['suit'] == 'wild':
        center = rect.center()
        draw_star(painter, QPointF(center.x(), center.y() - rect.height() * 0.03),
                  rect.width() * 0.25, rect.width() * 0.11,
                  QColor('#8a5cf6'))
        painter.setPen(foreground)
        painter.setFont(font(max(8, rect.width() * 0.14), True))
        painter.drawText(rect, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                         'WILD')
        painter.setFont(font(max(8, rect.width() * 0.13), True))
        painter.drawText(rect.adjusted(7, 5, -7, -5),
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                         'JKR')
        painter.restore()
        return

    rank_font = QFont('Georgia', max(12, int(rect.width() * 0.25)),
                      QFont.Weight.Bold)
    suit_font = QFont('Segoe UI Symbol', max(11, int(rect.width() * 0.22)))
    margin = max(6, rect.width() * 0.10)
    painter.setPen(foreground)
    painter.setFont(rank_font)
    painter.drawText(rect.adjusted(int(margin), int(margin * 0.55), 0, 0),
                     Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                     card['rank'])
    painter.setFont(suit_font)
    painter.drawText(rect.adjusted(int(margin), int(rect.height() * 0.22), 0, 0),
                     Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                     SUIT_SYMBOL[card['suit']])
    painter.setFont(QFont('Segoe UI Symbol', max(24, int(rect.width() * 0.58))))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                     SUIT_SYMBOL[card['suit']])
    painter.save()
    painter.translate(rect.right() - margin, rect.bottom() - margin * 0.55)
    painter.rotate(180)
    painter.setFont(rank_font)
    painter.drawText(QRectF(-rect.width(), -rect.height(), rect.width(), rect.height()),
                     Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                     card['rank'])
    painter.restore()
    painter.restore()


class PlayingCard(QWidget):
    clicked = Signal(object)

    def __init__(self, card, scale=1.0, parent=None):
        super().__init__(parent)
        self.card = card
        self.scale = scale
        self.selected = False
        self.hovered = False
        self.setFixedSize(int(78 * scale), int(124 * scale))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        shadow(self, 12)

    def paintEvent(self, _):
        painter = QPainter(self)
        lift = 14 * self.scale
        if self.hovered:
            lift = 7 * self.scale
        if self.selected:
            lift = 1 * self.scale
        rect = QRectF(2 * self.scale, lift,
                      self.width() - 4 * self.scale, 106 * self.scale)
        draw_card(painter, rect, self.card, selected=self.selected)
        if self.selected:
            painter.setPen(QPen(QColor('#f5c518'), 2))
            painter.setBrush(QColor('#f5c518'))
            center = QPointF(rect.right() - 10 * self.scale,
                             rect.top() + 10 * self.scale)
            painter.drawEllipse(center, 6 * self.scale, 6 * self.scale)
            painter.setPen(QColor('#1c2733'))
            painter.setFont(font(8 * self.scale, True))
            painter.drawText(center - QPointF(3 * self.scale, -4 * self.scale), '✓')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.card)

    def enterEvent(self, _):
        self.hovered = True
        self.update()

    def leaveEvent(self, _):
        self.hovered = False
        self.update()


class TableCard(QWidget):
    def __init__(self, card=None, scale=1.0, parent=None):
        super().__init__(parent)
        self.card = card
        self.scale = scale
        if card is None:
            self.setFixedSize(int(60 * scale), int(86 * scale))
        else:
            self.setFixedSize(int(72 * scale), int(102 * scale))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        shadow(self, 10)

    def paintEvent(self, _):
        painter = QPainter(self)
        draw_card(painter, QRectF(1, 1, self.width() - 2, self.height() - 2),
                  self.card, back=self.card is None)


class FloatingText(QLabel):
    def __init__(self, size=13, color='#dde', parent=None):
        super().__init__(parent)
        self.setFont(font(size))
        self.setStyleSheet('color: %s;' % color)
        shadow(self, 12)

    def setText(self, text):
        super().setText(text)
        self.adjustSize()


class FeltTable(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor(20, 42, 39, 205))
        gradient.setColorAt(0.55, QColor(14, 29, 31, 220))
        gradient.setColorAt(1, QColor(28, 26, 34, 215))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(218, 190, 105, 125), 1.4))
        painter.drawRoundedRect(rect, 34, 34)
        inset = rect.adjusted(10, 10, -10, -10)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(218, 190, 105, 38), 1))
        painter.drawRoundedRect(inset, 26, 26)


class ChamberBar(QWidget):
    def __init__(self, scale=1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.fired = 0
        self.dead = False
        self.setFixedSize(int(96 * scale), int(24 * scale))

    def set_state(self, fired, dead):
        self.fired = fired
        self.dead = dead
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = 5.5 * self.scale
        for index in range(6):
            center = QPointF((6 + index * 16) * self.scale,
                             self.height() / 2)
            if index < self.fired:
                painter.setBrush(QColor('#090d13'))
                painter.setPen(QColor('#6f7788'))
            else:
                painter.setBrush(QColor('#3b4250'))
                painter.setPen(QColor('#828b9d'))
            painter.drawEllipse(center, radius, radius)
            if index < self.fired:
                painter.setPen(QColor('#596273'))
                painter.drawLine(center - QPointF(2.5 * self.scale, 0),
                                 center + QPointF(2.5 * self.scale, 0))


class PlayerPlaque(QFrame):
    def __init__(self, name, player_index, scale=1.0, parent=None):
        super().__init__(parent)
        self.name = name
        self.player_index = player_index
        self.scale = scale
        self.setFixedSize(int(206 * scale), int(80 * scale))
        self.setStyleSheet(
            'QFrame { background: rgba(19, 25, 34, 224);'
            ' border: 1px solid rgba(137, 151, 177, 90); border-radius: 14px; }')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(int(12 * scale), int(8 * scale),
                                  int(12 * scale), int(7 * scale))
        layout.setSpacing(int(2 * scale))
        header = QHBoxLayout()
        header.setSpacing(int(5 * scale))
        self.dot = QLabel('●')
        self.dot.setFont(font(10 * scale))
        self.name_label = QLabel(name)
        self.name_label.setFont(font(12 * scale, True))
        self.name_label.setStyleSheet('color: #eef1f7;')
        self.state_label = QLabel('')
        self.state_label.setFont(font(9 * scale, True))
        header.addWidget(self.dot)
        header.addWidget(self.name_label)
        header.addStretch()
        header.addWidget(self.state_label)
        layout.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(int(6 * scale))
        self.hand_label = QLabel('手牌 5')
        self.hand_label.setFont(font(9 * scale))
        self.hand_label.setStyleSheet('color: #9eabc0;')
        self.chambers = ChamberBar(scale)
        body.addWidget(self.hand_label)
        body.addStretch()
        body.addWidget(self.chambers)
        layout.addLayout(body)
        shadow(self, 12)

    def set_state(self, state):
        alive = state['alive'][self.player_index]
        active = ((state['current_player'] == self.player_index
                   and state['phase'] == 'playing')
                  or (state['phase'] == 'shooting'
                      and state['current_shooter'] == self.player_index))
        color = SEAT_COLORS[self.player_index]
        self.dot.setStyleSheet('color: %s;' % color)
        self.hand_label.setText('手牌 %d' % len(state['hands'][self.player_index]))
        self.chambers.set_state(state['fired_shots'][self.player_index], not alive)
        if not alive:
            self.state_label.setText('已出局')
            self.state_label.setStyleSheet('color: #9a6470;')
            border = 'rgba(130, 80, 92, 110)'
        elif state['phase'] == 'shooting' and state['current_shooter'] == self.player_index:
            self.state_label.setText('扣扳机')
            self.state_label.setStyleSheet('color: #ffca3a;')
            border = 'rgba(245, 197, 24, 220)'
        elif state['current_player'] == self.player_index and state['phase'] == 'playing':
            self.state_label.setText('思考中' if self.player_index else '你的回合')
            self.state_label.setStyleSheet('color: #ffca3a;')
            border = 'rgba(245, 197, 24, 220)'
        else:
            self.state_label.setText('')
            border = 'rgba(137, 151, 177, 90)'
        self.setStyleSheet(
            'QFrame { background: rgba(19, 25, 34, %d);'
            ' border: 1px solid %s; border-radius: 14px; }'
            % (150 if not alive else 224, border))


class LiarWindow(QWidget):
    def __init__(self, screen_rect=None):
        super().__init__()
        self.setWindowTitle('骗子酒馆 · 桌面牌局')
        self.setWindowIcon(QIcon(APP_ICON))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if screen_rect is None:
            screen_rect = QApplication.primaryScreen().availableGeometry()
        self.screen_rect = QRect(screen_rect)
        window_width = max(480, min(1000, self.screen_rect.width() - 32))
        window_height = max(480, min(680, self.screen_rect.height() - 32))
        window_x = self.screen_rect.x() + (self.screen_rect.width() - window_width) // 2
        window_y = self.screen_rect.y() + self.screen_rect.height() - window_height - 20
        self.setGeometry(window_x, window_y, window_width, window_height)
        self.ui_scale = max(0.72, min(1.05,
                                      window_width / BASE_WIDTH,
                                      window_height / BASE_HEIGHT))
        self._seat_base = {}
        self._update_seat_base()

        self.state = liar_core.create_state(4)
        self.state['current_player'] = 0
        self.selected_cards = []
        self.history = []
        self.bubbles = {}
        self.mask_widgets = []
        self._pet_delta = (0, 0)
        self._press_win_pos = None
        self._dealing = False
        self._rules_paused = False
        self._rule_told = False
        self._reveal_round = None
        self.auto_status = True
        self.status_text = ''
        self._ready = False

        self.turn_timer = QTimer(self)
        self.turn_timer.setSingleShot(True)
        self.turn_timer.timeout.connect(self.tick)
        self.deal_timer = QTimer(self)
        self.deal_timer.setSingleShot(True)
        self.deal_timer.timeout.connect(self._launch_next_deal_card)
        self.rule_timer = QTimer(self)
        self.rule_timer.setSingleShot(True)
        self.rule_timer.timeout.connect(self._resume_after_rules)
        self._pet_processes = find_pet_processes()
        self.pet_watch_timer = QTimer(self)
        self.pet_watch_timer.timeout.connect(self._watch_pet_processes)
        self.pet_watch_timer.start(750)

        self._build_ui()
        self._ready = True
        self._relayout_all()
        self.refresh_all()
        self._notify_seats()
        self.start_deal_animation()

    def _remember(self, widget):
        if widget.parent() is None:
            widget.setParent(self)
        self.mask_widgets.append(widget)
        return widget

    def _make_button(self, text, width, kind='secondary'):
        button = QPushButton(text, self)
        button.setFont(font(11 * self.ui_scale, True))
        button.setFixedSize(int(width * self.ui_scale), int(44 * self.ui_scale))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        colors = {
            'primary': ('rgba(245, 197, 24, 238)', '#1b2430',
                        'rgba(255, 218, 92, 245)'),
            'danger': ('rgba(190, 62, 72, 238)', '#fff5f3',
                       'rgba(222, 82, 91, 245)'),
            'secondary': ('rgba(47, 57, 73, 232)', '#e2e8f3',
                          'rgba(66, 79, 101, 240)'),
            'quiet': ('rgba(30, 36, 47, 218)', '#aeb9cb',
                      'rgba(54, 64, 82, 232)'),
        }
        normal, text_color, hover = colors[kind]
        button.setStyleSheet(
            'QPushButton { background: %s; color: %s; border: none;'
            ' border-radius: %dpx; }'
            'QPushButton:hover { background: %s; }'
            'QPushButton:disabled { background: rgba(45, 51, 62, 170);'
            ' color: rgba(188, 198, 214, 120); }'
            'QPushButton:pressed { padding-top: 2px; }'
            % (normal, text_color, int(22 * self.ui_scale), hover))
        return self._remember(button)

    def _build_ui(self):
        scale = self.ui_scale
        self.felt = FeltTable(self)

        self.round_label = self._remember(FloatingText(11 * scale, '#c6cfde'))
        self.round_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.round_label.setFixedSize(int(260 * scale), int(26 * scale))

        self.rules_btn = self._make_button('规则  ?', 84, 'secondary')
        self.rules_btn.clicked.connect(self.ask_rules)
        self.history_btn = self._make_button('记录', 68, 'quiet')
        self.history_btn.clicked.connect(self.toggle_history)
        self.restart_btn = self._make_button('重开', 76, 'quiet')
        self.restart_btn.clicked.connect(lambda: self.restart_game(ask=True))
        self.quit_btn = self._make_button('退出 ×', 84, 'quiet')
        self.quit_btn.clicked.connect(self.request_close)

        self.history_panel = self._remember(QFrame(self))
        self.history_panel.setFixedSize(int(268 * scale), int(126 * scale))
        self.history_panel.setStyleSheet(
            'QFrame { background: rgba(18, 24, 33, 205);'
            ' border: 1px solid rgba(137, 151, 177, 65);'
            ' border-radius: 13px; }')
        history_layout = QVBoxLayout(self.history_panel)
        history_layout.setContentsMargins(int(13 * scale), int(9 * scale),
                                          int(13 * scale), int(8 * scale))
        history_layout.setSpacing(int(3 * scale))
        history_title = QLabel('牌局记录')
        history_title.setFont(font(9 * scale, True))
        history_title.setStyleSheet('color: #f0c965;')
        self.history_label = QLabel('牌局准备中…')
        self.history_label.setFont(font(9 * scale))
        self.history_label.setStyleSheet('color: #a9b4c6;')
        self.history_label.setWordWrap(True)
        history_layout.addWidget(history_title)
        history_layout.addWidget(self.history_label)
        history_layout.addStretch()
        shadow(self.history_panel, 10)
        self.history_panel.hide()

        self.plaques = {}
        for player_id, pi in (('角色C', 3), ('角色A', 1), ('角色B', 2)):
            plaque = self._remember(PlayerPlaque(PLAYER_NAMES[pi], pi, scale, self))
            self.plaques[player_id] = plaque

        self.target = self._remember(QFrame(self))
        self.target.setFixedSize(int(128 * scale), int(98 * scale))
        self.target.setStyleSheet(
            'QFrame { background: rgba(20, 26, 36, 232);'
            ' border: 1px solid rgba(245, 197, 24, 150);'
            ' border-radius: 14px; }')
        target_layout = QVBoxLayout(self.target)
        target_layout.setContentsMargins(int(6 * scale), int(6 * scale),
                                         int(6 * scale), int(5 * scale))
        target_layout.setSpacing(0)
        target_caption = QLabel('本轮目标')
        target_caption.setFont(font(9 * scale, True))
        target_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        target_caption.setStyleSheet('color: #aab5c8;')
        self.theme_label = QLabel('J')
        self.theme_label.setFont(QFont('Georgia', int(34 * scale), QFont.Weight.Bold))
        self.theme_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.theme_label.setStyleSheet('color: #f5c518;')
        target_hint = QLabel('目标牌 + 万能牌共 12 张')
        target_hint.setFont(font(7 * scale))
        target_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        target_hint.setStyleSheet('color: #7f8ba0;')
        target_layout.addWidget(target_caption)
        target_layout.addWidget(self.theme_label)
        target_layout.addWidget(target_hint)
        shadow(self.target, 14)

        self.pile_host = self._remember(QWidget(self))
        self.pile_area = QHBoxLayout(self.pile_host)
        self.pile_area.setContentsMargins(0, 0, 0, 0)
        self.pile_area.setSpacing(int(-24 * scale))
        self.pile_count = self._remember(FloatingText(10 * scale, '#8e9bb0'))
        self.pile_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pile_count.setFixedSize(int(150 * scale), int(22 * scale))

        self.claim_label = self._remember(FloatingText(12 * scale, '#d9e1ee'))
        self.claim_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.claim_label.setFixedSize(int(520 * scale), int(34 * scale))
        self.claim_label.setWordWrap(True)

        self.msg_label = self._remember(FloatingText(15 * scale, '#f4e7bd'))
        self.msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_label.setFixedSize(int(520 * scale), int(62 * scale))
        self.msg_label.setWordWrap(True)

        self.you_plaque = self._remember(PlayerPlaque('你', 0, scale, self))
        self.hand_host = self._remember(QWidget(self))
        self.hand_area = QHBoxLayout(self.hand_host)
        self.hand_area.setContentsMargins(0, 0, 0, 0)
        self.hand_area.setSpacing(int(10 * scale))
        self.hand_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hand = self._remember(FloatingText(11 * scale, '#9aa7bb'))
        self.empty_hand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hand.setFixedSize(int(430 * scale), int(36 * scale))
        self.empty_hand.hide()

        self.play_btn = self._make_button('出牌  ↵', 172, 'primary')
        self.play_btn.clicked.connect(self.do_play)
        self.call_btn = self._make_button('质疑  C', 166, 'danger')
        self.call_btn.clicked.connect(self.do_suspect)

        self.result_panel = self._remember(QFrame(self))
        self.result_panel.setFixedSize(int(420 * scale), int(190 * scale))
        self.result_panel.setStyleSheet(
            'QFrame { background: rgba(18, 24, 32, 248);'
            ' border: 1px solid rgba(245, 197, 24, 190);'
            ' border-radius: 20px; }')
        result_layout = QVBoxLayout(self.result_panel)
        result_layout.setContentsMargins(int(24 * scale), int(18 * scale),
                                         int(24 * scale), int(18 * scale))
        result_layout.setSpacing(int(7 * scale))
        self.result_title = QLabel('对局结束')
        self.result_title.setFont(font(22 * scale, True))
        self.result_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_title.setStyleSheet('color: #f5c518;')
        self.result_subtitle = QLabel('')
        self.result_subtitle.setFont(font(10 * scale))
        self.result_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_subtitle.setStyleSheet('color: #aeb9cb;')
        self.result_subtitle.setWordWrap(True)
        result_buttons = QHBoxLayout()
        result_buttons.setSpacing(int(10 * scale))
        self.replay_btn = self._make_button('再来一局', 160, 'primary')
        self.replay_btn.clicked.connect(lambda: self.restart_game(ask=False))
        self.result_quit_btn = self._make_button('退出牌局', 132, 'danger')
        self.result_quit_btn.clicked.connect(self.request_close)
        result_buttons.addStretch()
        result_buttons.addWidget(self.replay_btn)
        result_buttons.addWidget(self.result_quit_btn)
        result_buttons.addStretch()
        result_layout.addStretch()
        result_layout.addWidget(self.result_title)
        result_layout.addWidget(self.result_subtitle)
        result_layout.addLayout(result_buttons)
        result_layout.addStretch()
        self.result_panel.hide()
        shadow(self.result_panel, 28)

        QShortcut(Qt.Key.Key_Return, self, activated=self.do_play)
        QShortcut(Qt.Key.Key_Enter, self, activated=self.do_play)
        QShortcut(Qt.Key.Key_C, self, activated=self.do_suspect)
        QShortcut(Qt.Key.Key_R, self, activated=lambda: self.restart_game(ask=True))
        QShortcut('?', self, activated=self.ask_rules)
        QShortcut(Qt.Key.Key_F1, self, activated=self.ask_rules)
        QShortcut(Qt.Key.Key_Escape, self, activated=self.request_close)

        self.felt.show()
        for widget in self.mask_widgets:
            if widget.parent() is self and widget not in (self.empty_hand,
                                                          self.result_panel,
                                                          self.history_panel):
                widget.show()

    def _relayout_all(self):
        if not self._ready:
            return
        scale = self.ui_scale
        width, height = self.width(), self.height()
        center = width // 2
        controls_y = int(height - 58 * scale)
        hand_y = int(controls_y - 132 * scale)
        you_y = hand_y - int(88 * scale)
        felt_top = int(190 * scale)
        felt_bottom = you_y - int(12 * scale)

        self.round_label.move(width - int(282 * scale), int(17 * scale))
        utility_y = int(58 * scale)
        utility_left = width - int(22 * scale + 336 * scale)
        self.rules_btn.move(utility_left, utility_y)
        self.history_btn.move(utility_left + int(92 * scale), utility_y)
        self.restart_btn.move(utility_left + int(168 * scale), utility_y)
        self.quit_btn.move(utility_left + int(252 * scale), utility_y)
        self.quit_btn.raise_()

        self.history_panel.move(int(22 * scale), felt_top + int(12 * scale))
        self.felt.setGeometry(int(center - 360 * scale), felt_top,
                              int(720 * scale), max(180 * scale, felt_bottom - felt_top))
        plaque_y = int(108 * scale)
        self.plaques['角色B'].move(int(22 * scale), plaque_y)
        self.plaques['角色C'].move(center - int(103 * scale), plaque_y)
        self.plaques['角色A'].move(width - int(228 * scale), plaque_y)

        self.target.move(int(center - 232 * scale), felt_top + int(58 * scale))
        self.pile_host.adjustSize()
        self.pile_host.move(center - self.pile_host.width() // 2,
                            felt_top + int(44 * scale))
        self.pile_count.move(center - int(75 * scale),
                             felt_top + int(132 * scale))
        self.claim_label.move(center - int(260 * scale),
                              felt_top + int(160 * scale))
        self.msg_label.move(center - int(260 * scale),
                            felt_top + int(202 * scale))

        self.you_plaque.move(center - int(103 * scale), you_y)
        self.hand_host.adjustSize()
        self.hand_host.move(center - self.hand_host.width() // 2, hand_y)
        self.empty_hand.move(center - int(215 * scale), hand_y + int(38 * scale))

        total_width = int(360 * scale)
        self.play_btn.move(center - total_width // 2, controls_y)
        self.call_btn.move(center - total_width // 2 + int(184 * scale), controls_y)
        self.result_panel.move(center - int(210 * scale),
                               felt_top + (felt_bottom - felt_top) // 2
                               - int(95 * scale))
        self.update_mask()

    def _auto_status_text(self):
        state = self.state
        if self._dealing:
            return '正在发牌…'
        if state['winner'] is not None:
            return '对局结束'
        if self._rules_paused:
            return '规则讲解中 · 牌局已暂停'
        if state['phase'] == 'shooting':
            return '%s 正在扣扳机…' % PLAYER_NAMES[state['current_shooter']]
        current = PLAYER_NAMES[state['current_player']]
        if state['current_player'] == 0:
            if not state['hands'][0]:
                return '你的手牌已出完 · 只能质疑上家'
            if state['last_claimant'] < 0:
                return '轮到你 · 选择 1~3 张牌扣下'
            return '轮到你 · 继续出牌，或质疑 %s' % PLAYER_NAMES[state['last_claimant']]
        return '等待 %s 行动…' % current

    def set_status(self, text, color='#f4e7bd'):
        self.auto_status = False
        self.status_text = text
        self.msg_label.setText(text)
        self.msg_label.setStyleSheet('color: %s;' % color)

    def refresh_all(self):
        state = self.state
        self.theme_label.setText(state['theme_rank'])
        self.round_label.setText('第 %d 轮  ·  存活 %d / 4'
                                 % (state.get('round_number', 1),
                                    sum(state['alive'])))
        for plaque in self.plaques.values():
            plaque.set_state(state)
        self.you_plaque.set_state(state)

        revealed = self._reveal_round == state.get('round_number')
        while self.pile_area.count():
            item = self.pile_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.pile_area.setSpacing(int((8 if revealed else -24) * self.ui_scale))
        if revealed:
            for card in state['last_played_cards']:
                widget = TableCard(card, self.ui_scale)
                self.pile_area.addWidget(widget)
                widget.show()
        elif state['pile_cards']:
            for _ in range(min(5, len(state['pile_cards']))):
                widget = TableCard(scale=self.ui_scale)
                self.pile_area.addWidget(widget)
                widget.show()
        else:
            empty = QLabel('牌堆为空')
            empty.setFont(font(10 * self.ui_scale))
            empty.setStyleSheet('color: #7b879a;')
            self.pile_area.addWidget(empty)
            empty.show()
        self.pile_host.adjustSize()
        self.pile_count.setText('已翻开' if revealed
                                else '牌堆 %d 张' % len(state['pile_cards']))

        if state['last_claimant'] >= 0:
            self.claim_label.setText(
                '上一手：<b style="color:#f5c518">%s</b> 扣了 '
                '<b>%d</b> 张，声称是 <b>%s</b>'
                % (PLAYER_NAMES[state['last_claimant']],
                   len(state['last_played_cards']), state['theme_rank']))
        else:
            self.claim_label.setText('等待第一位玩家扣牌')
        self.history_label.setText('<br>'.join(self.history[-4:]) or '牌局准备中…')

        self.selected_cards = [card for card in self.selected_cards
                               if any(hand['id'] == card['id']
                                      for hand in state['hands'][0])]
        while self.hand_area.count():
            item = self.hand_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for card in state['hands'][0]:
            widget = PlayingCard(card, self.ui_scale)
            widget.selected = any(card['id'] == selected['id']
                                  for selected in self.selected_cards)
            widget.clicked.connect(self._pick_card)
            self.hand_area.addWidget(widget)
            widget.show()
        self.empty_hand.setVisible(not state['hands'][0] and state['alive'][0])
        self.empty_hand.setText('这手已出完 · 只能质疑上家')

        my_turn = (state['current_player'] == 0 and state['phase'] == 'playing'
                   and state['winner'] is None and state['alive'][0])
        self.play_btn.setEnabled(my_turn and not self._dealing
                                 and not self._rules_paused
                                 and 1 <= len(self.selected_cards) <= 3)
        self.call_btn.setEnabled(my_turn and not self._dealing
                                 and not self._rules_paused
                                 and state['last_claimant'] >= 0
                                 and state['last_claimant'] != 0)
        if self.selected_cards:
            self.play_btn.setText('出牌 %d/3  ↵' % len(self.selected_cards))
        else:
            self.play_btn.setText('出牌  ↵')

        if self.auto_status:
            text = self._auto_status_text()
            if text != self.status_text:
                self.status_text = text
                self.msg_label.setText(text)
                self.msg_label.setStyleSheet('color: #f4e7bd;')
        self.result_panel.setVisible(state['winner'] is not None)
        if state['winner'] is not None:
            self.result_panel.raise_()
            self.replay_btn.raise_()
            self.result_quit_btn.raise_()
        self._relayout_all()

    def update_mask(self):
        if not hasattr(self, 'mask_widgets'):
            return
        region = QRegion(self.felt.geometry())
        for widget in self.mask_widgets:
            if widget.isVisible() and widget.parent() is self:
                region = region.united(QRegion(widget.geometry()))
        for bubble in self.bubbles.values():
            if bubble.isVisible():
                region = region.united(QRegion(bubble.geometry()))
        self.setMask(region)

    def _pick_card(self, card):
        if self.state['current_player'] != 0 or self.state['phase'] != 'playing':
            return
        if self._dealing or self._rules_paused:
            return
        existing = next((item for item in self.selected_cards
                         if item['id'] == card['id']), None)
        if existing is not None:
            self.selected_cards.remove(existing)
        elif len(self.selected_cards) >= 3:
            self.set_status('最多同时扣 3 张牌', '#f5c518')
            return
        else:
            self.selected_cards.append(card)
        self.auto_status = True
        self.refresh_all()

    def toggle_history(self):
        visible = not self.history_panel.isVisible()
        self.history_panel.setVisible(visible)
        self.history_btn.setText('收起' if visible else '记录')
        self.update_mask()

    def push_history(self, text):
        self.history.append(text)
        self.history_label.setText('<br>'.join(self.history[-4:]) or '牌局准备中…')

    def schedule(self, delay):
        if self._rules_paused or self._dealing or self.state['winner'] is not None:
            return
        self.turn_timer.start(ms(delay))

    def _update_seat_base(self):
        frame = self.frameGeometry()
        center = frame.center().x()
        scale = self.ui_scale
        felt_left = frame.left() + frame.width() // 2 - int(360 * scale)
        felt_right = frame.left() + frame.width() // 2 + int(360 * scale)
        gap = max(2, int(4 * scale))
        side_scale = max(0.20, min(
            0.48,
            (felt_left - self.screen_rect.left() - 16) / 640,
            (self.screen_rect.right() - felt_right - 16) / 640,
        ))
        top_scale = max(0.20, min(0.45, side_scale))
        side_width = int(640 * side_scale)
        side_height = int(390 * side_scale)
        top_width = int(640 * top_scale)
        top_height = int(390 * top_scale)
        side_y = frame.top() + int(200 * scale)
        plaque_center_inset = int(125 * scale)
        left_seat_x = frame.left() + plaque_center_inset - side_width // 2
        right_seat_x = (frame.left() + frame.width() - plaque_center_inset
                        - side_width // 2)
        top_x = center - int(170 * scale)
        top_y = frame.top() + int(108 * scale) - gap - top_height
        if top_y < self.screen_rect.top() + 8:
            top_x = felt_left - gap - top_width
            top_y = side_y + side_height + gap

        def clamp_x(x, width):
            return max(self.screen_rect.left() + 8,
                       min(x, self.screen_rect.right() - width - 7))

        def clamp_y(y, height):
            return max(self.screen_rect.top() + 8,
                       min(y, self.screen_rect.bottom() - height - 7))

        self._seat_base = {
            '角色C': {'x': clamp_x(top_x, top_width),
                     'y': clamp_y(top_y, top_height),
                     'scale': top_scale},
            '角色B': {'x': clamp_x(left_seat_x, side_width),
                     'y': clamp_y(side_y, side_height),
                     'scale': side_scale},
            '角色A': {'x': clamp_x(right_seat_x, side_width),
                     'y': clamp_y(side_y, side_height),
                     'scale': side_scale},
        }

    def _seat_move(self, name):
        base = self._seat_base[name]
        return {'x': int(base['x'] + self._pet_delta[0]),
                'y': int(base['y'] + self._pet_delta[1]),
                'scale': base['scale']}

    def _notify_seats(self):
        notify_pets([{'char': name, 'emotion': '待机', 'ms': 500,
                      'move': self._seat_move(name)}
                     for name in ('角色C', '角色A', '角色B')])

    def _bubble_position(self, name):
        plaque = self.plaques[name]
        return plaque.x(), plaque.y() + plaque.height() + int(4 * self.ui_scale)

    def show_bubble(self, name, text, duration=3000):
        old = self.bubbles.pop(name, None)
        if old is not None:
            old.deleteLater()
        bubble = QLabel(self)
        bubble.setFont(font(10 * self.ui_scale, True))
        bubble.setText(text)
        bubble.setStyleSheet(
            'QLabel { background: #fffdf5; color: #1c2733;'
            ' border: 2px solid #d8b93a; border-radius: 14px;'
            ' padding: 8px 14px; }')
        bubble.setWordWrap(True)
        width = min(int(390 * self.ui_scale),
                    int((95 + len(text) * 12) * self.ui_scale))
        lines = max(1, -(-len(text) * 12 // max(80, width - 34)))
        bubble.setFixedSize(width, int((40 + lines * 18) * self.ui_scale))
        bx, by = self._bubble_position(name)
        bx = max(12, min(self.width() - bubble.width() - 12, bx))
        by = max(int(96 * self.ui_scale),
                 min(self.height() - bubble.height() - int(120 * self.ui_scale), by))
        bubble.move(bx, by)
        bubble.show()
        self.bubbles[name] = bubble
        self.update_mask()
        QTimer.singleShot(ms(duration), lambda: self._hide_bubble(name, bubble))

    def _hide_bubble(self, name, bubble):
        if self.bubbles.get(name) is bubble:
            self.bubbles.pop(name, None)
            bubble.deleteLater()
            self.update_mask()

    def start_deal_animation(self):
        self.turn_timer.stop()
        self._dealing = True
        self._deal_waiting = False
        self._reveal_round = None
        self.selected_cards = []
        self.auto_status = True
        self.refresh_all()
        self._deal_targets = []
        for _ in range(5):
            for pi in (3, 2, 1, 0):
                self._deal_targets.append(self._deal_target(pi))
        self._launch_next_deal_card()

    def _deal_target(self, pi):
        if pi == 0:
            return QPointF(self.width() // 2 - 30 * self.ui_scale,
                           self.hand_host.y() + 20 * self.ui_scale)
        name = PLAYER_IDS[pi]
        move = self._seat_move(name)
        global_target = QPoint(int(move['x'] + 55 * self.ui_scale),
                               int(move['y'] + 125 * self.ui_scale))
        return QPointF(self.mapFromGlobal(global_target))

    def _launch_next_deal_card(self):
        if not self._deal_targets:
            if getattr(self, '_deal_waiting', False):
                self._deal_finished()
            else:
                self._deal_waiting = True
                self.deal_timer.start(ms(500))
            return
        target = self._deal_targets.pop(0)
        flying = TableCard(scale=self.ui_scale * 0.76, parent=self)
        flying.move(self.width() // 2 - int(23 * self.ui_scale),
                    self.pile_host.y())
        flying.show()
        animation = QPropertyAnimation(flying, b'pos', self)
        animation.setDuration(ms(300))
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(flying.deleteLater)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self.deal_timer.start(ms(58 if self._deal_targets else 520))

    def _deal_finished(self):
        self._dealing = False
        self.auto_status = True
        self.refresh_all()
        if self.state['winner'] is None:
            self.schedule(ms(350))

    def tick(self):
        state = self.state
        if state['winner'] is not None or self._dealing or self._rules_paused:
            return
        self.auto_status = True
        if state['phase'] == 'shooting':
            pi = state['current_shooter']
            fired_count = state['fired_shots'][pi] + 1
            liar_core.handle_shoot(state, pi)
            self.show_shot_result(pi, fired_count)
            return
        pi = state['current_player']
        if pi == 0:
            return
        move = liar_core.bot_move(state, pi, PERSONALITIES[pi])
        if move['action'] == 'suspect':
            error = liar_core.handle_suspect(state, pi)
            if error is None:
                self.show_bubble(PLAYER_IDS[pi], '慢着——我不信！开牌！')
                self.show_reveal(pi)
        else:
            self.do_ai_play(pi, move)

    def do_ai_play(self, pi, move):
        state = self.state
        chosen = set(move['card_ids'])
        is_bluff = any(card['suit'] not in ('wild', 'ghost')
                       and card['rank'] != state['theme_rank']
                       for card in state['hands'][pi] if card['id'] in chosen)
        liar_core.handle_play(state, pi, move['card_ids'])
        who_id = PLAYER_IDS[pi]
        who = PLAYER_NAMES[pi]
        count = len(move['card_ids'])
        self.set_status('%s 扣了 %d 张牌，声称是 %s'
                        % (who, count, state['theme_rank']))
        self.push_history('%s 扣 %d 张 → 声称 %s' % (who, count, state['theme_rank']))
        if is_bluff and who_id == '角色B':
            self.show_bubble(who_id, '我扣的可是真牌！信我！')
        else:
            self.show_bubble(who_id, '我扣了 %d 张 %s！' % (count, state['theme_rank']))
        if is_bluff and random.random() < PERSONALITIES[pi].get('tell', 0.0):
            emotion = {'角色A': '开心', '角色C': '微笑'}.get(who_id)
            if emotion:
                notify_pets([{'char': who_id, 'emotion': emotion, 'ms': 1800}])
        self.refresh_all()
        self.schedule(ms(random.randint(1050, 1850)))

    RULE_TOPICS = [
        ('目标牌怎么玩？',
         '每轮会指定 J、Q 或 K。大家暗扣的牌，都要声称是目标牌。你可以诚实地扣，也可以冒险欺诈。'),
        ('质疑与开枪',
         '轮到你时，可以出牌，也可以质疑上家。翻牌后有假牌，出牌者开枪；全是目标牌或万能牌，质疑者开枪。'),
        ('万能牌',
         '万能牌可以冒充任何目标牌，被翻出来也算真牌。全场有 4 张，和 8 张目标牌一起构成 12 张有效牌。'),
        ('幽灵牌',
         '幽灵牌被质疑时，除了出牌者，场上所有活人都要各开一枪。它是一张能改变局势的危险牌。'),
        ('左轮手枪',
         '每人的弹巢里秘密藏着一颗子弹。每被罚一次就开一枪，越往后风险越高。名牌旁的六个圆点会记录已开枪次数。'),
        ('怎么算赢',
         '活到最后就是赢家。记住目标牌只有 8 张，加上 4 张万能牌；有人扣得太多，就值得质疑。'),
    ]

    def ask_rules(self):
        if self.state['winner'] is not None:
            return
        alive_ai = [pi for pi in range(1, 4) if self.state['alive'][pi]]
        if not alive_ai:
            return
        self.turn_timer.stop()
        self.rule_timer.stop()
        self._rules_paused = True
        self._rule_told = False
        self.auto_status = True
        self.refresh_all()
        menu = QMenu(self)
        menu.setStyleSheet(
            'QMenu { background: #23262e; color: #dde;'
            ' border: 1px solid #444c66; border-radius: 10px; padding: 6px; }'
            'QMenu::item { padding: 8px 22px; border-radius: 6px; }'
            'QMenu::item:selected { background: #3b82f6; }')
        for index, (topic, _) in enumerate(self.RULE_TOPICS):
            menu.addAction(topic, lambda k=index: self._tell_rule(k))
        menu.exec(self.cursor().pos())
        if not self._rule_told:
            self._resume_after_rules()

    def _tell_rule(self, index):
        alive_ai = [pi for pi in range(1, 4) if self.state['alive'][pi]]
        if not alive_ai:
            self._resume_after_rules()
            return
        self._rule_told = True
        pi = random.choice(alive_ai)
        player_id = PLAYER_IDS[pi]
        opener = {'角色A': '让我来讲——', '角色B': '听好了——',
                  '角色C': '（推了推牌）'}[player_id]
        self.show_bubble(player_id, opener + self.RULE_TOPICS[index][1], duration=6800)
        emotion = pet_emotion(player_id, 'survive')
        if emotion:
            notify_pets([{'char': player_id, 'emotion': emotion, 'ms': 4000}])
        self.rule_timer.start(ms(6900))

    def _resume_after_rules(self):
        if not self._rules_paused:
            return
        self._rules_paused = False
        self.auto_status = True
        self.refresh_all()
        if self.state['winner'] is None and not self._dealing:
            self.schedule(ms(550))

    def do_suspect(self):
        state = self.state
        if (state['current_player'] != 0 or state['phase'] != 'playing'
                or self._dealing or self._rules_paused):
            return
        error = liar_core.handle_suspect(state, 0)
        if error:
            self.set_status('现在不能质疑', '#f5c518')
            return
        self.selected_cards = []
        self.show_reveal(0)

    def show_reveal(self, caller_pi):
        state = self.state
        self._reveal_round = state.get('round_number')
        caller = PLAYER_NAMES[caller_pi]
        self.set_status('%s 质疑！%s' % (caller, state['round_message']), '#f5c518')
        self.push_history('%s 质疑 → %s' % (caller, state['round_message']))
        shooters = set(state['shoot_queue'])
        if caller_pi > 0 and caller_pi not in shooters:
            self.show_bubble(PLAYER_IDS[caller_pi], '果然有诈！翻牌！')
        if state['last_claimant'] > 0 and state['last_claimant'] in shooters:
            self.show_bubble(PLAYER_IDS[state['last_claimant']],
                             '讨厌——被你拆穿了…')
        events = []
        for pi in range(1, 4):
            player_id = PLAYER_IDS[pi]
            if pi == state['last_claimant'] and pi in shooters:
                emotion = pet_emotion(player_id, 'lie_caught')
            elif pi == caller_pi and pi not in shooters:
                emotion = pet_emotion(player_id, 'call_ok')
            else:
                continue
            if emotion:
                events.append({'char': player_id, 'emotion': emotion, 'ms': 3000})
        if events:
            notify_pets(events)
        self.refresh_all()
        self.schedule(ms(2800))

    def show_shot_result(self, pi, fired_count):
        state = self.state
        who_id = PLAYER_IDS[pi]
        who = PLAYER_NAMES[pi]
        if not state['alive'][pi]:
            line = '砰！中弹了……'
            self.set_status('%s 中弹出局' % who, '#ff7b7b')
            self.push_history('%s 开枪：中弹出局' % who)
            if pi > 0:
                self.show_bubble(who_id, line, duration=2600)
                emotion = pet_emotion(who_id, 'bad') or '震惊'
                notify_pets([{'char': who_id, 'emotion': emotion,
                              'ms': 2600}])
        else:
            line = '咔嗒……活下来了。'
            self.set_status('%s 开枪幸存 · 第 %d 次'
                            % (who, fired_count), '#b9e2c5')
            self.push_history('%s 开枪：幸存' % who)
            if pi > 0:
                self.show_bubble(who_id, line, duration=2200)
                emotion = pet_emotion(who_id, 'survive')
                event = {'char': who_id, 'ms': 2200}
                if emotion:
                    event['emotion'] = emotion
                notify_pets([event])
        self.refresh_all()
        if state['winner'] is not None:
            self.finish_game()
        elif state['phase'] == 'playing':
            self.start_deal_animation()
        else:
            self.schedule(ms(1250))

    def finish_game(self):
        state = self.state
        winner = PLAYER_NAMES[state['winner']] if state['winner'] >= 0 else '无人'
        self.result_title.setText('%s 获胜' % winner)
        if state['winner'] == 0:
            subtitle = '你活到了最后。这一桌，你说了算。'
        elif state['winner'] > 0:
            subtitle = '%s 活到了最后。再来一局，把牌桌赢回来。' % winner
        else:
            subtitle = '幽灵牌带走了所有人。再来一局吧。'
        self.result_subtitle.setText('%s\n共进行 %d 轮' %
                                     (subtitle, state.get('round_number', 1)))
        self.set_status('对局结束 · %s 获胜' % winner, '#f5c518')
        if state['winner'] > 0:
            emotion = pet_emotion(PLAYER_IDS[state['winner']], 'win')
            if emotion:
                notify_pets([{'char': PLAYER_IDS[state['winner']],
                              'emotion': emotion, 'ms': 6000}])
        self.refresh_all()

    def restart_game(self, ask=False):
        if ask and self.state['winner'] is None:
            answer = QMessageBox.question(
                self, '重新开局', '当前牌局会结束，确定重新发牌吗？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.turn_timer.stop()
        self.deal_timer.stop()
        self.rule_timer.stop()
        self._rules_paused = False
        self.state = liar_core.create_state(4)
        self.state['current_player'] = 0
        self.selected_cards = []
        self.history = []
        self._reveal_round = None
        self.auto_status = True
        self.refresh_all()
        self._notify_seats()
        self.start_deal_animation()

    def do_play(self):
        state = self.state
        if (state['current_player'] != 0 or state['phase'] != 'playing'
                or self._dealing or self._rules_paused):
            return
        ids = [card['id'] for card in self.selected_cards]
        if not 1 <= len(ids) <= 3:
            self.set_status('请选择 1~3 张牌', '#f5c518')
            return
        error = liar_core.handle_play(state, 0, ids)
        if error:
            self.set_status('无法出牌：%s' % error, '#f5c518')
            return
        count = len(ids)
        self.selected_cards = []
        self.set_status('你扣了 %d 张牌，声称是 %s'
                        % (count, state['theme_rank']))
        self.push_history('你 扣 %d 张 → 声称 %s' % (count, state['theme_rank']))
        for index in range(count):
            flying = TableCard(scale=self.ui_scale * 0.8, parent=self)
            flying.move(self.hand_host.x() + int((20 + index * 82) * self.ui_scale),
                        self.hand_host.y() + int(25 * self.ui_scale))
            flying.show()
            animation = QPropertyAnimation(flying, b'pos', self)
            animation.setDuration(ms(380))
            animation.setEndValue(QPointF(self.width() // 2 + index * 5 * self.ui_scale,
                                          self.pile_host.y()))
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.finished.connect(flying.deleteLater)
            animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self.refresh_all()
        self.schedule(ms(1250))

    def showEvent(self, event):
        super().showEvent(event)
        self.update_mask()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._ready:
            self._pet_delta = (0, 0)
            self._update_seat_base()
            self._relayout_all()
            self._notify_seats()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.raise_()
            self.activateWindow()
            self.setFocus()
            self._drag_offset = (event.globalPosition().toPoint()
                                 - self.frameGeometry().topLeft())
            self._press_win_pos = self.pos()

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton
                and hasattr(self, '_drag_offset')):
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press_win_pos is not None:
            dx = self.x() - self._press_win_pos.x()
            dy = self.y() - self._press_win_pos.y()
            self._press_win_pos = None
            if abs(dx) + abs(dy) > 3:
                self._pet_delta = (self._pet_delta[0] + dx,
                                   self._pet_delta[1] + dy)
                self._notify_seats()
        event.accept()

    def _watch_pet_processes(self):
        if any(not process.is_running() for process in self._pet_processes):
            self.close()

    def request_close(self):
        self.close()

    def closeEvent(self, event):
        self.turn_timer.stop()
        self.deal_timer.stop()
        self.rule_timer.stop()
        self.pet_watch_timer.stop()
        notify_pets([{'char': name, 'emotion': '待机', 'ms': 1500,
                      'release': True}
                     for name in ('角色A', '角色B', '角色C')])
        self.hide()
        try:
            _single.close()
        except NameError:
            pass
        event.accept()
        QTimer.singleShot(0, QApplication.quit)


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(APP_ICON))
    window = LiarWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
