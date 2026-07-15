"""
Scroll Inspector — diagnostic phase.

Responsibilities:
  - Walk every descendant of the root panel using the live uiautomation tree
    (NOT the already-snapshotted ControlInfo tree) so that UIA patterns such
    as ScrollPattern are accessible.
  - For every control, record:
      * AutomationId, Name, ControlType, ClassName
      * BoundingRectangle
      * Whether the control supports ScrollPattern (has_scroll_pattern)
      * Whether it has a vertical scrollbar child (has_vertical_scrollbar)
      * Whether it has a horizontal scrollbar child (has_horizontal_scrollbar)
      * Current vertical / horizontal scroll percentages (if available)
      * depth in the live tree
  - Export the full list to debug/scrollable_controls.json.
  - Log every control at DEBUG level and a summary at INFO level.
  - Never scroll, never click, never modify anything.
  - Never raise — log errors per-control and continue.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import uiautomation as auto
from loguru import logger

from config.settings import MAX_TREE_DEPTH, SCROLLABLE_CONTROLS_JSON


# ══════════════════════════════════════════════════════════════════════════════
# Data model
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ScrollCandidateInfo:
    index: int                       # sequential index in the flat list
    depth: int
    automation_id: str
    name: str
    control_type: str
    class_name: str
    # bounding rect
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int
    # scroll capability
    has_scroll_pattern: bool
    has_vertical_scrollbar: bool
    has_horizontal_scrollbar: bool
    vertical_scroll_percent: Optional[float]    # 0–100 or None
    horizontal_scroll_percent: Optional[float]  # 0–100 or None
    vertical_view_size: Optional[float]         # % of content visible
    horizontal_view_size: Optional[float]


# ══════════════════════════════════════════════════════════════════════════════
# ScrollPattern probe
# ══════════════════════════════════════════════════════════════════════════════

def _probe_scroll_pattern(
    control: auto.Control,
) -> tuple[bool, Optional[float], Optional[float], Optional[float], Optional[float]]:
    """
    Attempt to read the ScrollPattern on *control*.

    Returns:
      (has_pattern,
       vertical_scroll_percent, horizontal_scroll_percent,
       vertical_view_size,      horizontal_view_size)

    All numeric values are None when not available.
    """
    try:
        pattern = control.GetPattern(auto.PatternId.ScrollPattern)
        if pattern is None:
            return False, None, None, None, None

        v_pct  = _safe_float(lambda: pattern.VerticalScrollPercent)
        h_pct  = _safe_float(lambda: pattern.HorizontalScrollPercent)
        v_view = _safe_float(lambda: pattern.VerticalViewSize)
        h_view = _safe_float(lambda: pattern.HorizontalViewSize)
        return True, v_pct, h_pct, v_view, h_view

    except Exception as exc:  # noqa: BLE001
        logger.debug("ScrollPattern probe failed for '{}': {}", control.AutomationId, exc)
        return False, None, None, None, None


def _safe_float(getter) -> Optional[float]:
    """Call *getter* and return the float result, or None on any error."""
    try:
        val = getter()
        return float(val) if val is not None else None
    except Exception:  # noqa: BLE001
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Scrollbar child detection
# ══════════════════════════════════════════════════════════════════════════════

def _has_scrollbar_child(control: auto.Control, orientation: str) -> bool:
    """
    Return True if *control* has a direct ScrollBar child with the given
    orientation ('Vertical' or 'Horizontal').
    ScrollBar controls have ControlType == ScrollBarControl.
    """
    try:
        for child in control.GetChildren():
            if child.ControlTypeName != "ScrollBarControl":
                continue
            # The orientation is usually encoded in the Name or AutomationId.
            name_lower = (child.Name or "").lower()
            aid_lower  = (child.AutomationId or "").lower()
            orient_lower = orientation.lower()
            if orient_lower in name_lower or orient_lower in aid_lower:
                return True
            # Fallback: check BoundingRectangle shape — a vertical scrollbar
            # is taller than it is wide; horizontal is the reverse.
            rect = child.BoundingRectangle
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if orientation == "Vertical"   and h > w:
                return True
            if orientation == "Horizontal" and w > h:
                return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("Scrollbar child check failed for '{}': {}", control.AutomationId, exc)
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Live tree walker
# ══════════════════════════════════════════════════════════════════════════════

def _walk_live(
    control: auto.Control,
    depth: int,
    results: list[ScrollCandidateInfo],
) -> None:
    """
    Recursively walk the live UIA tree rooted at *control*.
    Appends one ScrollCandidateInfo per node to *results*.
    Stops at MAX_TREE_DEPTH.
    """
    try:
        rect  = control.BoundingRectangle
        w     = rect.right  - rect.left
        h     = rect.bottom - rect.top

        has_sp, v_pct, h_pct, v_view, h_view = _probe_scroll_pattern(control)
        has_v_bar = _has_scrollbar_child(control, "Vertical")
        has_h_bar = _has_scrollbar_child(control, "Horizontal")

        info = ScrollCandidateInfo(
            index=len(results),
            depth=depth,
            automation_id=control.AutomationId or "",
            name=control.Name or "",
            control_type=control.ControlTypeName or "",
            class_name=control.ClassName or "",
            left=rect.left,
            top=rect.top,
            right=rect.right,
            bottom=rect.bottom,
            width=w,
            height=h,
            has_scroll_pattern=has_sp,
            has_vertical_scrollbar=has_v_bar,
            has_horizontal_scrollbar=has_h_bar,
            vertical_scroll_percent=v_pct,
            horizontal_scroll_percent=h_pct,
            vertical_view_size=v_view,
            horizontal_view_size=h_view,
        )
        results.append(info)

        logger.debug(
            "[{}] depth={} type={} id={!r} name={!r} "
            "scroll_pattern={} v_bar={} h_bar={} "
            "v_pct={} h_pct={} rect=({},{},{},{})",
            info.index, depth,
            info.control_type, info.automation_id, info.name,
            has_sp, has_v_bar, has_h_bar,
            v_pct, h_pct,
            rect.left, rect.top, rect.right, rect.bottom,
        )

    except Exception as exc:  # noqa: BLE001
        logger.warning("Error inspecting control at depth {}: {}", depth, exc)

    if depth >= MAX_TREE_DEPTH:
        return

    try:
        for child in control.GetChildren():
            _walk_live(child, depth + 1, results)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Cannot get children at depth {}: {}", depth, exc)


# ══════════════════════════════════════════════════════════════════════════════
# JSON export
# ══════════════════════════════════════════════════════════════════════════════

def _save_json(candidates: list[ScrollCandidateInfo], path: Path) -> None:
    """Serialise *candidates* to a pretty-printed JSON file at *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(c) for c in candidates]
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    logger.info("Scrollable controls JSON saved → {}  ({} entries)", path, len(payload))


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def inspect_scroll_candidates(root: auto.Control) -> list[ScrollCandidateInfo]:
    """
    Walk the entire live UIA descendant tree of *root*, probe every control
    for scroll capability, and return the full list of ScrollCandidateInfo.

    Also saves debug/scrollable_controls.json automatically.
    """
    logger.info(
        "Starting scroll inspection from '{}' (id='{}').",
        root.Name, root.AutomationId,
    )

    candidates: list[ScrollCandidateInfo] = []
    _walk_live(root, depth=0, results=candidates)

    # ── summary ───────────────────────────────────────────────────────────────
    with_pattern = [c for c in candidates if c.has_scroll_pattern]
    with_v_bar   = [c for c in candidates if c.has_vertical_scrollbar]
    with_h_bar   = [c for c in candidates if c.has_horizontal_scrollbar]
    either       = [c for c in candidates
                    if c.has_scroll_pattern
                    or c.has_vertical_scrollbar
                    or c.has_horizontal_scrollbar]

    logger.info("── Scroll inspection summary ─────────────────")
    logger.info("  Total controls inspected  : {}", len(candidates))
    logger.info("  Have ScrollPattern        : {}", len(with_pattern))
    logger.info("  Have vertical scrollbar   : {}", len(with_v_bar))
    logger.info("  Have horizontal scrollbar : {}", len(with_h_bar))
    logger.info("  Any scroll capability     : {}", len(either))
    logger.info("─────────────────────────────────────────────")

    for c in either:
        logger.info(
            "  SCROLLABLE [{}] {} id={!r} rect=({},{},{},{}) "
            "v_pct={} h_pct={}",
            c.index, c.control_type, c.automation_id,
            c.left, c.top, c.right, c.bottom,
            c.vertical_scroll_percent, c.horizontal_scroll_percent,
        )

    _save_json(candidates, SCROLLABLE_CONTROLS_JSON)
    return candidates
