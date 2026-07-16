"""
Mouse movement logger — instrumentation only, no behaviour.

Provides log_move(x, y) which emits a sequentially numbered log line
showing the call site (file + line), timestamp, and destination coordinates.

Usage:
    from automation.mouse_logger import log_move
    log_move(x, y)          # call IMMEDIATELY before any cursor-moving API

Thread-safe: uses a threading.Lock to protect the global counter.
"""

from __future__ import annotations

import inspect
import threading
import time

from loguru import logger

_lock: threading.Lock = threading.Lock()
_counter: int = 0


def log_move(x: int, y: int) -> None:
    """
    Emit one MOVE log line with a global sequence number, timestamp,
    caller location, and destination coordinates.

    Call this immediately before every API that moves the cursor:
        win32api.SetCursorPos, pyautogui.moveTo, pyautogui.click,
        pyautogui.scroll, mouse_event(LEFTDOWN/UP), SendInput, etc.
    """
    global _counter

    with _lock:
        _counter += 1
        seq = _counter

    # Inspect the call stack one frame up (the actual mouse-moving call site).
    frame = inspect.stack()[1]
    src_file = frame.filename.replace("\\", "/").split("/")[-1]
    src_line = frame.lineno
    ts = time.strftime("%H:%M:%S", time.localtime())

    logger.debug(
        "MOVE #{seq}  [{ts}]  {file}:{line}  → ({x}, {y})",
        seq=seq,
        ts=ts,
        file=src_file,
        line=src_line,
        x=x,
        y=y,
    )
