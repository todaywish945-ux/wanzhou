import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys

import psutil


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def is_pet_command(command, cwd, project_root=PROJECT_ROOT):
    if not command or not cwd:
        return False
    root = os.path.normcase(os.path.abspath(project_root))
    executables = {
        os.path.normcase(str(project_root / "venv" / "Scripts" / name))
        for name in ("python.exe", "pythonw.exe")
    }
    if os.path.normcase(command[0]) not in executables:
        return False
    if os.path.normcase(os.path.abspath(cwd)) != root:
        return False
    rest = command[1:]
    # slot 0 是「主宠页」进程（不带 --instance/--character），也由本项目启动，
    # 以前只认 slot 1/2/3 的三只 A/B/C，把它漏掉了——用户点「全部退出」后
    # 桌面上就还剩这一只。cwd + 解释器白名单已经保证不会误伤别的项目。
    if rest == ["-m", "pet", "--slot", "0"]:
        return True
    return any(
        rest == [
            "-m", "pet", "--slot", str(slot), "--instance", character,
            "--character", character,
        ]
        for slot, character in enumerate("ABC", start=1)
    )


def find_pet_processes():
    targets = []
    for process in psutil.process_iter(["cmdline"]):
        try:
            command = process.info["cmdline"]
            if command and is_pet_command(command, process.cwd()):
                targets.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return targets


def post_quit_messages(processes):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    targets = {process.pid: process for process in processes}
    windows = []

    @callback_type
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in targets:
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, len(class_name))
            if class_name.value.startswith("Qt"):
                windows.append((hwnd, pid.value, thread_id))
        return True

    if not user32.EnumWindows(visit, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    sent = set()
    for hwnd, pid, thread_id in windows:
        if thread_id in sent or not targets[pid].is_running():
            continue
        current_pid = wintypes.DWORD()
        current_thread = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(current_pid))
        if current_pid.value != pid or current_thread != thread_id:
            continue
        # WM_CLOSE 只关宠物窗口；WM_QUIT 才会触发 QApplication 的退出清理。
        if user32.PostThreadMessageW(thread_id, 0x0012, 0, 0):
            sent.add(thread_id)


def main():
    if sys.platform != "win32":
        print("This launcher requires Windows.")
        return 1
    processes = find_pet_processes()
    if not processes:
        print("No A/B/C pets from this project are running.")
        return 0
    post_quit_messages(processes)
    _, alive = psutil.wait_procs(processes, timeout=10)
    if alive:
        print("Some pets did not exit. Close any open dialogs, then try again.")
        print("No processes were forcibly terminated.")
        return 1
    print("All A/B/C pets from this project have exited.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
