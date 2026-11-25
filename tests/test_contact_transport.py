"""Real local sockets only; every endpoint/lock is scoped to tmp_path."""

import itertools
import json
from pathlib import Path
import sys
from time import monotonic

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QLockFile, QProcess, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from pet import contact_transport as transport
from pet.contact_transport import ContactBus


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_until(predicate, timeout=5000):
    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(5)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(timeout)
    loop.exec()
    poll.stop()
    deadline.stop()
    assert predicate(), "Timed out waiting for local IPC"


def advance(milliseconds):
    end = monotonic() + milliseconds / 1000
    wait_until(lambda: monotonic() >= end, milliseconds + 2000)


def dispose(obj):
    obj.deleteLater()
    QCoreApplication.sendPostedEvents(obj, QEvent.Type.DeferredDelete)


class Node:
    def __init__(self, directory, label):
        self.state = {"label": label, "runtime_id": "forged", "x": 0, "y": 12,
                      "radius_x": 10, "radius_y": 15, "vx": 2, "vy": -1,
                      "mass": 3, "flags": {"dragging": False}, "scale": 1.25}
        self.samples = []
        self.rounds = []
        self.changes = []
        self.empty = False
        self.bus = ContactBus(directory, self.sample, self.solve, self.apply)

    def sample(self):
        self.samples.append(dict(self.state))
        return dict(self.state)

    def solve(self, states):
        self.rounds.append((self.bus._frame, states))
        if self.empty:
            return {}
        return {s["runtime_id"]: {"x": s["x"] + 1, "for": s["label"]} for s in states}

    def apply(self, change):
        self.changes.append(change)
        self.state["x"] = change["x"]


@pytest.fixture
def nodes(app, tmp_path):
    created = []

    def create(label="A", directory=None):
        node = Node(tmp_path if directory is None else directory, label)
        created.append(node)
        return node

    yield create
    for node in reversed(created):
        node.bus.stop()
    for node in created:
        dispose(node.bus)


@pytest.fixture
def wires(nodes):
    sockets = []

    def connect(bus):
        socket = QLocalSocket()
        sockets.append(socket)
        socket.connectToServer(bus.server_name)
        wait_until(lambda: socket.state() == QLocalSocket.LocalSocketState.ConnectedState)
        return socket

    yield connect
    for socket in sockets:
        socket.abort()
        dispose(socket)


def read_message(socket):
    wait_until(socket.canReadLine)
    return json.loads(bytes(socket.readLine()))


def send(socket, message):
    data = json.dumps(message, separators=(",", ":")).encode() + b"\n"
    assert socket.write(data) == len(data)


@pytest.mark.parametrize("order", list(itertools.permutations("ABC")))
def test_start_orders_state_exchange_and_apply_before_next_sample(nodes, order):
    pets = {label: nodes(label) for label in "ABC"}
    for label in order:
        pets[label].bus.start()
        pets[label].bus.start()
        wait_until(lambda: len(pets[label].changes) >= 2)
    leader = pets[order[0]]
    wait_until(lambda: sum(len(states) == 3 for _, states in leader.rounds) >= 5)
    assert [p.bus.is_leader for p in pets.values()].count(True) == 1
    states = next(states for _, states in reversed(leader.rounds) if len(states) == 3)
    assert {s["label"] for s in states} == set("ABC")
    assert len({s["runtime_id"] for s in states}) == 3
    assert all(s["runtime_id"] != "forged" and s["scale"] == 1.25 for s in states)
    frames = [frame for frame, _ in leader.rounds]
    assert frames == sorted(set(frames))  # At most one solve per round.
    for label, pet in pets.items():
        assert all(change["for"] == label for change in pet.changes)
        assert [s["x"] for s in pet.samples] == list(range(len(pet.samples)))
        assert [c["x"] for c in pet.changes] == list(range(1, len(pet.changes) + 1))
        if pet is not leader:
            assert not pet.rounds


def test_leader_exit_re_election_restart_and_idempotent_stop(nodes, tmp_path):
    pets = [nodes(label) for label in "CAB"]
    for pet in pets:
        pet.bus.start()
    wait_until(lambda: all(len(p.changes) >= 3 for p in pets))
    leader = next(p for p in pets if p.bus.is_leader)
    remaining = [p for p in pets if p is not leader]
    before = [len(p.changes) for p in remaining]
    leader.bus.stop()
    leader.bus.stop()
    wait_until(lambda: sum(p.bus.is_leader for p in remaining) == 1
               and all(len(p.changes) > n + 2 for p, n in zip(remaining, before)))
    winner = next(p for p in remaining if p.bus.is_leader)
    assert all(len(states) == 2 for _, states in winner.rounds)
    assert not leader.bus._retry.isActive()
    assert not leader.bus._tick.isActive()
    assert not leader.bus._deadline.isActive()
    probe = QLockFile(str(leader.bus._lock_path))
    probe.setStaleLockTime(0)
    assert not probe.tryLock(0)  # Repeated follower/old-leader stop cannot unlock the winner.
    leader.bus.start()
    wait_until(lambda: any(len(states) == 3 for _, states in winner.rounds))
    assert not leader.bus.is_leader
    for pet in pets:
        pet.bus.stop()
        pet.bus.stop()
    advance(600)
    assert not list(tmp_path.glob("pet-contacts-*.lock"))
    assert not any(p.bus.is_leader or p.bus._retry.isActive() for p in pets)


def test_canonical_directory_and_installation_isolation(nodes, tmp_path, monkeypatch):
    config = tmp_path / "existing.json"
    config.write_bytes(b'{"untouched": true}\n')
    other = tmp_path / "other"
    other.mkdir()
    a = nodes("A")
    b = nodes("B", tmp_path / "not-created" / "..")
    c = nodes("C", other)
    with monkeypatch.context() as patch:
        patch.setattr(transport, "__file__", str(tmp_path / "other-install" / "pet" / "contact_transport.py"))
        d = nodes("D")
    assert a.bus.server_name == b.bus.server_name
    assert len({a.bus.server_name, c.bus.server_name, d.bus.server_name}) == 3
    assert len(a.bus.server_name) < 50
    for pet in (a, b, c, d):
        pet.bus.start()
    wait_until(lambda: all(len(p.changes) >= 3 for p in (a, b, c, d)))
    assert sum(p.bus.is_leader for p in (a, b, c, d)) == 3
    assert any({s["label"] for s in states} == {"A", "B"} for _, states in a.rounds)
    assert all(len(states) == 1 for p in (c, d) for _, states in p.rounds)
    assert config.read_bytes() == b'{"untouched": true}\n'
    assert {p.name for p in tmp_path.iterdir()} == {
        "existing.json", "other", a.bus._lock_path.name, d.bus._lock_path.name,
    }
    assert a.bus._server.socketOptions() & QLocalServer.SocketOption.UserAccessOption
    for pet in (a, b, c, d):
        pet.bus.stop()
    assert list(other.iterdir()) == []
    assert {p.name for p in tmp_path.iterdir()} == {"existing.json", "other"}


def test_solo_is_timer_paced_and_empty_change_skips_apply(nodes):
    pet = nodes()
    pet.empty = True
    pet.bus.start()
    wait_until(lambda: len(pet.rounds) >= 3)
    before = len(pet.rounds)
    advance(120)
    assert 1 <= len(pet.rounds) - before <= 12
    assert all(len(states) == 1 for _, states in pet.rounds)
    assert not pet.changes
    assert pet.bus._client.readBufferSize() == transport._MAX_FRAME
    assert len(pet.bus._members) == 1  # The leader participates through its own socket.


def test_slow_member_cancels_round_then_healthy_nodes_resume(nodes, wires):
    a, b = nodes("A"), nodes("B")
    a.bus.start()
    b.bus.start()
    wait_until(lambda: len(b.changes) >= 3)
    slow = wires(a.bus)
    frame = read_message(slow)["frame"]
    wait_until(lambda: len(a.bus._states) == 2)
    assert len(a.bus._expected) == 3
    assert not any(n == frame for n, _ in a.rounds)
    before = len(b.changes)
    wait_until(lambda: slow.state() == QLocalSocket.LocalSocketState.UnconnectedState, 3000)
    wait_until(lambda: len(b.changes) >= before + 3)
    assert not any(n == frame for n, _ in a.rounds)
    assert len(a.bus._members) == 2


def test_join_uses_next_snapshot_and_disconnect_discards_partial_round(nodes, wires):
    a = nodes("A")
    a.bus.start()
    wait_until(lambda: len(a.changes) >= 2)
    raw = wires(a.bus)
    frame = read_message(raw)["frame"]
    wait_until(lambda: len(a.bus._states) == 1)
    expected = a.bus._expected
    b = nodes("B")
    b.bus.start()
    wait_until(lambda: len(a.bus._members) == 3)
    assert a.bus._expected == expected
    send(raw, {"type": "state", "frame": frame, "state": {"label": "raw", "x": 0}})
    wait_until(lambda: any(n == frame for n, _ in a.rounds))
    assert len(next(states for n, states in a.rounds if n == frame)) == 2
    assert read_message(raw)["type"] == "apply"
    next_frame = read_message(raw)["frame"]
    wait_until(lambda: len(a.bus._states) == 2)
    raw.abort()
    wait_until(lambda: len(b.changes) >= 2)
    assert not any(n == next_frame for n, _ in a.rounds)


@pytest.mark.parametrize("bad", [
    b"not-json\n", b"[]\n", b"null\n", b"\xff\n",
    b'{"type":"state","frame":true,"state":{}}\n',
    b'{"type":"state","frame":1,"state":[]}\n',
    b'{"type":"state","frame":1,"state":{"x":NaN}}\n',
    b'{"type":"unexpected","frame":1}\n',
    b"[" * 1500 + b"]" * 1500 + b"\n",
    b"x" * transport._MAX_FRAME,
    b"x" * transport._MAX_FRAME + b"\n",
])
def test_bad_or_overlong_frame_drops_only_offender(nodes, wires, bad):
    a, b = nodes("A"), nodes("B")
    a.bus.start()
    b.bus.start()
    wait_until(lambda: len(b.changes) >= 2)
    raw = wires(a.bus)
    read_message(raw)
    a.bus._deadline.stop()  # Disconnect must be validation, not the slow-member timer.
    before = len(b.changes)
    assert raw.write(bad) == len(bad)
    wait_until(lambda: raw.state() == QLocalSocket.LocalSocketState.UnconnectedState)
    wait_until(lambda: len(b.changes) >= before + 2)
    assert a.bus.is_leader and len(a.bus._members) == 2


def test_fragmented_exact_limit_frame_and_duplicate_state(nodes, wires):
    a = nodes()
    a.bus.start()
    wait_until(lambda: len(a.changes) >= 2)
    raw = wires(a.bus)
    frame = read_message(raw)["frame"]
    message = {"type": "state", "frame": frame, "state": {"label": "raw", "x": 0, "padding": ""}}
    base = json.dumps(message, separators=(",", ":")).encode() + b"\n"
    message["state"]["padding"] = "x" * (transport._MAX_FRAME - len(base))
    data = json.dumps(message, separators=(",", ":")).encode() + b"\n"
    assert len(data) == transport._MAX_FRAME
    raw.write(data[:50])
    wait_until(lambda: any(len(buf) == 50 for sock, buf in a.bus._buffers.items() if sock is not a.bus._client))
    assert not any(n == frame for n, _ in a.rounds)
    raw.write(data[50:] + data)
    assert read_message(raw)["type"] == "apply"
    assert sum(n == frame for n, _ in a.rounds) == 1
    assert raw.state() == QLocalSocket.LocalSocketState.ConnectedState


def test_client_rejects_stale_and_duplicate_apply_over_real_socket(nodes):
    pet = nodes()
    lock = QLockFile(str(pet.bus._lock_path))
    assert lock.tryLock(0)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    peer = None
    try:
        assert server.listen(pet.bus.server_name)
        pet.bus.start()
        wait_until(server.hasPendingConnections)
        peer = server.nextPendingConnection()
        send(peer, {"type": "sample", "frame": 10})
        assert read_message(peer)["frame"] == 10
        for frame, x in ((9, 90), (11, 110), (10, 1), (10, 99)):
            send(peer, {"type": "apply", "frame": frame, "change": {"x": x}})
        send(peer, {"type": "sample", "frame": 11})
        send(peer, {"type": "sample", "frame": 11})
        state = read_message(peer)
        assert state["state"]["x"] == 1
        assert pet.changes == [{"x": 1}]
        assert len(pet.samples) == 2
        assert not pet.bus.is_leader
        peer.write(b"[]\n")
        wait_until(lambda: pet.bus._client.state() == QLocalSocket.LocalSocketState.UnconnectedState)
        assert not pet.bus._buffers[pet.bus._client]
    finally:
        pet.bus.stop()
        if peer is not None:
            peer.abort()
        server.close()
        dispose(server)
        lock.unlock()


def test_write_queue_is_bounded_and_oversized_sample_is_contained(nodes):
    a, b = nodes("A"), nodes("B")
    a.bus.start()
    b.bus.start()
    wait_until(lambda: len(b.changes) >= 2)
    socket = b.bus._client
    message = {"type": "state", "frame": 1, "state": {"padding": "x" * 15000}}
    for _ in range(1000):  # Do not pump events: deliberately create write backpressure.
        sent = b.bus._send(socket, message)
        assert socket.bytesToWrite() <= transport._MAX_PENDING
        if not sent:
            break
    else:
        pytest.fail("Write queue never hit its bound")
    assert socket.state() == QLocalSocket.LocalSocketState.UnconnectedState
    oversized_samples = []

    def oversized_sample():
        oversized_samples.append(True)
        return {"padding": "x" * transport._MAX_FRAME}

    b.bus._sample = oversized_sample
    before = len(a.changes)
    wait_until(lambda: len(a.changes) >= before + 3)
    wait_until(lambda: bool(oversized_samples))
    wait_until(lambda: len(a.bus._members) == 1)
    b.bus._sample = b.sample
    wait_until(lambda: len(b.changes) >= 4)


@pytest.mark.parametrize("callback", ["sample", "solve", "apply"])
def test_callback_failure_does_not_escape_qt_or_stop_other_nodes(nodes, callback):
    a, b = nodes("A"), nodes("B")
    a.bus.start()
    b.bus.start()
    wait_until(lambda: len(b.changes) >= 2)
    target = b if callback in ("sample", "apply") else a
    failures = []

    def fail(*args):
        failures.append(True)
        raise RuntimeError("intentional test failure")

    setattr(target.bus, "_" + callback, fail)
    wait_until(lambda: bool(failures))
    setattr(target.bus, "_" + callback, getattr(target, callback))
    before = len(b.changes)
    wait_until(lambda: len(b.changes) > before + 2)
    assert a.bus.is_leader


_WORKER = r'''
import json, sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QTimer
from pet.contact_transport import ContactBus
app = QCoreApplication([])
label = sys.argv[2]
status = {"x": 0, "applied": 0, "peers": []}
def sample():
    return {"label": label, "x": status["x"], "runtime_id": "forged"}
def solve(states):
    peers = sorted(s["label"] for s in states)
    return {s["runtime_id"]: {"x": s["x"] + 1, "peers": peers} for s in states}
def apply(change):
    status.update(change)
    status["applied"] += 1
bus = ContactBus(Path(sys.argv[1]), sample, solve, apply)
bus.start()
timer = QTimer()
timer.setInterval(80)
timer.timeout.connect(lambda: print(json.dumps(dict(status, leader=bus.is_leader)), flush=True))
timer.start()
app.aboutToQuit.connect(bus.stop)
app.exec()
'''


def test_three_independent_processes_and_crashed_leader_takeover(app, tmp_path):
    processes = {}
    statuses = {}
    pending = {}
    project = Path(transport.__file__).resolve().parent.parent

    def collect(label):
        process = processes[label]
        pending[label] += bytes(process.readAllStandardOutput())
        while b"\n" in pending[label]:
            line, pending[label] = pending[label].split(b"\n", 1)
            statuses[label] = json.loads(line)

    try:
        for label in "BCA":
            process = QProcess()
            processes[label] = process
            pending[label] = b""
            process.setWorkingDirectory(str(project))
            process.readyReadStandardOutput.connect(lambda label=label: collect(label))
            process.start(sys.executable, ["-B", "-u", "-c", _WORKER, str(tmp_path), label])
            wait_until(lambda: label in statuses, 10000)
        wait_until(lambda: all(s["peers"] == list("ABC") and s["applied"] >= 3
                               for s in statuses.values()), 10000)
        assert sum(s["leader"] for s in statuses.values()) == 1
        leader = next(label for label, s in statuses.items() if s["leader"])
        assert leader == "B"
        processes[leader].kill()  # Exercise dead-PID QLockFile recovery, not only clean stop.
        wait_until(lambda: processes[leader].state() == QProcess.ProcessState.NotRunning)
        alive = sorted(set(processes) - {leader})
        baseline = {label: statuses[label]["applied"] for label in alive}
        wait_until(lambda: sum(statuses[label]["leader"] for label in alive) == 1
                   and all(statuses[label]["peers"] == alive
                           and statuses[label]["applied"] > baseline[label] + 2
                           for label in alive), 10000)
        assert all(processes[label].state() == QProcess.ProcessState.Running for label in alive)
        assert all(p.name.startswith("pet-contacts-") and p.suffix == ".lock" for p in tmp_path.iterdir())
    finally:
        for process in processes.values():
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
        for process in processes.values():
            wait_until(lambda p=process: p.state() == QProcess.ProcessState.NotRunning)
            errors = bytes(process.readAllStandardError()).decode(errors="replace")
            dispose(process)
            assert not errors, errors
        for path in tmp_path.glob("pet-contacts-*.lock"):
            lock = QLockFile(str(path))
            lock.setStaleLockTime(0)
            assert lock.tryLock(0)
            lock.unlock()
