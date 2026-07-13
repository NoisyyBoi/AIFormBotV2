"""
Recursive UI-tree inspector.

Responsibilities:
  - Locate the root panel by Name anywhere in the descendant tree.
  - Walk every descendant up to MAX_TREE_DEPTH.
  - Return a list of ControlInfo dataclasses (one per node).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import uiautomation as auto
from loguru import logger

from config.settings import MAX_TREE_DEPTH, ROOT_CONTROL_NAME


@dataclass
class BoundingRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def as_dict(self) -> dict:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class ControlInfo:
    depth: int
    control_type: str
    name: str
    automation_id: str
    class_name: str
    bounding_rect: BoundingRect
    is_visible: bool
    is_enabled: bool
    children: list[ControlInfo] = field(default_factory=list)


def _extract_bounding_rect(control: auto.Control) -> BoundingRect:
    """Pull the bounding rectangle out of a uiautomation Control."""
    rect = control.BoundingRectangle
    return BoundingRect(
        left=rect.left,
        top=rect.top,
        right=rect.right,
        bottom=rect.bottom,
    )


def _is_visible(control: auto.Control) -> bool:
    """Return False only when IsOffscreen is explicitly True."""
    try:
        return not control.IsOffscreen
    except Exception:  # noqa: BLE001
        return True


def _build_control_info(control: auto.Control, depth: int) -> ControlInfo:
    """Create a ControlInfo snapshot for a single control."""
    return ControlInfo(
        depth=depth,
        control_type=control.ControlTypeName or "",
        name=control.Name or "",
        automation_id=control.AutomationId or "",
        class_name=control.ClassName or "",
        bounding_rect=_extract_bounding_rect(control),
        is_visible=_is_visible(control),
        is_enabled=bool(control.IsEnabled),
    )


def _walk(control: auto.Control, depth: int) -> ControlInfo:
    """
    Recursively build a ControlInfo tree.
    Stops at MAX_TREE_DEPTH to prevent runaway recursion.
    """
    node = _build_control_info(control, depth)

    if depth >= MAX_TREE_DEPTH:
        logger.warning("MAX_TREE_DEPTH ({}) reached — truncating here.", MAX_TREE_DEPTH)
        return node

    try:
        children = control.GetChildren()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not get children at depth {}: {}", depth, exc)
        return node

    for child in children:
        try:
            node.children.append(_walk(child, depth + 1))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping child at depth {} due to error: {}", depth + 1, exc)

    return node


def _search_descendant(
    control: auto.Control,
    name: str,
    depth: int,
) -> Optional[tuple[auto.Control, int]]:
    """
    Depth-first search for the first control whose Name equals *name*.
    Returns a (control, depth) tuple, or None if not found.
    Stops descending beyond MAX_TREE_DEPTH.
    """
    if (control.Name or "").strip() == name.strip():
        return control, depth

    if depth >= MAX_TREE_DEPTH:
        return None

    try:
        children = control.GetChildren()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Cannot get children at depth {} during search: {}", depth, exc)
        return None

    for child in children:
        try:
            result = _search_descendant(child, name, depth + 1)
            if result is not None:
                return result
        except Exception as exc:  # noqa: BLE001
            logger.debug("Error searching child at depth {}: {}", depth + 1, exc)

    return None


def find_root_panel(
    window: auto.WindowControl,
    name: str = ROOT_CONTROL_NAME,
) -> Optional[auto.Control]:
    """
    Recursively search the entire descendant tree of *window* for a control
    whose Name equals *name*.

    Returns the control on success and logs its location.
    Returns None (does NOT raise) if the control is not found — callers must
    handle the missing-panel case gracefully.
    """
    logger.debug("Searching full descendant tree for panel named '{}'.", name)
    result = _search_descendant(window, name, depth=0)

    if result is None:
        logger.warning(
            "Control named '{}' was NOT found anywhere in the tree of '{}'.",
            name,
            window.Name,
        )
        return None

    control, found_depth = result
    rect = control.BoundingRectangle
    logger.info("Root panel found at depth {}:", found_depth)
    logger.info("  Name          : {}", control.Name)
    logger.info("  ControlType   : {}", control.ControlTypeName)
    logger.info("  AutomationId  : {}", control.AutomationId or "(none)")
    logger.info("  ClassName     : {}", control.ClassName or "(none)")
    logger.info(
        "  BoundingRect  : ({}, {}, {}, {})",
        rect.left, rect.top, rect.right, rect.bottom,
    )
    return control


def inspect_tree(root: auto.Control) -> ControlInfo:
    """
    Walk the full descendant tree starting at *root*.
    Returns the root ControlInfo with all children populated.
    """
    logger.info("Starting recursive UI-tree inspection from '{}'.", root.Name)
    tree = _walk(root, depth=0)
    logger.info("Inspection complete.")
    return tree


def flatten_tree(root: ControlInfo) -> list[ControlInfo]:
    """
    Return a flat list of every ControlInfo node in depth-first order.
    Useful for iteration without recursion at call sites.
    """
    result: list[ControlInfo] = []
    stack = [root]
    while stack:
        node = stack.pop(0)
        result.append(node)
        stack = node.children + stack
    return result
