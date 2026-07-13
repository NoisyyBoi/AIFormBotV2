"""
Phase 3 — Form data exporter.

Responsibilities:
  - Write the merged label/value dictionary to output/form_data.json.
  - Write a human-readable version to output/form_data.txt.
  - Never raise — log errors and return.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger


# ── JSON ──────────────────────────────────────────────────────────────────────

def save_form_data_json(data: dict[str, str], path: Path) -> None:
    """Serialise *data* to a pretty-printed JSON file at *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        logger.info("Form data JSON saved → {}  ({} fields)", path, len(data))
    except OSError as exc:
        logger.error("Could not write form data JSON to {}: {}", path, exc)


# ── Plain text ────────────────────────────────────────────────────────────────

def _format_txt(data: dict[str, str]) -> str:
    """
    Build a human-readable text representation of *data*.

    Format:
        Label                : Value
        ─────────────────────────────
        ...
    """
    if not data:
        return "(no fields extracted)\n"

    max_key_len = max(len(k) for k in data)
    col_width = max(max_key_len, 20)
    separator = "─" * (col_width + 3 + 40)

    lines = [separator]
    for label, value in data.items():
        lines.append(f"{label:<{col_width}} : {value}")
    lines.append(separator)
    lines.append(f"Total fields: {len(data)}")
    return "\n".join(lines) + "\n"


def save_form_data_txt(data: dict[str, str], path: Path) -> None:
    """Write a human-readable text report of *data* to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as fh:
            fh.write(_format_txt(data))
        logger.info("Form data TXT saved → {}  ({} fields)", path, len(data))
    except OSError as exc:
        logger.error("Could not write form data TXT to {}: {}", path, exc)
