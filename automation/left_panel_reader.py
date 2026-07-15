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

import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional

import win32api
import win32con
from loguru import logger
from PIL import ImageGrab

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


def _sha256_of_region(rect: BoundingRect) -> str:
    """
    Capture the screen region defined by *rect* and return its SHA-256 hex
    digest.  Using SHA-256 of raw PNG bytes eliminates false positives that
    plagued the old integer-sum approach.
    """
    img = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom),
        all_screens=False,
    )
    # tobytes() gives the raw pixel buffer — fast and deterministic.
    return hashlib.sha256(img.tobytes()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# Core read loop
# ══════════════════════════════════════════════════════════════════════════════

# Number of consecutive identical hashes that signals the bottom of the panel.
_REPEAT_THRESHOLD: int = 3


def _read_sections(rect: BoundingRect) -> tuple[list[SectionResult], str]:
    """
    Scroll through the panel at *rect* from top to bottom.

    Termination conditions (whichever fires first):
      A. Pre-scroll hash == post-scroll hash on the same step
         (panel did not move at all after scrolling).
      B. The same hash has appeared _REPEAT_THRESHOLD consecutive times
         (panel is stuck / already at bottom for several steps).
      C. SCROLL_MAX_ITERATIONS is exhausted (safety cap).

    Returns (sections, stop_reason_string).
    """
    sections: list[SectionResult] = []
    recent_hashes: list[str] = []   # rolling window of post-scroll hashes
    stop_reason: str = f"SCROLL_MAX_ITERATIONS ({SCROLL_MAX_ITERATIONS}) reached"

    for i in range(SCROLL_MAX_ITERATIONS):

        # ── OCR the current view ──────────────────────────────────────────────
        ocr_result = run_ocr(rect)
        pairs = parse_pairs(ocr_result.lines) if ocr_result.success else {}
        sections.append(SectionResult(scroll_index=i, ocr=ocr_result, pairs=pairs))

        logger.debug(
            "Section {}: OCR success={}, lines={}, pairs={}, mean_conf={:.1f}",
            i,
            ocr_result.success,
            len(ocr_result.lines),
            len(pairs),
            ocr_result.mean_confidence,
        )

        # ── Hash the panel BEFORE scrolling ───────────────────────────────────
        hash_before = _sha256_of_region(rect)

        # ── Scroll one step down ──────────────────────────────────────────────
        _scroll_down(rect, SCROLL_CLICKS_PER_STEP)
        time.sleep(SCROLL_PAUSE_S)

        # ── Hash the panel AFTER scrolling ────────────────────────────────────
        hash_after = _sha256_of_region(rect)

        # ── Termination check A: same step, before == after ───────────────────
        if hash_before == hash_after:
            stop_reason = "Image hash unchanged (before == after scroll)"
            logger.info(
                "Bottom detected.  Reason: {}  |  "
                "Sections read: {}  |  Fields extracted: {}",
                stop_reason,
                len(sections),
                sum(len(s.pairs) for s in sections),
            )
            break

        # ── Termination check B: same hash repeated N times in a row ──────────
        recent_hashes.append(hash_after)
        if len(recent_hashes) > _REPEAT_THRESHOLD:
            recent_hashes.pop(0)

        if (
            len(recent_hashes) == _REPEAT_THRESHOLD
            and len(set(recent_hashes)) == 1
        ):
            stop_reason = (
                f"Same hash repeated {_REPEAT_THRESHOLD} consecutive times"
            )
            logger.info(
                "Bottom detected.  Reason: {}  |  "
                "Sections read: {}  |  Fields extracted: {}",
                stop_reason,
                len(sections),
                sum(len(s.pairs) for s in sections),
            )
            break

    else:
        # Loop exhausted SCROLL_MAX_ITERATIONS without an early break.
        logger.warning(
            "Bottom detected.  Reason: {}  |  "
            "Sections read: {}  |  Fields extracted: {}",
            stop_reason,
            len(sections),
            sum(len(s.pairs) for s in sections),
        )

    return sections, stop_reason


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
    sections, stop_reason = _read_sections(rect)

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
    logger.info("  Stop reason               : {}", stop_reason)
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

    Always writes both files — even when result.success is False or
    form_data is empty — so the output directory is always populated
    after every run and callers can inspect what (if anything) was captured.
    """
    save_form_data_json(result.form_data, FORM_DATA_JSON)
    save_form_data_txt(result.form_data, FORM_DATA_TXT)
