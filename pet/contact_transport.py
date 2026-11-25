"""Main-thread, round-based contact exchange over user-local Qt sockets."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from time import monotonic
from typing import Callable
from uuid import uuid4

from PySide6.QtCore import QLockFile, QObject, QTimer, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_MAX_FRAME = 16 * 1024  # Includes the terminating newline.
_MAX_PENDING = 4 * _MAX_FRAME
_ROUND_MS = 250
_LOG = logging.getLogger(__name__)


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _encode(message: dict) -> bytes:
    data = json.dumps(message, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    if len(data) > _MAX_FRAME:
        raise ValueError("Contact frame too large")
    return data


class ContactBus(QObject):
    """Call start/stop and all callbacks on the owning Qt (GUI) thread.

    The directory must already exist. Only the election lock is written there;
    no configuration is loaded or changed. Call stop before destroying the owner.
    New connections participate in the next round, never in a partial snapshot.
    """

    def __init__(
        self,
        directory: Path,
        sample: Callable[[], dict],
        solve: Callable[[list[dict]], dict[str, dict]],
        apply: Callable[[dict], None],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        directory = Path(directory).resolve()
        project = Path(__file__).resolve().parent.parent
        identity = [os.path.normcase(str(p)) for p in (directory, project)]
        digest = hashlib.sha256(json.dumps(identity).encode("utf-8")).hexdigest()[:24]
        self.server_name = f"pet-contacts-{digest}"
        self._lock_path = directory / f"{self.server_name}.lock"
        self._lock = QLockFile(str(self._lock_path))
        self._lock.setStaleLockTime(0)  # Never evict a live, long-running leader.
        self._owns_lock = False
        self._stopped = True
        self._sample, self._solve, self._apply = sample, solve, apply
        self._frame = 0
        self._expected: tuple[QLocalSocket, ...] = ()
        self._states: dict[QLocalSocket, dict] = {}
        self._round_started = 0.0
        self._members: dict[QLocalSocket, str] = {}
        self._buffers: dict[QLocalSocket, bytearray] = {}
        self._sample_frame: int | None = None
        self._seen_frame = 0

        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._accept)
        self._client = QLocalSocket(self)
        self._client.setReadBufferSize(_MAX_FRAME)
        self._buffers[self._client] = bytearray()
        self._client.readyRead.connect(lambda: self._read(self._client))
        self._client.connected.connect(self._clear_client)
        self._client.disconnected.connect(self._clear_client)
        self._retry = QTimer(self)
        self._retry.setInterval(500)
        self._retry.timeout.connect(self._connect)
        self._tick = QTimer(self)
        self._tick.setInterval(16)
        self._tick.setTimerType(Qt.TimerType.PreciseTimer)
        self._tick.timeout.connect(self._begin_round)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.setInterval(_ROUND_MS)
        self._deadline.setTimerType(Qt.TimerType.PreciseTimer)
        self._deadline.timeout.connect(self._timeout)

    @property
    def is_leader(self) -> bool:
        return self._owns_lock and self._server.isListening()

    def start(self) -> None:
        if not self._stopped:
            return
        self._stopped = False
        self._retry.start()
        self._connect()

    def stop(self) -> None:
        self._stopped = True  # Disconnect callbacks must not restart anything.
        self._retry.stop()
        self._tick.stop()
        self._cancel_round()
        self._client.abort()
        self._clear_client()
        for socket in tuple(self._members):
            self._drop(socket)
        self._accept()  # Also dispose of connections still in the accept queue.
        self._server.close()
        if self._owns_lock:
            self._lock.unlock()
            self._owns_lock = False

    def _clear_client(self) -> None:
        self._buffers[self._client].clear()
        self._sample_frame = None
        self._seen_frame = 0

    def _connect(self) -> None:
        if self._stopped or self._client.state() == QLocalSocket.LocalSocketState.ConnectedState:
            return
        self._client.abort()  # Bound a pending asynchronous connect to one retry interval.
        self._clear_client()
        if not self.is_leader and self._lock.tryLock(0):
            self._owns_lock = True
            # Removing an endpoint is safe ONLY after winning the election lock.
            QLocalServer.removeServer(self.server_name)
            if self._server.listen(self.server_name):
                self._cancel_round()
                self._tick.start()
            else:
                self._lock.unlock()
                self._owns_lock = False
        self._client.connectToServer(self.server_name)

    def _accept(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if self._stopped:
                socket.abort()
                socket.deleteLater()
                continue
            socket.setReadBufferSize(_MAX_FRAME)
            self._members[socket] = uuid4().hex
            self._buffers[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._drop(s))
            socket.errorOccurred.connect(lambda _error, s=socket: self._drop(s))
            if socket.bytesAvailable():
                self._read(socket)

    def _drop(self, socket: QLocalSocket) -> None:
        if socket is self._client:
            socket.abort()
            self._clear_client()
        elif socket in self._members:
            del self._members[socket]
            self._buffers.pop(socket, None)
            self._cancel_round()
            socket.abort()
            socket.deleteLater()

    def _send(self, socket: QLocalSocket, message: dict) -> bool:
        try:
            data = _encode(message)
        except (ValueError, TypeError, RecursionError, OverflowError):
            self._drop(socket)
            return False
        if (socket.state() != QLocalSocket.LocalSocketState.ConnectedState
                or socket.bytesToWrite() + len(data) > _MAX_PENDING):
            self._drop(socket)
            return False
        if socket.write(data) != len(data):
            self._drop(socket)
            return False
        return True

    def _read(self, socket: QLocalSocket) -> None:
        while not self._stopped and socket in self._buffers and socket.bytesAvailable():
            buffer = self._buffers[socket]
            buffer.extend(bytes(socket.read(_MAX_FRAME - len(buffer))))
            while b"\n" in buffer:
                end = buffer.index(b"\n")
                line = bytes(buffer[:end])
                del buffer[:end + 1]
                try:
                    message = json.loads(line.decode("utf-8"), parse_constant=_reject_constant)
                    if not isinstance(message, dict):
                        raise ValueError("Expected an object")
                    frame = message.get("frame")
                    if type(frame) is not int or frame <= 0:
                        raise ValueError("Invalid frame number")
                    if socket is self._client:
                        self._client_message(message)
                    else:
                        self._state(socket, message)
                except (ValueError, TypeError, RecursionError, OverflowError):
                    self._drop(socket)
                    return
                if self._stopped or socket not in self._buffers or not socket.isOpen():
                    return
            if len(buffer) >= _MAX_FRAME:  # No space left even for a newline.
                self._drop(socket)
                return

    def _client_message(self, message: dict) -> None:
        frame = message["frame"]
        if message.get("type") == "sample":
            if frame <= self._seen_frame:
                return
            self._seen_frame = self._sample_frame = frame
            try:
                state = self._sample()
            except Exception:
                _LOG.exception("Contact sample callback failed")
                self._drop(self._client)
                return
            if not isinstance(state, dict):
                raise ValueError("Expected a state object")
            if not self._stopped and self._sample_frame == frame:
                self._send(self._client, {"type": "state", "frame": frame, "state": state})
        elif message.get("type") == "apply" and isinstance(message.get("change"), dict):
            if frame != self._sample_frame:
                return
            self._sample_frame = None  # Also discard duplicate applies.
            if message["change"]:
                try:
                    self._apply(message["change"])
                except Exception:
                    _LOG.exception("Contact apply callback failed")
        else:
            raise ValueError("Invalid server message")

    def _begin_round(self) -> None:
        if self._stopped or not self.is_leader or self._expected or not self._members:
            return
        self._frame += 1
        self._expected = tuple(self._members)
        self._states.clear()
        self._round_started = monotonic()
        self._deadline.start()
        for socket in self._expected:
            if not self._send(socket, {"type": "sample", "frame": self._frame}):
                break

    def _state(self, socket: QLocalSocket, message: dict) -> None:
        if message.get("type") != "state" or not isinstance(message.get("state"), dict):
            raise ValueError("Invalid client message")
        if (message["frame"] != self._frame or socket not in self._expected
                or socket in self._states):
            return
        if monotonic() - self._round_started >= _ROUND_MS / 1000:
            self._timeout()
            return
        state = dict(message["state"])
        state["runtime_id"] = self._members[socket]
        self._states[socket] = state
        if len(self._states) != len(self._expected):
            return
        frame, expected = self._frame, self._expected
        try:
            result = self._solve([self._states[s] for s in expected])
            if not isinstance(result, dict):
                raise ValueError("Expected a result object")
            replies = []
            for member in expected:
                change = result.get(self._members[member], {})
                if not isinstance(change, dict):
                    raise ValueError("Expected a change object")
                reply = {"type": "apply", "frame": frame, "change": change}
                _encode(reply)  # Validate the whole result before applying any of it.
                replies.append(reply)
        except Exception:
            _LOG.exception("Contact solve callback/result failed")
            self._cancel_round()
            return
        if self._stopped or self._frame != frame or self._expected != expected:
            return
        for member, reply in zip(expected, replies):
            if not self._send(member, reply):
                break
        self._cancel_round()

    def _cancel_round(self) -> None:
        self._deadline.stop()
        self._expected = ()
        self._states.clear()

    def _timeout(self) -> None:
        missing = [s for s in self._expected if s not in self._states]
        self._cancel_round()
        for socket in missing:
            self._drop(socket)
