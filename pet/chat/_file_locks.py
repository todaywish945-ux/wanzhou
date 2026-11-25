# -*- coding: utf-8 -*-
"""会话/记忆文件的进程内锁与跨进程锁文件辅助。

从参考项目 pet/proactive/memory.py 摘出的 5 个锁辅助符号（chat.memory 依赖），
proactive 子系统裁剪后在此独立存活。语义与原实现逐位一致。
"""
from __future__ import annotations

import os
import threading
import weakref
from pathlib import Path

DEFAULT_LOCK_TIMEOUT_MS = 1000

_LOCKS: weakref.WeakValueDictionary[str, threading.RLock] = weakref.WeakValueDictionary()
_LOCKS_GUARD = threading.Lock()

_IO_LOCKS: weakref.WeakValueDictionary[str, threading.Lock] = weakref.WeakValueDictionary()
_IO_LOCKS_GUARD = threading.Lock()


def _resolved(path: Path | str) -> Path:
    """归一化存储路径：锁键与锁文件路径都按它算。"""
    return Path(os.path.realpath(str(path)))


def _lock_key(path: Path | str) -> str:
    """进程内锁表键：再叠一层 normcase，保证同一文件只有一把进程内锁。"""
    return os.path.normcase(str(_resolved(path)))


def _lock_for(path: Path | str) -> threading.RLock:
    """返回该存储路径在本进程内共享的可重入锁。"""
    key = _lock_key(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


def _io_lock_for(path: Path | str) -> threading.Lock:
    """返回该存储路径在本进程内共享的本地 I/O 窄锁（非重入）。"""
    key = _lock_key(path)
    with _IO_LOCKS_GUARD:
        lock = _IO_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _IO_LOCKS[key] = lock
        return lock


def lock_path_for(path: Path | str) -> Path:
    """跨进程锁文件路径：数据文件的旁路文件。"""
    resolved = _resolved(path)
    return resolved.with_name(resolved.name + ".lock")
