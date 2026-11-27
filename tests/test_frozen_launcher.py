# -*- coding: utf-8 -*-
"""冻结启动器：双击一次 exe 要起三个独立桌宠进程。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_launcher_spawns_three_roles(tmp_path):
    env = dict(os.environ)
    env["PET_LAUNCHER_DRY_RUN"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(ROOT)
    for entry in ("packaging/pet_entry.py", "packaging/pet_entry_no_chat.py"):
        completed = subprocess.run(
            [sys.executable, str(ROOT / entry)],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        commands = [json.loads(line) for line in completed.stdout.strip().splitlines()]
        assert len(commands) == 3
        assert [cmd[cmd.index("--slot") + 1] for cmd in commands] == ["1", "2", "3"]
        assert [cmd[cmd.index("--instance") + 1] for cmd in commands] == ["A", "B", "C"]
        assert [cmd[cmd.index("--character") + 1] for cmd in commands] == ["A", "B", "C"]


def test_launch_all_flag_spawns_three_roles(tmp_path):
    """开机自启写的 --launch-all 必须和双击 exe（无参数）一样起三只。"""
    env = dict(os.environ)
    env["PET_LAUNCHER_DRY_RUN"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [sys.executable, "-m", "pet", "--launch-all"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    commands = [json.loads(line) for line in completed.stdout.strip().splitlines()]
    assert len(commands) == 3
    assert [cmd[cmd.index("--slot") + 1] for cmd in commands] == ["1", "2", "3"]
