"""
Wheel scroller — click-to-focus + mouse-wheel input.

Responsibilities:
  - Move the cursor to a given (x, y) screen coordinate.
  - Left-click to give the target pane keyboard/scroll focus.
  - Send a downward mouse-wheel event.
  - Primary method  : pyautogui.click() + pyautogui.scroll()
  - Automatic fallback: win32api.mouse_event(MOUSEEVENTF_WHEEL) when
    pyautogui.scroll() raises or produces no result (both are attempted
    and the fallback is always also executed so the pane receives two
    independent wheel signals for reliability).
  - Return a ScrollAttemptResult describing every detail of the attempt.
  - Never raise — catch all exceptions internally.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import time
from dataclasses import dataclass

import win32api
import win32con
from loguru import logger

from config.settings import SCROLL_CLICK_PAUSE_S, SCROLL_CLICKS_PER_STEP

# ── Try importing pyautogui — it may not be installed yet ────────────────────
try:
    import pyautogui
    _PYAUTOGUI_AVAILABLE = True
except ImportError:
    _PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui not found — wheel scroll will use win32 only.")


# ══════════════════════════════════════════════════════════════════════════════
# SendInput structure  (lower-level than mouse_event, preferred by modern apps)
# ══════════════════════════════════════════════════════════════════════════════

_INPUT_MOUSE    = 0
_WHEEL_DELTA    = 120   # one notch

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]
    _anonymous_ = ("_u",)
    _fields_    = [("type", ctypes.c_ulong), ("_u", _INPUT_UNION)]


def _send_wheel_input(clicks: int) -> bool:
    """
    Send a vertical wheel event via SendInput (most reliable on Windows 10/11).
    Returns True on success.
    """
    try:
        wheel_data = ctypes.c_ulong(-_WHEEL_DELTA * clicks & 0xFFFFFFFF)
        inp = _INPUT(
            type=_INPUT_MOUSE,
            _u=_INPUT._INPUT_UNION(
                mi=_MOUSEINPUT(
                    dx=0,
                    dy=0,
                    mouseData=wheel_data,
                    dwFlags=win32con.MOUSEEVENTF_WHEEL,
                    time=0,
                    dwExtraInfo=None,
                )
            ),
        )
        result = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        return result == 1
    except Exception as exc:  # noqa: BLE001
        logger.debug("SendInput wheel failed: {}", exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Data model
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ScrollAttemptResult:
    click_x: int
    click_y: int
    clicks: int
    pyautogui_used: bool
    pyautogui_ok: bool
    sendinput_used: bool
    sendinput_ok: bool
    win32_fallback_used: bool
    win32_fallback_ok: bool
    success: bool          # True = hash changed after this attempt
    hash_before: str
    hash_after: str


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def click_and_scroll(
    x: int,
    y: int,
    clicks: int = SCROLL_CLICKS_PER_STEP,
) -> dict:
    """
    Move to (x, y), left-click to focus, then send a downward wheel event.

    Wheel delivery sequence
    -----------------------
    1. pyautogui.scroll(-clicks)           — primary, works for most apps
    2. SendInput(MOUSEEVENTF_WHEEL)        — lower-level, works when pyautogui
                                             is swallowed by the message queue
    3. win32api.mouse_event(WHEEL)         — legacy fallback, always attempted

    All three are fired so the pane receives the maximum number of wheel
    signals possible from a single call.

    Returns a dict with fields matching ScrollAttemptResult for easy logging.
    """
    pyautogui_ok     = False
    sendinput_ok     = False
    win32_ok         = False

    # ── 1. Move cursor and left-click to focus ────────────────────────────────
    try:
        win32api.SetCursorPos((x, y))
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,   x, y, 0, 0)
        time.sleep(SCROLL_CLICK_PAUSE_S)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Click at ({},{}) failed: {}", x, y, exc)

    # ── 2. pyautogui scroll (primary) ────────────────────────────────────────
    if _PYAUTOGUI_AVAILABLE:
        try:
            pyautogui.scroll(-clicks, x=x, y=y)
            pyautogui_ok = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("pyautogui.scroll failed: {}", exc)

    # ── 3. SendInput wheel ────────────────────────────────────────────────────
    sendinput_ok = _send_wheel_input(clicks)

    # ── 4. win32api fallback ──────────────────────────────────────────────────
    try:
        delta = -(win32con.WHEEL_DELTA * clicks)
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, x, y, delta & 0xFFFF, 0)
        win32_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.debug("win32api.mouse_event wheel failed: {}", exc)

    result = {
        "click_x":            x,
        "click_y":            y,
        "clicks":             clicks,
        "pyautogui_used":     _PYAUTOGUI_AVAILABLE,
        "pyautogui_ok":       pyautogui_ok,
        "sendinput_used":     True,
        "sendinput_ok":       sendinput_ok,
        "win32_fallback_used": True,
        "win32_fallback_ok":  win32_ok,
    }

    logger.debug(
        "Wheel attempt at ({},{}): pyautogui={}/{}, SendInput={}, win32={}",
        x, y,
        _PYAUTOGUI_AVAILABLE, pyautogui_ok,
        sendinput_ok, win32_ok,
    )
    return result
