"""
Phase 3 — Left Panel Reader.

Responsibilities:
  - Detect the left information panel from the existing ControlInfo tree.
  - Scroll through the entire panel one step at a time.
  - OCR each visible section.
  - Parse every OCR result into label/value pairs.
  - Merge all sections into one dictionary (latest value wins on duplicate keys).
  - Return a ReadResult containing the merged data and rich diagnostics.

This module does NOT:
  - Type into any control.
  - Click any control.
  - Interact with the right panel.
  - Submit or modify the form in any way.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import win32api
import win32con
import win32gui
from loguru import logger

from config.settings import (
    FORM_DATA_JSON,
    FORM_DATA_TXT,
    LABEL_MAX_LENGTH,
    LABEL_MIN_LENGTH,
    LABEL_VALUE_SEPARATORS,
    SCROLL_CLICKS_PER_STEP,
    SCROLL_MAX_ITERATIONS,
    SCROLL_PAUSE_S,
)
from automation.form_data_exporter import save_form_data_json, save_form_data_txt
from automation.ocr_engine import OcrResult, run_ocr
from ui.inspector import BoundingRect, ControlInfo
from ui.panel_locator import find_left_panel


# ══════════════════════════════════════════════════════════════════════════════
# Data models
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SectionResult:
    """OCR output and parsed pairs for one scroll position."""
    scroll_index: int
    ocr: OcrResult
    pairs: dict[str, str] = field(default_factory=dict)


@dataclass
class ReadResult:
    """Final aggregated output of the full left-panel read."""
    form_data: dict[str, str] = field(default_factory=dict)
    sections_read: int = 0
    total_fields: int = 0
    duplicate_keys_overwritten: int = 0
    total_elapsed_s: float = 0.0
    mean_confidence: float = 0.0   # average across all sections that returned text
    panel_found: bool = False
    success: bool = False


# ══════════════════════════════════════════════════════════════════════════════
# Label / value parser
# ══════════════════════════════════════════════════════════════════════════════

def _split_line(line: str) -> Optional[tuple[str, str]]:
    """
    Attempt to split a single OCR text line into a (label, value) pair.

    Tries each configured separator in order.  Returns None when no separator
    is found or when the resulting label fails the length guard.
    """
    for sep in LABEL_VALUE_SEPARATORS:
        if sep in line:
            label, _, value = line.partition(sep)
            label = label.strip()
            value = value.strip()
            if LABEL_MIN_LENGTH <= len(label) <= LABEL_MAX_LENGTH:
                return label, value
    return None


def parse_pairs(lines: list[str]) -> dict[str, str]:
    """
    Convert a list of OCR text lines into a label→value dictionary.

    Lines that cannot be split are silently skipped (they may be headings,
    decorative separators, or OCR noise).
    """
    pairs: dict[str, str] = {}
    for line in lines:
        result = _split_line(line)
        if result is not None:
            label, value = result
            pairs[label] = value
    return pairs


# ══════════════════════════════════════════════════════════════════════════════
# Scroll helpers  (mouse-wheel scroll, no click, no button press)
# ══════════════════════════════════════════════════════════════════════════════

def _panel_centre(rect: BoundingRect) -> tuple[int, int]:
    """Return the (x, y) screen coordinate of the panel's centre."""
    return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2


def _scroll_down(rect: BoundingRect, clicks: int) -> None:
    """
    Send a mouse-wheel scroll-down event over the centre of *rect*.
    Uses win32api to move the cursor and post a wheel message — no button
    clicks are generated.
    """
    cx, cy = _panel_centre(rect)
    win32api.SetCursorPos((cx, cy))
    # WHEEL_DELTA = 120 per notch; negative = scroll down
    delta = -120 * clicks
    win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, cx, cy, delta, 0)


def _capture_screenshot_hash(rect: BoundingRect) -> int:
    """
    Return a cheap integer hash of the current pixel content of *rect*.
    Used to detect whether the panel has actually scrolled (content changed).
    """
    from PIL import ImageGrab
    import numpy as np
    img = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom),
        all_screens=False,
    )
    arr = np.array(img)
    # Downsample to a coarse grid for speed, then sum
    return int(arr[::8, ::8].sum())


# ══════════════════════════════════════════════════════════════════════════════
# Core read loop
# ══════════════════════════════════════════════════════════════════════════════

def _read_sections(rect: BoundingRect) -> list[SectionResult]:
    """
    Scroll through the panel at *rect* from top to bottom.

    Algorithm:
      1. OCR the current view → parse pairs → record section.
      2. Scroll down by SCROLL_CLICKS_PER_STEP.
      3. Wait SCROLL_PAUSE_S for the panel to repaint.
      4. Hash the new pixel content.
      5. If the hash equals the previous hash → content did not change →
         we have reached the bottom.  Stop.
      6. Repeat up to SCROLL_MAX_ITERATIONS times (safety cap).
    """
    sections: list[SectionResult] = []
    prev_hash: Optional[int] = None

    for i in range(SCROLL_MAX_ITERATIONS):
        ocr_result = run_ocr(rect)
        pairs = parse_pairs(ocr_result.lines) if ocr_result.success else {}
        sections.append(SectionResult(scroll_index=i, ocr=ocr_result, pairs=pairs))

        logger.debug(
            "Section {}: OCR success={}, lines={}, pairs={}, "
            "mean_conf={:.1f}",
            i,
            ocr_result.success,
            len(ocr_result.lines),
            len(pairs),
            ocr_result.mean_confidence,
        )

        # Scroll down
        _scroll_down(rect, SCROLL_CLICKS_PER_STEP)
        time.sleep(SCROLL_PAUSE_S)

        # Check whether the view changed
        current_hash = _capture_screenshot_hash(rect)
        if prev_hash is not None and current_hash == prev_hash:
            logger.info(
                "Scroll bottom reached after {} section(s) "
                "(content unchanged at step {}).",
                len(sections),
                i + 1,
            )
            break
        prev_hash = current_hash
    else:
        logger.warning(
            "Reached SCROLL_MAX_ITERATIONS ({}) — stopping scroll loop.",
            SCROLL_MAX_ITERATIONS,
        )

    return sections


def _merge_sections(sections: list[SectionResult]) -> tuple[dict[str, str], int]:
    """
    Merge all per-section pair dicts into one dictionary.
    Later sections overwrite earlier ones on key collision.

    Returns (merged_dict, count_of_overwrites).
    """
    merged: dict[str, str] = {}
    overwrites = 0

    for section in sections:
        for label, value in section.pairs.items():
            if label in merged:
                overwrites += 1
                logger.debug(
                    "Duplicate key '{}': overwriting '{}' → '{}'",
                    label, merged[label], value,
                )
            merged[label] = value

    return merged, overwrites


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def read_left_panel(tree: ControlInfo) -> ReadResult:
    """
    Entry point for Phase 3.

    1. Locate the left panel node in *tree*.
    2. Scroll through it, OCR-ing each visible section.
    3. Parse and merge all label/value pairs.
    4. Return a ReadResult with the merged data and full diagnostics.

    On failure (panel not found, OCR entirely empty) returns a ReadResult
    with success=False — never raises.
    """
    t0 = time.monotonic()

    # ── 1. Locate left panel ──────────────────────────────────────────────────
    panel_node = find_left_panel(tree)

    if panel_node is None:
        logger.error(
            "Left panel not detected — cannot read form data. "
            "Check ui_tree.json for panel structure."
        )
        return ReadResult(
            total_elapsed_s=time.monotonic() - t0,
            panel_found=False,
            success=False,
        )

    rect = panel_node.bounding_rect
    logger.info(
        "Starting left panel read: rect=({},{},{},{})  size={}x{}",
        rect.left, rect.top, rect.right, rect.bottom,
        rect.width, rect.height,
    )

    # ── 2. Scroll + OCR ───────────────────────────────────────────────────────
    sections = _read_sections(rect)

    # ── 3. Aggregate confidence ───────────────────────────────────────────────
    successful = [s for s in sections if s.ocr.success]
    mean_conf = (
        sum(s.ocr.mean_confidence for s in successful) / len(successful)
        if successful
        else 0.0
    )

    # ── 4. Merge ──────────────────────────────────────────────────────────────
    merged, overwrites = _merge_sections(sections)

    elapsed = time.monotonic() - t0

    # ── 5. Log summary ────────────────────────────────────────────────────────
    logger.info("── Left panel read summary ───────────────────")
    logger.info("  Sections read             : {}", len(sections))
    logger.info("  Sections with OCR text    : {}", len(successful))
    logger.info("  Fields extracted          : {}", len(merged))
    logger.info("  Duplicate keys overwritten: {}", overwrites)
    logger.info("  Mean OCR confidence       : {:.1f}", mean_conf)
    logger.info("  Total time                : {:.2f}s", elapsed)
    logger.info("─────────────────────────────────────────────")

    if not merged:
        logger.warning(
            "OCR returned no parseable label/value pairs. "
            "Check OCR confidence, Tesseract install, and panel detection."
        )
        return ReadResult(
            sections_read=len(sections),
            total_elapsed_s=elapsed,
            mean_confidence=mean_conf,
            panel_found=True,
            success=False,
        )

    return ReadResult(
        form_data=merged,
        sections_read=len(sections),
        total_fields=len(merged),
        duplicate_keys_overwritten=overwrites,
        total_elapsed_s=elapsed,
        mean_confidence=mean_conf,
        panel_found=True,
        success=True,
    )


def save_read_result(result: ReadResult) -> None:
    """
    Persist the ReadResult's form_data to output/form_data.json and .txt.
    Saves empty-dict files even when result.success is False so the output
    directory is always populated after a run.
    """
    save_form_data_json(result.form_data, FORM_DATA_JSON)
    save_form_data_txt(result.form_data, FORM_DATA_TXT)
