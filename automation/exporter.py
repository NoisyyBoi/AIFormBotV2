"""
Export the UI control tree to JSON and plain-text formats.

Responsibilities:
  - Serialise ControlInfo trees to JSON (debug/ui_tree.json).
  - Write a human-readable indented text report (debug/ui_tree.txt).
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from ui.inspector import ControlInfo


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _control_to_dict(node: ControlInfo) -> dict:
    """Recursively convert a ControlInfo tree to a plain dict."""
    return {
        "depth": node.depth,
        "control_type": node.control_type,
        "name": node.name,
        "automation_id": node.automation_id,
        "class_name": node.class_name,
        "bounding_rect": node.bounding_rect.as_dict(),
        "is_visible": node.is_visible,
        "is_enabled": node.is_enabled,
        "children": [_control_to_dict(child) for child in node.children],
    }


def save_json(root: ControlInfo, path: Path) -> None:
    """Write the full control tree to *path* as formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _control_to_dict(root)

    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    logger.info("UI tree JSON saved → {}", path)


# ── Text helpers ──────────────────────────────────────────────────────────────

_INDENT = "  "  # two spaces per depth level


def _format_node(node: ControlInfo) -> str:
    """Return a single-line text representation of one control."""
    rect = node.bounding_rect
    return (
        f"{_INDENT * node.depth}"
        f"[{node.control_type}] "
        f"name={node.name!r}  "
        f"id={node.automation_id!r}  "
        f"class={node.class_name!r}  "
        f"rect=({rect.left},{rect.top},{rect.right},{rect.bottom})  "
        f"visible={node.is_visible}  "
        f"enabled={node.is_enabled}"
    )


def _collect_lines(node: ControlInfo, lines: list[str]) -> None:
    """Depth-first traversal that appends formatted lines in place."""
    lines.append(_format_node(node))
    for child in node.children:
        _collect_lines(child, lines)


def save_txt(root: ControlInfo, path: Path) -> None:
    """Write a human-readable indented tree report to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    _collect_lines(root, lines)

    with path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")

    logger.info(
        "UI tree TXT saved → {}  ({} controls)",
        path,
        len(lines),
    )
