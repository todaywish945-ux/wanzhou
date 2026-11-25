import os
import subprocess
import sys
from types import SimpleNamespace

import psutil
import pytest

from pet import quit_all


def pet_command(root, character="A"):
    return [
        str(root / "venv" / "Scripts" / "pythonw.exe"),
        "-m", "pet", "--slot", str("ABC".index(character) + 1),
        "--instance", character, "--character", character,
    ]


@pytest.mark.parametrize("character", list("ABC"))
@pytest.mark.parametrize("executable", ["python.exe", "pythonw.exe"])
def test_matches_only_project_pet_launchers(tmp_path, character, executable):
    command = pet_command(tmp_path, character)
    command[0] = str(tmp_path / "venv" / "Scripts" / executable)
    assert quit_all.is_pet_command(command, str(tmp_path), tmp_path)


def test_matches_slot_zero_main_pet(tmp_path):
    """slot 0 主宠进程也得退出：它同样由本项目启动，只是没有角色参数。"""
    command = [str(tmp_path / "venv" / "Scripts" / "pythonw.exe"),
               "-m", "pet", "--slot", "0"]
    assert quit_all.is_pet_command(command, str(tmp_path), tmp_path)


def test_slot_zero_from_another_project_is_not_ours(tmp_path):
    """别的项目也用 `-m pet --slot 0`：cwd 不同就不能碰。"""
    command = [str(tmp_path / "venv" / "Scripts" / "pythonw.exe"),
               "-m", "pet", "--slot", "0"]
    assert not quit_all.is_pet_command(
        command, str(tmp_path / "another-project"), tmp_path)


@pytest.mark.parametrize("change", [
    "cwd", "executable", "module", "slot", "instance", "character",
    "settings", "empty", "incomplete",
])
def test_rejects_other_programs(tmp_path, change):
    command = pet_command(tmp_path)
    cwd = str(tmp_path)
    if change == "cwd":
        cwd = str(tmp_path / "another-project")
    elif change == "executable":
        command[0] = str(tmp_path / "pythonw.exe")
    elif change == "module":
        command[2] = "other_app"
    elif change == "slot":
        command[4] = "4"
    elif change == "instance":
        command[6] = "D"
    elif change == "character":
        command[8] = "D"
    elif change == "settings":
        command.append("--settings")
    elif change == "empty":
        command = []
    else:
        command = command[:-1]
    assert not quit_all.is_pet_command(command, cwd, tmp_path)


def test_scan_tolerates_processes_disappearing_or_inaccessible(monkeypatch):
    def inaccessible():
        raise psutil.AccessDenied(123)

    def gone():
        raise psutil.NoSuchProcess(456)

    command = pet_command(quit_all.PROJECT_ROOT)
    target = SimpleNamespace(info={"cmdline": command}, cwd=lambda: str(quit_all.PROJECT_ROOT))
    other = SimpleNamespace(info={"cmdline": [sys.executable, "-m", "other_app"]}, cwd=target.cwd)
    processes = [
        SimpleNamespace(info={"cmdline": command}, cwd=inaccessible),
        SimpleNamespace(info={"cmdline": command}, cwd=gone),
        other, target,
    ]
    monkeypatch.setattr(quit_all.psutil, "process_iter", lambda attrs: processes)
    assert quit_all.find_pet_processes() == [target]


def test_no_pets_is_success(monkeypatch, capsys):
    monkeypatch.setattr(quit_all.sys, "platform", "win32")
    monkeypatch.setattr(quit_all, "find_pet_processes", lambda: [])
    assert quit_all.main() == 0
    assert "No A/B/C pets" in capsys.readouterr().out


def test_unresponsive_pets_are_not_forcibly_terminated(monkeypatch, capsys):
    target = SimpleNamespace(pid=123)
    monkeypatch.setattr(quit_all.sys, "platform", "win32")
    monkeypatch.setattr(quit_all, "find_pet_processes", lambda: [target])
    monkeypatch.setattr(quit_all, "post_quit_messages", lambda processes: None)
    monkeypatch.setattr(quit_all.psutil, "wait_procs", lambda processes, timeout: ([], processes))
    assert quit_all.main() == 1
    assert "No processes were forcibly terminated" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native messages")
@pytest.mark.parametrize("hidden", [False, True])
def test_native_quit_cleans_up_three_apps_and_leaves_other_app_running(monkeypatch, hidden):
    code = '''
import os
import sys
from pet.qt_plugin_sanitizer import sanitize_plugin_path
sanitize_plugin_path()
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
window = QWidget()
window.setWindowTitle("Quit-all verification")
window.resize(220, 80)
window.show()
if sys.argv[1] == "hidden":
    window.hide()
app.aboutToQuit.connect(lambda: print("CLEANUP_OK", flush=True))
QTimer.singleShot(100, lambda: print(os.getpid(), flush=True))
QTimer.singleShot(20000, app.quit)
raise SystemExit(app.exec())
'''
    env = dict(os.environ, QT_QPA_PLATFORM="windows")
    children = []
    targets = []
    try:
        for _ in range(4):
            child = subprocess.Popen(
                [sys.executable, "-u", "-c", code, "hidden" if hidden else "visible"],
                cwd=quit_all.PROJECT_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            children.append(child)
            pid = int(child.stdout.readline().strip())
            targets.append(psutil.Process(pid))
        selected = targets[:3]
        for child in children[:3]:
            if child.pid not in {process.pid for process in selected}:
                selected.append(psutil.Process(child.pid))
        monkeypatch.setattr(quit_all, "find_pet_processes", lambda: selected)
        assert quit_all.main() == 0
        for child in children[:3]:
            out, err = child.communicate(timeout=5)
            assert child.returncode == 0, err
            assert "CLEANUP_OK" in out
        assert children[3].poll() is None
        assert targets[3].is_running()
        assert quit_all.main() == 0
        quit_all.post_quit_messages([targets[3]])
        out, err = children[3].communicate(timeout=5)
        assert children[3].returncode == 0, err
        assert "CLEANUP_OK" in out
    finally:
        for child in children:
            child.communicate(timeout=25)
