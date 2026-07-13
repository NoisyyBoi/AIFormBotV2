"""
Phase 2 — Field mapper.

Responsibilities:
  - Walk the ControlInfo tree and collect every input control
    (Edit, ComboBox, DateTimePicker, Button).
  - For each input, find the nearest TextControl to its left on the same row.
  - Return a list of FieldEntry dataclasses ready for export and validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from config.settings import (
    INPUT_CONTROL_TYPES,
    LABEL_SEARCH_X_TOLERANCE_PX,
    LABEL_SEARCH_Y_TOLERANCE_PX,
    TEXT_CONTROL_TYPE,
)
from ui.inspector import BoundingRect, ControlInfo, flatten_tree


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class SiblingInfo:
    automation_id: str
    name: str
    control_type: str


@dataclass
class FieldEntry:
    label: str                        # nearest TextControl text to the left
    automation_id: str
    control_type: str                 # normalised type string
    name: str
    bounding_rect: BoundingRect
    parent_automation_id: str
    parent_name: str
    siblings: list[SiblingInfo]
    is_visible: bool
    is_enabled: bool


# ── Parent / sibling resolution ───────────────────────────────────────────────

def _build_parent_map(
    root: ControlInfo,
) -> dict[int, ControlInfo]:
    """
    Return a dict mapping id(child) → parent ControlInfo for every node
    in the tree.  The root itself has no parent and is not included.
    """
    parent_map: dict[int, ControlInfo] = {}
    stack = [(root, None)]
    while stack:
        node, parent = stack.pop()
        if parent is not None:
            parent_map[id(node)] = parent
        for child in node.children:
            stack.append((child, node))
    return parent_map


def _siblings_of(node: ControlInfo, parent: Optional[ControlInfo]) -> list[SiblingInfo]:
    """Return SiblingInfo for every child of *parent* except *node* itself."""
    if parent is None:
        return []
    return [
        SiblingInfo(
            automation_id=child.automation_id,
            name=child.name,
            control_type=child.control_type,
        )
        for child in parent.children
        if child is not node
    ]


# ── Label resolution ──────────────────────────────────────────────────────────

def _vertical_centre(rect: BoundingRect) -> float:
    return (rect.top + rect.bottom) / 2.0


def _is_left_aligned(label_rect: BoundingRect, input_rect: BoundingRect) -> bool:
    """
    True when the label's right edge is to the LEFT of the input's left edge
    and within LABEL_SEARCH_X_TOLERANCE_PX pixels of it.
    """
    gap = input_rect.left - label_rect.right
    return 0 <= gap <= LABEL_SEARCH_X_TOLERANCE_PX


def _is_same_row(label_rect: BoundingRect, input_rect: BoundingRect) -> bool:
    """True when vertical centres are within LABEL_SEARCH_Y_TOLERANCE_PX."""
    delta = abs(_vertical_centre(label_rect) - _vertical_centre(input_rect))
    return delta <= LABEL_SEARCH_Y_TOLERANCE_PX


def _find_label(
    input_node: ControlInfo,
    text_controls: list[ControlInfo],
) -> str:
    """
    Among all TextControls, find the one that is:
      1. To the LEFT of *input_node* (within X tolerance).
      2. On the same row (within Y tolerance).
      3. Closest horizontally (smallest gap between label.right and input.left).

    Returns the label text, or empty string if nothing qualifies.
    """
    candidates: list[tuple[int, ControlInfo]] = []  # (gap, node)

    for text_node in text_controls:
        r = text_node.bounding_rect
        if not _is_left_aligned(r, input_node.bounding_rect):
            continue
        if not _is_same_row(r, input_node.bounding_rect):
            continue
        gap = input_node.bounding_rect.left - r.right
        candidates.append((gap, text_node))

    if not candidates:
        return ""

    # pick the closest (smallest gap)
    candidates.sort(key=lambda t: t[0])
    best = candidates[0][1]
    return (best.name or "").strip()


# ── Public API ────────────────────────────────────────────────────────────────

def build_field_map(root: ControlInfo) -> list[FieldEntry]:
    """
    Walk the full ControlInfo tree rooted at *root* and return one
    FieldEntry per input control (Edit / ComboBox / DateTimePicker / Button).

    Algorithm:
      1. Flatten the tree once into a list.
      2. Partition into input controls and text controls.
      3. Build a parent map for sibling/parent resolution.
      4. For each input, resolve its nearest left-side label.
    """
    all_nodes = flatten_tree(root)
    parent_map = _build_parent_map(root)

    input_nodes = [n for n in all_nodes if n.control_type in INPUT_CONTROL_TYPES]
    text_nodes = [n for n in all_nodes if n.control_type == TEXT_CONTROL_TYPE]

    logger.debug(
        "Field mapper: {} input controls, {} text controls in tree.",
        len(input_nodes),
        len(text_nodes),
    )

    entries: list[FieldEntry] = []

    for node in input_nodes:
        parent = parent_map.get(id(node))
        label = _find_label(node, text_nodes)

        if not label:
            logger.warning(
                "No label found for {} '{}' (id={}) at rect ({},{},{},{}).",
                node.control_type,
                node.name,
                node.automation_id,
                node.bounding_rect.left,
                node.bounding_rect.top,
                node.bounding_rect.right,
                node.bounding_rect.bottom,
            )

        entries.append(
            FieldEntry(
                label=label,
                automation_id=node.automation_id,
                control_type=node.control_type,
                name=node.name,
                bounding_rect=node.bounding_rect,
                parent_automation_id=parent.automation_id if parent else "",
                parent_name=parent.name if parent else "",
                siblings=_siblings_of(node, parent),
                is_visible=node.is_visible,
                is_enabled=node.is_enabled,
            )
        )

    logger.info(
        "Field map built: {} entries ({} with labels, {} without).",
        len(entries),
        sum(1 for e in entries if e.label),
        sum(1 for e in entries if not e.label),
    )
    return entries


def log_totals(entries: list[FieldEntry]) -> None:
    """Print a type-breakdown summary to the log."""
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.control_type] = counts.get(e.control_type, 0) + 1

    logger.info("── Field map totals ──────────────────────────")
    logger.info("  Total EditControls       : {}", counts.get("EditControl", 0))
    logger.info("  Total ComboBoxes         : {}", counts.get("ComboBoxControl", 0))
    logger.info("  Total DateTimePickers    : {}", counts.get("DateTimePickerControl", 0))
    logger.info("  Total Buttons            : {}", counts.get("ButtonControl", 0))
    logger.info("  Total (all types)        : {}", len(entries))
    logger.info("─────────────────────────────────────────────")
