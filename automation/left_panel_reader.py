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
    SCROLL_DEBUG_LEFT_AFTER,
    SCROLL_DEBUG_LEFT_BEFORE,
    SCROLL_DEBUG_RIGHT_AFTER,
    SCROLL_DEBUG_RIGHT_BEFORE,
    SCROLL_MAX_ITERATIONS,
    SCROLL_PAUSE_S,
)
from automation.crop_region import compute_content_rect
from automation.form_data_exporter import save_form_data_json, save_form_data_txt
from automation.ocr_engine import OcrResult, run_ocr
from automation.section_saver import save_crop_overlay, save_section_crop
from ui.inspector import BoundingRect, ControlInfo
from ui.panel_locator import find_left_panel, find_scroll_target


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
    """Return the (x, y) screen coordinate of a rect's centre."""
    return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2


def _scroll_down(target_rect: BoundingRect, clicks: int) -> None:
    """
    Send a mouse-wheel scroll-down event positioned at the centre of
    *target_rect*.  Uses win32api — no button clicks are generated.

    The caller is responsible for passing the SCROLL TARGET rect, not the
    panel rect or the OCR rect.  This guarantees the wheel event lands on
    the correct control.
    """
    cx, cy = _panel_centre(target_rect)
    win32api.SetCursorPos((cx, cy))
    delta = -120 * clicks   # negative = scroll down
    win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, cx, cy, delta, 0)


def _save_debug_image(rect: BoundingRect, path) -> None:
    """
    Capture the screen region *rect* and save it to *path*.
    Silently logs errors — never raises.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = ImageGrab.grab(
            bbox=(rect.left, rect.top, rect.right, rect.bottom),
            all_screens=False,
        )
        img.save(str(path))
        logger.debug("Debug image saved → {}", path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not save debug image {}: {}", path, exc)


def _right_panel_rect(
    scroll_rect: BoundingRect,
    root_rect: BoundingRect,
) -> BoundingRect:
    """
    Derive an approximate bounding rect for the right panel.
    Used only for saving side-by-side debug images — never scrolled.
    The right panel is assumed to occupy the right half of *root_rect*
    at the same vertical extent as *scroll_rect*.
    """
    mid = (root_rect.left + root_rect.right) // 2
    return BoundingRect(
        left=mid,
        top=scroll_rect.top,
        right=root_rect.right,
        bottom=scroll_rect.bottom,
    )


def _sha256_of_region(rect: BoundingRect) -> str:
    """
    Capture the screen region *rect* and return its SHA-256 hex digest.
    Using SHA-256 of raw pixel bytes gives collision-free change detection.
    """
    img = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom),
        all_screens=False,
    )
    return hashlib.sha256(img.tobytes()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# Core read loop
# ══════════════════════════════════════════════════════════════════════════════

# Number of consecutive identical hashes that signals the bottom of the panel.
_REPEAT_THRESHOLD: int = 3


def _read_sections(
    scroll_rect: BoundingRect,
    scroll_target_rect: BoundingRect,
    ocr_rect: BoundingRect,
    root_rect: BoundingRect,
) -> tuple[list[SectionResult], str]:
    """
    Scroll through the left panel from top to bottom.

    Parameters
    ----------
    scroll_rect        Full left-panel rect — used for SHA-256 change detection
                       and the left-pane debug images.
    scroll_target_rect Innermost scrollable container rect — the ONLY rect the
                       wheel event is sent to.  Always strictly inside the left
                       half of root_rect.
    ocr_rect           Tight content crop — used for OCR and section PNGs.
    root_rect          Root panel rect — used to derive the right-panel rect
                       for debug images.

    Termination (first that fires):
      A. Pre-scroll hash == post-scroll hash  (panel did not move).
      B. Same hash _REPEAT_THRESHOLD consecutive times  (stuck at bottom).
      C. SCROLL_MAX_ITERATIONS exhausted  (safety cap).
    """
    sections: list[SectionResult] = []
    recent_hashes: list[str] = []
    stop_reason: str = f"SCROLL_MAX_ITERATIONS ({SCROLL_MAX_ITERATIONS}) reached"
    right_rect = _right_panel_rect(scroll_rect, root_rect)

    for i in range(SCROLL_MAX_ITERATIONS):

        # ── Save overlay once for visual audit ────────────────────────────────
        if i == 0:
            save_crop_overlay(ocr_rect)

        # ── Save raw crop for this scroll position ────────────────────────────
        save_section_crop(ocr_rect, i)

        # ── OCR the tight content region ──────────────────────────────────────
        ocr_result = run_ocr(ocr_rect)
        pairs = parse_pairs(ocr_result.lines) if ocr_result.success else {}
        sections.append(SectionResult(scroll_index=i, ocr=ocr_result, pairs=pairs))

        logger.debug(
            "Section {}: OCR success={}, lines={}, pairs={}, mean_conf={:.1f}",
            i, ocr_result.success,
            len(ocr_result.lines), len(pairs), ocr_result.mean_confidence,
        )

        # ── Capture before-scroll debug images ───────────────────────────────
        _save_debug_image(scroll_rect, SCROLL_DEBUG_LEFT_BEFORE)
        _save_debug_image(right_rect,  SCROLL_DEBUG_RIGHT_BEFORE)

        # ── Hash the LEFT panel BEFORE scrolling ──────────────────────────────
        hash_before = _sha256_of_region(scroll_rect)

        # ── Scroll the correct (left) target only ─────────────────────────────
        _scroll_down(scroll_target_rect, SCROLL_CLICKS_PER_STEP)
        time.sleep(SCROLL_PAUSE_S)

        # ── Capture after-scroll debug images ────────────────────────────────
        _save_debug_image(scroll_rect, SCROLL_DEBUG_LEFT_AFTER)
        _save_debug_image(right_rect,  SCROLL_DEBUG_RIGHT_AFTER)

        # ── Hash the LEFT panel AFTER scrolling ───────────────────────────────
        hash_after = _sha256_of_region(scroll_rect)

        # ── Verify left pane actually moved ───────────────────────────────────
        if hash_before == hash_after:
            stop_reason = "Image hash unchanged (before == after scroll)"
            logger.warning("Left pane did not move after scroll.")
            logger.info(
                "Bottom detected.  Reason: {}  |  "
                "Sections read: {}  |  Fields extracted: {}",
                stop_reason, len(sections),
                sum(len(s.pairs) for s in sections),
            )
            break

        # ── Termination check B: same hash N times in a row ───────────────────
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
                stop_reason, len(sections),
                sum(len(s.pairs) for s in sections),
            )
            break

    else:
        logger.warning(
            "Bottom detected.  Reason: {}  |  "
            "Sections read: {}  |  Fields extracted: {}",
            stop_reason, len(sections),
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

    # ── 2. Derive tight content crop rect ────────────────────────────────────
    ocr_rect = compute_content_rect(panel_node)
    logger.info(
        "OCR crop rect: ({},{},{},{})  size={}x{}",
        ocr_rect.left, ocr_rect.top, ocr_rect.right, ocr_rect.bottom,
        ocr_rect.width, ocr_rect.height,
    )

    # ── 3. Find the innermost scrollable container in the left half ───────────
    scroll_target = find_scroll_target(panel_node, tree.bounding_rect)

    # ── 4. Scroll + OCR ───────────────────────────────────────────────────────
    sections, stop_reason = _read_sections(
        scroll_rect=rect,
        scroll_target_rect=scroll_target.bounding_rect,
        ocr_rect=ocr_rect,
        root_rect=tree.bounding_rect,
    )

    # ── 5. Aggregate confidence ───────────────────────────────────────────────
    successful = [s for s in sections if s.ocr.success]
    mean_conf = (
        sum(s.ocr.mean_confidence for s in successful) / len(successful)
        if successful
        else 0.0
    )

    # ── 6. Merge ──────────────────────────────────────────────────────────────
    merged, overwrites = _merge_sections(sections)

    elapsed = time.monotonic() - t0

    # ── 7. Log summary ────────────────────────────────────────────────────────
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
