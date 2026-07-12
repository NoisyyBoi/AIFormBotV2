"""
Window discovery and foreground management.

Responsibilities:
  - Find the target application window by partial title match.
  - Bring it to the foreground.
  - Return the pywinauto Application wrapper for further inspection.
"""

import time
from typing import Optional

import uiautomation as auto
from loguru import logger

from config.settings import (
    APP_TITLE_SUBSTRING,
    WINDOW_FIND_TIMEOUT_S,
    WINDOW_FIND_INTERVAL_S,
)


def _find_window_control(title_substring: str) -> Optional[auto.WindowControl]:
    """Return the first WindowControl whose title contains *title_substring*."""
    desktop = auto.GetRootControl()
    for child in desktop.GetChildren():
        if title_substring.lower() in (child.Name or "").lower():
            return child  # type: ignore[return-value]
    return None


def wait_for_window(title_substring: str = APP_TITLE_SUBSTRING) -> auto.WindowControl:
    """
    Poll until the target window appears or the timeout expires.

    Returns the WindowControl on success.
    Raises RuntimeError if the window is not found in time.
    """
    deadline = time.monotonic() + WINDOW_FIND_TIMEOUT_S
    logger.debug(
        "Searching for window containing '{}' (timeout={}s)",
        title_substring,
        WINDOW_FIND_TIMEOUT_S,
    )

    while time.monotonic() < deadline:
        window = _find_window_control(title_substring)
        if window is not None:
            logger.info("Found window: '{}'", window.Name)
            return window
        time.sleep(WINDOW_FIND_INTERVAL_S)

    raise RuntimeError(
        f"Window containing '{title_substring}' not found "
        f"within {WINDOW_FIND_TIMEOUT_S}s."
    )


def bring_to_foreground(window: auto.WindowControl) -> None:
    """
    Set focus and bring *window* to the foreground.
    Logs a warning if the operation cannot be confirmed.
    """
    logger.debug("Bringing window '{}' to foreground.", window.Name)
    try:
        window.SetFocus()
        # Give the OS a moment to honour the request
        time.sleep(0.3)
        logger.info("Window '{}' is now in the foreground.", window.Name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SetFocus raised an exception (non-fatal): {}", exc)
