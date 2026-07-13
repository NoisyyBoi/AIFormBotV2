"""
Phase 2 — Field map exporter.

Responsibilities:
  - Serialise a list of FieldEntry objects to debug/control_map.json.
  - Write the same data as debug/control_map.csv with columns:
      Label, AutomationId, Type, ParentPanel, X, Y, Width, Height
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from loguru import logger

from ui.field_mapper import FieldEntry


# ── JSON ──────────────────────────────────────────────────────────────────────

def _entry_to_dict(entry: FieldEntry) -> dict:
    """Convert one FieldEntry to a JSON-serialisable dict."""
    r = entry.bounding_rect
    return {
        "label":              entry.label,
        "automation_id":      entry.automation_id,
        "type":               entry.control_type,
        "name":               entry.name,
        "parent_automation_id": entry.parent_automation_id,
        "parent_name":        entry.parent_name,
        "bounding_rect": {
            "x":      r.left,
            "y":      r.top,
            "width":  r.width,
            "height": r.height,
        },
        "is_visible":  entry.is_visible,
        "is_enabled":  entry.is_enabled,
        "siblings": [
            {
                "automation_id": s.automation_id,
                "name":          s.name,
                "control_type":  s.control_type,
            }
            for s in entry.siblings
        ],
    }


def save_map_json(entries: list[FieldEntry], path: Path) -> None:
    """Write the full field map to *path* as formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [_entry_to_dict(e) for e in entries]

    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    logger.info("Control map JSON saved → {}  ({} entries)", path, len(payload))


# ── CSV ───────────────────────────────────────────────────────────────────────

_CSV_COLUMNS = ["Label", "AutomationId", "Type", "ParentPanel", "X", "Y", "Width", "Height"]


def _entry_to_row(entry: FieldEntry) -> dict:
    """Convert one FieldEntry to a CSV row dict."""
    r = entry.bounding_rect
    return {
        "Label":        entry.label,
        "AutomationId": entry.automation_id,
        "Type":         entry.control_type,
        "ParentPanel":  entry.parent_name or entry.parent_automation_id,
        "X":            r.left,
        "Y":            r.top,
        "Width":        r.width,
        "Height":       r.height,
    }


def save_map_csv(entries: list[FieldEntry], path: Path) -> None:
    """Write the field map to *path* as a UTF-8 CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for entry in entries:
            writer.writerow(_entry_to_row(entry))

    logger.info("Control map CSV saved → {}  ({} rows)", path, len(entries))
