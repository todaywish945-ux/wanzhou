# -*- coding: utf-8 -*-
"""敲敲聊天窗（照搬原版）—— 用 QtWebEngine 直接跑叶瞬光的 HTML/CSS。

与原版逐像素一致：界面就是原版 style.css + 原版 DOM 结构，只是把后端的
``window.petAPI``（Electron IPC）换成 QtWebChannel 的 Python 桥接，AI 从
叶瞬光换成挽昼的 ChatService/SessionStore/PromptBuilder。

不做视频通话（用户明确只要私信聊天）。一个窗口内可切换三个挽昼角色。
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QMouseEvent, QPainterPath, QRegion
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .. import catalog
from .episodic_memory import EpisodicMemory, recall_text, schedule_summary
from .memory import ChatMemory, memory_payload
from .memory_extract import schedule_extraction
from .prompt import PromptBuilder
from .service import ChatService
from .session_store import SessionStore

logger = logging.getLogger(__name__)

_ASSETS = Path(__file__).resolve().parents[2] / "assets"
_KK = _ASSETS / "chat" / "kk"
_HTML = _KK / "kk.html"
_CHARACTERS = ("角色A", "角色B", "角色C")


class _Bridge(QObject):
    """暴露给 JS 的桥接：Python 槽 ↔ Qt 信号。"""

    sessionsChanged = Signal(str)
    chatOpened = Signal(str)
    bubbleAppended = Signal(str)
    textAppended = Signal(str)
    # 思考态：原版是「头像 + 三点气泡」，单独信号驱动（不占正式消息气泡）
    thinkingStarted = Signal()
    thinkingEnded = Signal()

    def __init__(self, window: "KKWebWindow"):
        super().__init__()
        self._win = window

    # -------------------------------------------------- JS 调用 Python
    @Slot(result=str)
    def initialData(self) -> str:  # noqa: N802 - JS 名
        # 开窗先给空态，但必须把**当前角色**的头像和名字交给前端。旧实现
        # 只给 groups 不给 chat，kk.html 走 showEmpty() 无参分支，会话头一直
        # 停在 HTML 里的 tab-dm.png 通用人形图标——看起来就是"头像不显示"。
        # 这里不自动打开会话（保留原来的空态交互），只填会话头。
        win = self._win
        return json.dumps({
            "groups": win._session_groups(),
            "chat": {
                "empty": True,
                "name": win.config.character_display_name(win.character_id),
                "avatar": win._avatar_data(win.character_id),
            },
        }, ensure_ascii=False)

    @Slot(str)
    def sendMessage(self, text: str) -> None:  # noqa: N802
        self._win._send(text)

    @Slot(str)
    def startTopic(self, text: str) -> None:  # noqa: N802
        self._win._start_topic(text)

    @Slot(str, str)
    def openSession(self, cid: str, sid: str) -> None:  # noqa: N802
        self._win._open_session(cid, sid)

    @Slot(str)
    def switchCharacter(self, cid: str) -> None:  # noqa: N802
        """点角色组头：切到该角色最近的会话（没有就建一个空对话）。"""
        self._win._switch_character(cid)

    @Slot(str)
    def newSession(self, cid: str) -> None:  # noqa: N802
        """点角色组头的 ＋：为该角色新建一个空会话并打开。"""
        self._win._new_session(cid)

    @Slot(str)
    def deleteSessions(self, items_json: str) -> bool:  # noqa: N802
        """批量/单条删除会话：items_json = [{"cid":..,"sid":..}, ...]。"""
        return self._win._delete_sessions(items_json)

    @Slot()
    def minimize(self) -> None:  # noqa: N802
        self._win.showMinimized()

    @Slot()
    def closeWindow(self) -> None:  # noqa: N802
        self._win.close()

    @Slot()
    def openSettings(self) -> None:  # noqa: N802
        self._win._open_settings()

    @Slot()
    def dragStart(self) -> None:  # noqa: N802
        """标题栏按下：记鼠标全局坐标相对窗口左上角的偏移（Qt 逻辑坐标，免 DPR 错位）。"""
        from PySide6.QtGui import QCursor
        gp = QCursor.pos()
        self._win._drag_offset = (gp.x() - self._win.x(), gp.y() - self._win.y())

    @Slot()
    def dragMove(self) -> None:  # noqa: N802
        """标题栏拖动：用 Python 侧真实鼠标位置移动窗口。"""
        off = getattr(self._win, "_drag_offset", None)
        if off is None:
            return
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QCursor
        gp = QCursor.pos()
        self._win.move(QPoint(gp.x() - off[0], gp.y() - off[1]))

    @Slot()
    def dragEnd(self) -> None:  # noqa: N802
        self._win._drag_offset = None


class KKWebWindow(QWidget):
    """照搬原版界面的敲敲聊天窗（QWebEngine 承载）。"""

    def __init__(self, config, character_id: str = "角色A", parent=None):
        super().__init__(parent)
        self.config = config
        self.character_id = character_id if character_id in _CHARACTERS else "角色A"
        self.setObjectName("kk-web-window")
        self.setWindowTitle("敲敲")
        # 置顶：桌宠本身是置顶窗，聊天窗不置顶会被它/别的程序盖住，WebEngine 就
        # 收不到点击（表现为"点两下就点不动"）。原版敲敲平板也是始终浮在桌面的。
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
                            | Qt.WindowType.WindowStaysOnTopHint)
        # 注意：WA_TranslucentBackground 会让 QWebEngineView 命中测试失效（点击穿透），
        # 敲敲界面本身满屏暗纹不需要透明，故这里不开启透明背景。
        self.setAutoFillBackground(True)
        # 圆角外的兜底色：与 HTML 里 #screen 的顶色一致。即使 mask 因平台差异
        # 没裁干净，露出的也是深色而非白色直角。
        self.setStyleSheet("QWidget#kk-web-window { background: #17171b; }")
        self.resize(880, 620)
        self.setMinimumSize(680, 460)

        self.prompt_builder = PromptBuilder(_ASSETS / "characters")
        # 三只挽昼是三进程分槽（slot-1/2/3 各存各的会话）。敲敲窗要能切三个角色，
        # 必须按角色去对应 slot 目录读写，而不是只看当前进程那一个 store。
        self.store = SessionStore(config.dir, getattr(config, "instance_id", ""))
        # 当前进程自带的 store 就服务它自己那只角色
        self._stores: dict[str, SessionStore] = {self.character_id: self.store}
        self.service = ChatService(parent=self)
        # 回复完成后由 service 同步调这个钩子 → 静默提炼对话总结（档 B），
        # 存进该角色 slot 的 memory.json，实现跨会话聊天。
        self.service.memory_extract_hook = self._schedule_memory_extract
        self._req_id: str | None = None
        self._stream_text = ""
        self._last_user_text = ""
        self._session = None  # 当前打开的会话；未打开任何会话时为 None
        self._avatar_for_current = ""

        self._bridge = _Bridge(self)
        self._build()

        self.service.started.connect(self._on_started)
        self.service.delta.connect(self._on_delta)
        self.service.finished.connect(self._on_finished)
        self.service.error.connect(self._on_error)
        self.service.stopped.connect(self._on_stopped)
        # 构造期 resize 未必发出 resizeEvent（尺寸恰好等于默认值时），显式裁一次
        self._apply_rounded_mask()

    def _apply_rounded_mask(self) -> None:
        """按 HTML 的圆角裁掉窗口四角：QWidget 默认方形背景会在 #screen 的
        圆角外露出白色直角。用 mask 只裁窗口形状，不开 WA_TranslucentBackground
        ——后者会让 QWebEngineView 命中测试失效（点不动），mask 不影响圆角内点击。
        半径与 original.css 的 --screen-radius: 34px 一致。
        """
        radius = 34
        path = QPainterPath()
        path.addRoundedRect(self.rect().toRectF(), radius, radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_rounded_mask()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        # QWebEngineView 默认 focusPolicy=NoFocus，会导致鼠标点击进不了页面 DOM
        # （表现为"界面显示正常但点不动"）——必须显式设为 StrongFocus。
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        lay.addWidget(self.view)

        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        channel = QWebChannel(self.view.page())
        self.view.page().setWebChannel(channel)
        channel.registerObject("bridge", self._bridge)

        # 注意：不要在 view 上装鼠标 eventFilter 做拖动——WebEngine 的点击要
        # 原样透传给页面，一旦在过滤器里按坐标吞事件，顶部页签/侧栏角色就全
        # 点不动（只剩 JS 直绑的最小化/关闭能用）。拖动改由 HTML 侧 bridge
        # 的 drag 方法实现，只认标题栏、不碰内容区。
        if _HTML.is_file():
            self.view.load(QUrl.fromLocalFile(str(_HTML)))
        else:
            logger.warning("敲敲 HTML 不存在: %s", _HTML)

    # ------------------------------------------------------------ 多角色会话仓库
    def _store_for(self, cid: str) -> SessionStore:
        """按角色取对应 slot 的会话仓库（跨进程分槽架构）。

        三只桌宠各跑一个进程、会话存在 sessions-slot-N/<角色>/。当前进程自带
        store 直接用；其他角色探测 slot 目录（sessions-slot-1/2/3 下谁有这个
        角色目录就用谁），找不到就退回当前 store（至少能新建空对话）。
        """
        if cid in self._stores:
            return self._stores[cid]
        root = self.store.root.parent  # .../wanzhou-pet
        for slot in (1, 2, 3):
            slot_root = root / f"sessions-slot-{slot}"
            if (slot_root / cid).is_dir():
                store = SessionStore(root, f"slot-{slot}")
                self._stores[cid] = store
                return store
        # 没有现成目录：用当前进程的 store（新建会话时会落到当前 slot）
        self._stores[cid] = self.store
        return self.store

    # ------------------------------------------------------------ 跨会话记忆
    def _memory_path(self, cid: str) -> Path:
        """该角色的记忆卡路径：与其会话同 slot 目录下（与现有聊天窗同口径）。"""
        return self._store_for(cid).root / cid / "memory.json"

    def _memory_injection(self, cid: str):
        """本轮提示词注入快照：enabled/无记忆 → 空。"""
        memory = ChatMemory(self._memory_path(cid))
        return memory_payload(memory, bool(self.config.get("chat_memory_enabled", True)))

    def _episodic_memory(self, cid: str) -> EpisodicMemory:
        """叶瞬光式情景记忆（双卡 + 向量）：每角色一份，按 slot 目录。"""
        cache = getattr(self, "_episodic_cache", None)
        if cache is None:
            cache = self._episodic_cache = {}
        if cid not in cache:
            path = self._store_for(cid).root / cid / "episodic-memory.json"
            cache[cid] = EpisodicMemory(path)
        return cache[cid]

    def _episodic_recall(self, cid: str, query: str, current_sid: str) -> str:
        """语义召回（有 5 秒超时保护）；未启用或失败返回空串。"""
        if not self.config.get("chat_memory_enabled", True):
            return ""
        cfg = self.config.chat_settings().active_config
        key = self.config.resolve_api_key(cfg)
        try:
            return recall_text(
                self._episodic_memory(cid), query, current_sid,
                base_url=cfg.base_url, api_key=key,
            )
        except Exception:
            return ""

    def _schedule_memory_extract(self, user_text: str, reply_text: str, provider, provider_config) -> None:
        """回复完成后静默提炼总结（护栏/后台线程都在 memory_extract 内）。

        用发送时锁定的角色（不是当前 character_id）——用户在回复途中切了角色，
        回忆也必须写回原会话那只角色的记忆卡（与原项目同口径）。
        """
        cid = getattr(self, "_send_character", self.character_id)
        schedule_extraction(
            config=self.config,
            memory_path=self._memory_path(cid),
            user_text=user_text, reply_text=reply_text,
            provider=provider, provider_config=provider_config,
        )

    # ------------------------------------------------------------ 数据 → JS
    def _session_groups(self) -> list[dict]:
        groups = []
        for cid in _CHARACTERS:
            sessions = self._store_for(cid).list(cid)
            name = self.config.character_display_name(cid)
            group = {
                "cid": cid, "name": name,
                "avatar": self._avatar_data(cid),
                "active": cid == self.character_id,
                "sessions": [],
            }
            for s in sessions[:10]:
                title = s.custom_title or (s.messages[0].content[:18] if s.messages else "新的对话")
                preview = (s.messages[-1].content[:20] if s.messages else "还没开始聊")
                when = s.updated_at[5:16].replace("T", " ")
                current_sid = getattr(getattr(self, "_session", None), "session_id", None)
                group["sessions"].append({
                    "sid": s.session_id, "title": title,
                    "preview": preview, "time": when,
                    # 当前打开的会话高亮（原版 session.id === currentSession.id）
                    "selected": cid == self.character_id and s.session_id == current_sid,
                })
            groups.append(group)
        return groups

    def _avatar_data(self, cid: str) -> str:
        """角色头像：走 file:// 指向待机 GIF 首帧不可行（GIF 首帧即 img），
        这里用项目内已有的角色贴纸占位；缺失就用页签图标兜底。"""
        # 优先用 skins 目录的角色头像（叶瞬光是 skin/avatar.png）
        skin = _KK / f"avatar-{cid}.png"
        if skin.is_file():
            return QUrl.fromLocalFile(str(skin)).toString()
        return "tab-dm.png"

    def _push_sessions(self) -> None:
        self._bridge.sessionsChanged.emit(json.dumps(
            {"groups": self._session_groups()}, ensure_ascii=False))

    # ------------------------------------------------------------ 会话操作
    def _create_empty_session(self, cid: str):
        """为角色建一个已落盘的空会话（一轮一框 / 点＋共用）。"""
        store = self._store_for(cid)
        settings = self.config.chat_settings()
        msgs = self.prompt_builder.build_messages(settings, cid, [], "ping")
        system = next((m["content"] for m in msgs if m.get("role") == "system"), "")
        session = store.create(cid, settings.active_config.provider_id, system)
        store.save(session)
        return session

    def _get_or_create_session(self, cid: str):
        store = self._store_for(cid)
        sessions = store.list(cid)
        if sessions:
            return sessions[0]
        return self._create_empty_session(cid)

    def _open_session(self, cid: str, sid: str) -> None:
        # JS 桥的参数不可信：和 _switch_character/_delete_sessions 一样先过白名单，
        # 否则 cid 里的 ../ 会让 SessionStore 去读会话目录外的文件。
        if cid not in _CHARACTERS or not sid:
            return
        session = self._store_for(cid).load(sid, cid)
        if not session:
            return
        self.character_id = cid
        self._session = session
        self._avatar_for_current = self._avatar_data(cid)
        # 重建列表 → 左侧角色/会话高亮切到当前项（否则点了看着没反应）
        self._push_sessions()
        payload = {
            "title": session.custom_title or (session.messages[0].content[:18] if session.messages else "新的对话"),
            "time": session.updated_at[5:16].replace("T", " "),
            "name": self.config.character_display_name(cid),
            "avatar": self._avatar_for_current,
            "messages": [{"role": m.role, "content": m.content} for m in session.messages],
        }
        self._bridge.chatOpened.emit(json.dumps(payload, ensure_ascii=False))

    def _switch_character(self, cid: str) -> None:
        """切角色：有会话开最近的，没有就展示该角色的空话题页。"""
        if cid not in _CHARACTERS:
            return
        self.character_id = cid
        sessions = self._store_for(cid).list(cid)
        if sessions:
            self._open_session(cid, sessions[0].session_id)
        else:
            self._session = None
            self._avatar_for_current = self._avatar_data(cid)
            self._push_sessions()
            self._bridge.chatOpened.emit(json.dumps({
                "title": "", "time": "",
                "name": self.config.character_display_name(cid),
                "avatar": self._avatar_for_current,
                "messages": [], "empty": True,
            }, ensure_ascii=False))

    def _new_session(self, cid: str) -> None:
        """为指定角色新建空会话并打开（组头的 ＋ 按钮）。"""
        if cid not in _CHARACTERS:
            return
        self.character_id = cid
        session = self._create_empty_session(cid)
        self._session = session
        self._avatar_for_current = self._avatar_data(cid)
        self._push_sessions()
        self._bridge.chatOpened.emit(json.dumps({
            "title": "", "time": "",
            "name": self.config.character_display_name(cid),
            "avatar": self._avatar_for_current,
            "messages": [], "empty": True,
        }, ensure_ascii=False))

    def _delete_sessions(self, items_json: str) -> bool:
        """删除会话（批量管理/单条×），删掉当前会话则回到该角色的空态。"""
        try:
            items = json.loads(items_json)
        except (ValueError, TypeError):
            return False
        if not isinstance(items, list):
            return False
        deleted_current = False
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("cid") or "")
            sid = str(item.get("sid") or "")
            if cid not in _CHARACTERS or not sid:
                continue
            store = self._store_for(cid)
            session = store.load(sid, cid)
            if session is None:
                continue
            store.delete(session)
            if (self._session is not None
                    and self._session.session_id == sid
                    and cid == self.character_id):
                deleted_current = True
        if deleted_current:
            self._session = None
            self._avatar_for_current = self._avatar_data(self.character_id)
            self._bridge.chatOpened.emit(json.dumps({
                "empty": True, "name": self.config.character_display_name(self.character_id),
                "avatar": self._avatar_for_current,
            }, ensure_ascii=False))
        self._push_sessions()
        return True

    def _start_topic(self, text: str) -> None:
        self.character_id = self.character_id
        self._session = self._get_or_create_session(self.character_id)
        self._avatar_for_current = self._avatar_data(self.character_id)
        payload = {
            "title": text[:18], "time": "",
            "name": self.config.character_display_name(self.character_id),
            "avatar": self._avatar_for_current, "messages": [],
        }
        self._bridge.chatOpened.emit(json.dumps(payload, ensure_ascii=False))
        self._send(text)

    # ------------------------------------------------------------ AI 发送
    def _send(self, text: str) -> None:
        if not text.strip():
            return
        # 锁定本轮归属角色（回复途中切角色也不写错记忆卡）
        self._send_character = self.character_id
        session = getattr(self, "_session", None)
        # 在当前会话里继续聊：不自动新建会话。想开新对话时用户点角色旁的「＋」。
        if session is None:
            session = self._session = self._get_or_create_session(self.character_id)
        fresh, _ = self._store_for(self.character_id).append_message(
            session, self._make_message("user", text))
        if fresh is not None:
            self._session = session = fresh
        # 用户气泡统一由 Python 发（JS 的 sendText 只管调 sendMessage）
        self._bridge.bubbleAppended.emit(json.dumps(
            {"role": "user", "text": text}, ensure_ascii=False))

        settings = self.config.chat_settings()
        cfg = settings.active_config
        cfg.api_key = self.config.resolve_api_key(cfg)
        msgs = self.prompt_builder.build_messages(
            settings, self.character_id, session.messages[:-1], text,
            # 跨会话记忆：注入该角色过往对话的总结（memory.json 提炼卡）
            memory_payload=self._memory_injection(self.character_id),
            roleplay_enabled=bool(self.config.get("roleplay_enabled", False)),
            roleplay_scene=str(self.config.get("roleplay_scene", "") or ""),
            roleplay_cast=str(self.config.get("roleplay_cast", "") or ""),
        )
        # 叶瞬光式情景记忆：语义相似度召回更早的对话（拼进 system 末尾）
        episodic = self._episodic_recall(
            self.character_id, text, getattr(session, "session_id", ""))
        if episodic and msgs and msgs[0].get("role") == "system":
            msgs[0]["content"] = (msgs[0]["content"] + episodic).strip()
        self._req_id = uuid.uuid4().hex
        self._stream_text = ""
        self.service.send(msgs, cfg, request_id=self._req_id)
        self._push_sessions()

    @staticmethod
    def _make_message(role: str, content: str):
        from .models import ChatMessage
        return ChatMessage(role=role, content=content)

    def _on_started(self, req: str) -> None:
        if req == self._req_id:
            # 原版"思考中"是头像 + 三点气泡（.h-row.assistant.live），单独信号驱动
            self._bridge.thinkingStarted.emit()

    def _on_delta(self, req: str, text: str) -> None:
        if req != self._req_id:
            return
        self._stream_text += text
        self._bridge.textAppended.emit(json.dumps(
            {"text": self._stream_text, "avatar": self._avatar_for_current},
            ensure_ascii=False))

    def _on_finished(self, req: str, text: str) -> None:
        if req != self._req_id:
            return
        self._bridge.textAppended.emit(json.dumps(
            {"text": text, "avatar": self._avatar_for_current}, ensure_ascii=False))
        self._bridge.thinkingEnded.emit()
        fresh, _ = self._store_for(self.character_id).append_message(
            self._session, self._make_message("assistant", text))
        if fresh is not None:
            self._session = fresh
        # 叶瞬光式情景记忆：静默 90 秒后把这段对话压成一条带向量的回忆
        cid = getattr(self, "_send_character", self.character_id)
        if self.config.get("chat_memory_enabled", True) and self._session is not None:
            prov = self.config.chat_settings().active_config
            try:
                schedule_summary(
                    session_id=getattr(self._session, "session_id", ""),
                    memory=self._episodic_memory(cid),
                    messages=[{"role": m.role, "content": m.content} for m in self._session.messages],
                    base_url=prov.base_url,
                    api_key=self.config.resolve_api_key(prov),
                    model=prov.model,
                )
            except Exception:
                logger.debug("情景记忆总结调度失败（已静默）", exc_info=True)
        self._req_id = None
        self._push_sessions()

    def _on_error(self, req: str, text: str) -> None:
        if req != self._req_id:
            return
        self._bridge.textAppended.emit(json.dumps(
            {"text": f"出错了：{text}", "avatar": self._avatar_for_current},
            ensure_ascii=False))
        self._bridge.thinkingEnded.emit()
        self._req_id = None

    def _on_stopped(self, req: str) -> None:
        if req == self._req_id:
            self._bridge.thinkingEnded.emit()
            self._req_id = None

    def _open_settings(self) -> None:
        parent = self.parent()
        opener = getattr(parent, "open_chat_settings", None)
        if callable(opener):
            opener()

    # ------------------------------------------------------------ 置前
    def bring_to_front(self) -> None:
        """强制窗口到前台：Qt 的 raise_/activateWindow 在 Windows 前台锁定下
        常被忽略（窗口显示却被别的程序盖住 → 点击落不到 WebEngine）。用
        AttachThreadInput + SetForegroundWindow 绕过前台锁定；失败也不炸。"""
        self.show()
        self.raise_()
        self.activateWindow()
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            fg = user32.GetForegroundWindow()
            if fg == hwnd:
                return
            thread = user32.GetWindowThreadProcessId(fg, None)
            current = ctypes.windll.kernel32.GetCurrentThreadId()
            attached = bool(user32.AttachThreadInput(current, thread, True)) if thread else False
            try:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.SetActiveWindow(hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(current, thread, False)
        except Exception:  # noqa: BLE001 - 置前失败只影响焦点，不影响功能
            logger.debug("敲敲窗口置前失败", exc_info=True)
