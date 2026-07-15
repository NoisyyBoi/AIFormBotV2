"""
Phase 3 — Left panel locator.

Responsibilities:
  - Inspect the ControlInfo tree produced by Phase 1.
  - Identify the left information panel using spatial heuristics.
  - Identify the innermost scrollable container within that panel as the
    precise scroll target — so wheel events never land on the right pane.
  - Return ControlInfo nodes so callers can capture screen regions.
  - Never interact with the right panel.
  - Never raise — return None on failure and let the caller decide.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from ui.inspector import BoundingRect, ControlInfo, flatten_tree


# Control types considered plausible containers for the left info panel.
_PANEL_TYPES: frozenset[str] = frozenset(
    {
        "PaneControl",
        "GroupControl",
        "CustomControl",
        "WindowControl",
        "DocumentControl",
        "ScrollViewerControl",
        "ListControl",
        "DataGridControl",
    }
)

# Control types that are themselves scrollable — preferred scroll targets.
_SCROLLABLE_TYPES: frozenset[str] = frozenset(
    {
        "ScrollViewerControl",
        "ListControl",
        "DataGridControl",
        "PaneControl",
        "DocumentControl",
        "CustomControl",
    }
)


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _centre_x(rect: BoundingRect) -> float:
    return (rect.left + rect.right) / 2.0


def _area(rect: BoundingRect) -> int:
    return rect.width * rect.height


def _is_left_half(rect: BoundingRect, root_rect: BoundingRect) -> bool:
    """True when the panel's horizontal centre is in the left half of root."""
    root_mid = (root_rect.left + root_rect.right) / 2.0
    return _centre_x(rect) < root_mid


def _has_area(rect: BoundingRect) -> bool:
    return rect.width > 10 and rect.height > 10


# ── Candidate scoring ─────────────────────────────────────────────────────────

def _score(node: ControlInfo, root_rect: BoundingRect) -> Optional[int]:
    """
    Return an integer score for *node* as a left-panel candidate,
    or None if it does not qualify at all.

    Higher score = better candidate.
    Score = pixel area (larger panels score higher).
    """
    r = node.bounding_rect

    if not _has_area(r):
        return None
    if not _is_left_half(r, root_rect):
        return None
    if node.control_type not in _PANEL_TYPES:
        return None

    return _area(r)


# ── Public API ────────────────────────────────────────────────────────────────

def find_left_panel(root: ControlInfo) -> Optional[ControlInfo]:
    """
    Search the full ControlInfo tree for the left information panel.

    Strategy:
      1. Flatten the tree.
      2. Filter to Panel/Group/Pane nodes whose centre is in the left half
         of *root*.
      3. Pick the one with the largest area.

    Returns the best-matching ControlInfo node, or None if nothing qualifies.
    Logs the result either way so the caller has full visibility.
    """
    all_nodes = flatten_tree(root)
    root_rect = root.bounding_rect

    if not _has_area(root_rect):
        logger.warning(
            "Root bounding rect has no area — cannot determine left half. "
            "Will fall back to full tree."
        )
        return None

    best_node: Optional[ControlInfo] = None
    best_score: int = -1
    candidates_found: int = 0

    for node in all_nodes:
        score = _score(node, root_rect)
        if score is None:
            continue
        candidates_found += 1
        if score > best_score:
            best_score = score
            best_node = node

    if best_node is None:
        logger.warning(
            "Left panel not found among {} nodes "
            "(no qualifying Panel/Group/Pane in left half of root).",
            len(all_nodes),
        )
        return None

    r = best_node.bounding_rect
    logger.info(
        "Left panel detected: type='{}' name='{}' id='{}' "
        "rect=({},{},{},{}) area={} — from {} candidates.",
        best_node.control_type,
        best_node.name,
        best_node.automation_id,
        r.left, r.top, r.right, r.bottom,
        best_score,
        candidates_found,
    )
    return best_node


def find_scroll_target(
    left_panel: ControlInfo,
    root_rect: BoundingRect,
) -> ControlInfo:
    """
    Find the innermost scrollable container that is:
      - A descendant of *left_panel* (or *left_panel* itself).
      - Strictly within the LEFT half of *root_rect*.
      - Of a scrollable control type.
      - Has positive area.

    Selection priority:
      1. Deepest node (highest depth) among scrollable types — the innermost
         container is most likely the actual scrollable list, not a wrapper.
      2. If no scrollable-typed descendant qualifies, fall back to the
         left_panel node itself.

    This guarantees wheel events land inside the left pane, never the right.
    """
    all_nodes = flatten_tree(left_panel)
    root_mid = (root_rect.left + root_rect.right) / 2.0

    candidates: list[ControlInfo] = []

    for node in all_nodes:
        r = node.bounding_rect
        if not _has_area(r):
            continue
        if node.control_type not in _SCROLLABLE_TYPES:
            continue
        # Entire rect must be strictly left of the midpoint —
        # right edge must not cross into the right half.
        if r.right > root_mid:
            continue
        candidates.append(node)

    if not candidates:
        logger.warning(
            "No scrollable child found strictly in left half — "
            "falling back to left_panel node itself for scroll targeting."
        )
        _log_scroll_target(left_panel)
        return left_panel

    # Pick deepest (innermost) candidate; break ties by largest area.
    best = max(candidates, key=lambda n: (n.depth, _area(n.bounding_rect)))
    _log_scroll_target(best)
    return best


def _log_scroll_target(node: ControlInfo) -> None:
    """Emit the required scroll-target identity log lines."""
    r = node.bounding_rect
    logger.info("Scrolling control:")
    logger.info("  AutomationId  = {}", node.automation_id or "(none)")
    logger.info("  ControlType   = {}", node.control_type)
    logger.info(
        "  BoundingRect  = ({}, {}, {}, {})  size={}x{}",
        r.left, r.top, r.right, r.bottom,
        r.width, r.height,
    )
