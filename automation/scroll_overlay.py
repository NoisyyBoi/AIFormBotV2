"""
Scroll inspection overlay.

Responsibilities:
  - Capture a full-screen screenshot.
  - Draw every ScrollCandidateInfo on it, color-coded by scroll capability.
  - Label each rectangle with its index, AutomationId, and ControlType.
  - Draw a legend explaining the color coding.
  - Save to debug/scrollable_controls_overlay.png.
  - Never raise — log errors and return.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab
from loguru import logger

from config.settings import SCROLLABLE_CONTROLS_OVERLAY_PNG
from automation.scroll_inspector import ScrollCandidateInfo


# ── Color scheme (BGR) ────────────────────────────────────────────────────────
# ScrollPattern present                   → cyan
_COLOR_SCROLL_PATTERN  = (255, 220,   0)   # cyan
# Has vertical scrollbar (no pattern)     → yellow
_COLOR_V_SCROLLBAR     = (  0, 220, 220)   # yellow
# Has horizontal scrollbar only           → magenta
_COLOR_H_SCROLLBAR     = (200,   0, 200)   # magenta
# No scroll capability (all others)       → grey — drawn thin, less prominent
_COLOR_NONE            = (100, 100, 100)
_THICK = 2
_THIN  = 1

_FONT       = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.32
_FONT_THICK = 1


# ── Helpers ───────────────────────────────────────────────────────────────────

def _grab_screen() -> np.ndarray:
    pil = ImageGrab.grab(all_screens=False)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def _color_and_thickness(c: ScrollCandidateInfo) -> tuple[tuple[int, int, int], int]:
    if c.has_scroll_pattern:
        return _COLOR_SCROLL_PATTERN, _THICK
    if c.has_vertical_scrollbar:
        return _COLOR_V_SCROLLBAR, _THICK
    if c.has_horizontal_scrollbar:
        return _COLOR_H_SCROLLBAR, _THICK
    return _COLOR_NONE, _THIN


def _label(c: ScrollCandidateInfo) -> str:
    aid = c.automation_id or "(no id)"
    return f"[{c.index}] {c.control_type} | {aid}"


def _draw_candidate(image: np.ndarray, c: ScrollCandidateInfo) -> None:
    """Draw one rectangle + label for *c* onto *image* in place."""
    if c.width <= 0 or c.height <= 0:
        return

    color, thickness = _color_and_thickness(c)
    cv2.rectangle(image, (c.left, c.top), (c.right, c.bottom), color, thickness)

    text  = _label(c)
    pos_y = max(c.top - 3, 10)

    # shadow for readability
    cv2.putText(image, text, (c.left + 2, pos_y + 1),
                _FONT, _FONT_SCALE, (0, 0, 0), _FONT_THICK + 1, cv2.LINE_AA)
    # foreground
    cv2.putText(image, text, (c.left + 2, pos_y),
                _FONT, _FONT_SCALE, color, _FONT_THICK, cv2.LINE_AA)


def _draw_legend(image: np.ndarray) -> None:
    """Draw a compact color legend in the top-left corner."""
    entries = [
        ("ScrollPattern",      _COLOR_SCROLL_PATTERN),
        ("Vertical scrollbar", _COLOR_V_SCROLLBAR),
        ("Horiz. scrollbar",   _COLOR_H_SCROLLBAR),
        ("No scroll cap.",     _COLOR_NONE),
    ]
    x0, y0, box_w, box_h, pad = 8, 8, 14, 12, 4
    for i, (label, color) in enumerate(entries):
        y = y0 + i * (box_h + pad)
        cv2.rectangle(image, (x0, y), (x0 + box_w, y + box_h), color, -1)
        cv2.putText(image, label,
                    (x0 + box_w + 4, y + box_h - 1),
                    _FONT, 0.33, (230, 230, 230), 1, cv2.LINE_AA)


# ── Public API ────────────────────────────────────────────────────────────────

def save_scroll_overlay(
    candidates: list[ScrollCandidateInfo],
    path: Path = SCROLLABLE_CONTROLS_OVERLAY_PNG,
) -> None:
    """
    Capture the screen, annotate every candidate, and save to *path*.

    All controls are drawn — non-scrollable ones in grey so they provide
    spatial context without distracting from the scrollable ones.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        image = _grab_screen()
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not capture screen for scroll overlay: {}", exc)
        return

    # Draw non-scrollable controls first (background layer)
    for c in candidates:
        if not (c.has_scroll_pattern or c.has_vertical_scrollbar or c.has_horizontal_scrollbar):
            _draw_candidate(image, c)

    # Draw scrollable controls on top (foreground layer)
    for c in candidates:
        if c.has_scroll_pattern or c.has_vertical_scrollbar or c.has_horizontal_scrollbar:
            _draw_candidate(image, c)

    _draw_legend(image)

    try:
        cv2.imwrite(str(path), image)
        logger.info(
            "Scroll overlay saved → {}  ({} total, {} scrollable)",
            path,
            len(candidates),
            sum(1 for c in candidates
                if c.has_scroll_pattern
                or c.has_vertical_scrollbar
                or c.has_horizontal_scrollbar),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not write scroll overlay to {}: {}", path, exc)
