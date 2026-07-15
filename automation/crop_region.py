"""
Phase 3.1 — OCR content-region calculator.

Responsibilities:
  - Accept the detected left-panel ControlInfo node.
  - Derive the tightest BoundingRect that covers only the scrollable form
    content — excluding borders, title bars, toolbars, and the right panel.
  - Never interact with the screen or any live control.
  - Never raise — return a safe fallback rect on any error.

Strategy (in order, first that produces a valid rect wins):
  1. CHILD UNION  — compute the union of every visible child's bounding rect
                    that falls inside the inset panel rect.  Pad by CROP_PADDING.
  2. INSET FALLBACK — if no children qualify, inset the raw panel rect by the
                      configured margins.
  3. HARD CAP     — clamp the right edge so the rect never exceeds
                    CROP_MAX_WIDTH_FRACTION of the panel width.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from config.settings import (
    CROP_MAX_WIDTH_FRACTION,
    CROP_PADDING,
    PANEL_INSET_BOTTOM,
    PANEL_INSET_LEFT,
    PANEL_INSET_RIGHT,
    PANEL_INSET_TOP,
)
from ui.inspector import BoundingRect, ControlInfo


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _inset(rect: BoundingRect) -> BoundingRect:
    """Apply the configured panel insets to strip chrome/border pixels."""
    return BoundingRect(
        left=rect.left + PANEL_INSET_LEFT,
        top=rect.top + PANEL_INSET_TOP,
        right=rect.right - PANEL_INSET_RIGHT,
        bottom=rect.bottom - PANEL_INSET_BOTTOM,
    )


def _is_inside(child_rect: BoundingRect, container: BoundingRect) -> bool:
    """True when child_rect is fully or substantially inside container."""
    return (
        child_rect.left >= container.left - CROP_PADDING
        and child_rect.top >= container.top - CROP_PADDING
        and child_rect.right <= container.right + CROP_PADDING
        and child_rect.bottom <= container.bottom + CROP_PADDING
    )


def _has_positive_area(rect: BoundingRect) -> bool:
    return rect.width > 0 and rect.height > 0


def _union(rects: list[BoundingRect]) -> BoundingRect:
    """Return the smallest BoundingRect that contains all *rects*."""
    return BoundingRect(
        left=min(r.left for r in rects),
        top=min(r.top for r in rects),
        right=max(r.right for r in rects),
        bottom=max(r.bottom for r in rects),
    )


def _pad(rect: BoundingRect, px: int) -> BoundingRect:
    """Expand *rect* by *px* on every side."""
    return BoundingRect(
        left=rect.left - px,
        top=rect.top - px,
        right=rect.right + px,
        bottom=rect.bottom + px,
    )


def _clamp_to(rect: BoundingRect, container: BoundingRect) -> BoundingRect:
    """Clamp *rect* so it does not extend beyond *container*."""
    return BoundingRect(
        left=max(rect.left, container.left),
        top=max(rect.top, container.top),
        right=min(rect.right, container.right),
        bottom=min(rect.bottom, container.bottom),
    )


def _apply_width_cap(rect: BoundingRect, panel_rect: BoundingRect) -> BoundingRect:
    """
    Ensure the crop rect's right edge never exceeds
    panel_rect.left + CROP_MAX_WIDTH_FRACTION * panel_rect.width.
    This guards against the right input panel bleeding into the crop.
    """
    max_right = int(panel_rect.left + panel_rect.width * CROP_MAX_WIDTH_FRACTION)
    if rect.right > max_right:
        logger.debug(
            "Right-edge cap applied: {} → {}  (panel_left={}, fraction={}).",
            rect.right, max_right, panel_rect.left, CROP_MAX_WIDTH_FRACTION,
        )
        return BoundingRect(
            left=rect.left,
            top=rect.top,
            right=max_right,
            bottom=rect.bottom,
        )
    return rect


# ── Child-union strategy ──────────────────────────────────────────────────────

def _collect_visible_children(
    panel: ControlInfo,
    container: BoundingRect,
) -> list[BoundingRect]:
    """
    Return bounding rects for all direct children of *panel* that:
      - have positive area
      - are visible (is_visible=True)
      - fall substantially inside *container* (the inset panel rect)
    """
    qualifying: list[BoundingRect] = []
    for child in panel.children:
        r = child.bounding_rect
        if not _has_positive_area(r):
            continue
        if not child.is_visible:
            continue
        if not _is_inside(r, container):
            continue
        qualifying.append(r)
    return qualifying


# ── Public API ────────────────────────────────────────────────────────────────

def compute_content_rect(panel: ControlInfo) -> BoundingRect:
    """
    Derive the OCR crop BoundingRect for *panel*.

    Returns a BoundingRect guaranteed to:
      - Have positive area.
      - Lie within the panel's bounding rect.
      - Not exceed CROP_MAX_WIDTH_FRACTION of the panel width (right-edge cap).

    Logs every decision so the caller can audit the chosen rect.
    """
    panel_rect = panel.bounding_rect

    if not _has_positive_area(panel_rect):
        # Degenerate panel — return as-is; OCR will fail gracefully.
        logger.warning(
            "Panel '{}' has zero-area bounding rect — returning raw rect.",
            panel.name,
        )
        return panel_rect

    # Step 1: inset the panel rect to strip borders/title
    inset_rect = _inset(panel_rect)
    if not _has_positive_area(inset_rect):
        logger.warning(
            "Inset rect has no area for panel '{}' — using raw panel rect.",
            panel.name,
        )
        inset_rect = panel_rect

    # Step 2: collect qualifying child rects
    child_rects = _collect_visible_children(panel, inset_rect)

    if child_rects:
        # Build union, pad it, clamp to the inset container
        raw_union = _union(child_rects)
        padded = _pad(raw_union, CROP_PADDING)
        clamped = _clamp_to(padded, inset_rect)
        strategy = "child-union"
    else:
        # No qualifying children — fall back to the inset panel rect itself
        clamped = inset_rect
        strategy = "inset-fallback"
        logger.debug(
            "No visible children inside inset rect for panel '{}' — "
            "falling back to inset panel rect.",
            panel.name,
        )

    # Step 3: hard cap on right edge to exclude the right input panel
    content_rect = _apply_width_cap(clamped, panel_rect)

    logger.info(
        "OCR content rect (strategy={}): ({},{},{},{})  size={}x{}",
        strategy,
        content_rect.left,
        content_rect.top,
        content_rect.right,
        content_rect.bottom,
        content_rect.width,
        content_rect.height,
    )
    return content_rect
