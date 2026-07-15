"""
Phase 3 — Left Panel Reader.

Responsibilities:
  - Detect the left information panel from the existing ControlInfo tree.
  - Scroll through the entire panel one step at a time using click-to-focus
    + mouse-wheel input (no UIA ScrollPattern required).
  - OCR each visible section.
  - Parse every OCR result into label/value pairs.
  - Merge all sections into one dictionary (latest value wins on duplicate keys).
  - Return a ReadResult containing the merged data and rich diagnostics.

Scroll strategy
  For each scroll step:
    1. Hash the OCR region BEFORE scrolling.
    2. Try each click position in SCROLL_CLICK_POSITIONS (centre, 35%, 65%,
       near scrollbar edge).
    3. For every position: click-to-focus + fire all wheel methods
       (pyautogui, SendInput, win32api).
    4. Hash AFTER.  If changed → scroll succeeded, move to next section.
    5. If no position produced a hash change → consecutive_failures += 1.
    6. Stop after SCROLL_MAX_CONSECUTIVE_FAILURES consecutive failed cycles.

This module does NOT:
  - Use UI Automation ScrollPattern.
  - Use heuristic pane scoring.
  - Type into any control.
  - Interact with the right panel.
  - Submit or modify the form.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger
from PIL import ImageGrab

from config.settings import (
    FORM_DATA_JSON,
    FORM_DATA_TXT,
    LABEL_MAX_LENGTH,
    LABEL_MIN_LENGTH,
    LABEL_VALUE_SEPARATORS,
    OCR_BOTTOM_CROP_PERCENT,
    SCROLL_CLICK_POSITIONS,
    SCROLL_CLICKS_PER_STEP,
    SCROLL_FAIL_DEBUG_DIR,
    SCROLL_MAX_CONSECUTIVE_FAILURES,
    SCROLL_MAX_ITERATIONS,
    SCROLL_PAUSE_S,
)
from automation.crop_region import compute_content_rect
from automation.form_data_exporter import save_form_data_json, save_form_data_txt
from automation.ocr_engine import OcrResult, run_ocr
from automation.section_saver import save_crop_overlay, save_section_crop
from automation.wheel_scroller import click_and_scroll
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
    mean_confidence: float = 0.0
    panel_found: bool = False
    success: bool = False


# ══════════════════════════════════════════════════════════════════════════════
# Label / value parser  (unchanged)
# ══════════════════════════════════════════════════════════════════════════════

def _split_line(line: str) -> Optional[tuple[str, str]]:
    for sep in LABEL_VALUE_SEPARATORS:
        if sep in line:
            label, _, value = line.partition(sep)
            label = label.strip()
            value = value.strip()
            if LABEL_MIN_LENGTH <= len(label) <= LABEL_MAX_LENGTH:
                return label, value
    return None


def parse_pairs(lines: list[str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for line in lines:
        result = _split_line(line)
        if result is not None:
            label, value = result
            pairs[label] = value
    return pairs


# ══════════════════════════════════════════════════════════════════════════════
# Image / hash helpers
# ══════════════════════════════════════════════════════════════════════════════

def _sha256_of_region(rect: BoundingRect) -> str:
    """SHA-256 of the raw pixel bytes of *rect* — collision-free change detection."""
    img = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom),
        all_screens=False,
    )
    return hashlib.sha256(img.tobytes()).hexdigest()


def _save_image(rect: BoundingRect, path: Path) -> None:
    """Capture *rect* and save to *path*. Logs errors, never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = ImageGrab.grab(
            bbox=(rect.left, rect.top, rect.right, rect.bottom),
            all_screens=False,
        )
        img.save(str(path))
        logger.debug("Debug image → {}", path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not save debug image {}: {}", path, exc)


# ══════════════════════════════════════════════════════════════════════════════
# Bottom crop — strips Shift Details / countdown timer
# ══════════════════════════════════════════════════════════════════════════════

def _apply_bottom_crop(rect: BoundingRect) -> BoundingRect:
    """
    Discard the bottom OCR_BOTTOM_CROP_PERCENT of *rect*.

    This removes the Shift Details section and countdown timer so they cannot
    contaminate OCR output or cause false-positive hash changes.

    Returns a new BoundingRect with the same left/top/right but a reduced
    bottom edge.  If the crop would produce zero or negative height the
    original rect is returned unchanged with a warning.
    """
    pixels_to_remove = int(rect.height * OCR_BOTTOM_CROP_PERCENT)
    new_bottom = rect.bottom - pixels_to_remove

    if new_bottom <= rect.top:
        logger.warning(
            "Bottom crop of {:.0%} would eliminate the entire rect — "
            "keeping original rect ({},{},{},{}).",
            OCR_BOTTOM_CROP_PERCENT,
            rect.left, rect.top, rect.right, rect.bottom,
        )
        return rect

    return BoundingRect(
        left=rect.left,
        top=rect.top,
        right=rect.right,
        bottom=new_bottom,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Click position resolution
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_click_positions(rect: BoundingRect) -> list[tuple[int, int]]:
    """
    Convert SCROLL_CLICK_POSITIONS fractional coordinates into absolute
    (x, y) screen pixels within *rect*.
    """
    positions: list[tuple[int, int]] = []
    for fx, fy in SCROLL_CLICK_POSITIONS:
        x = int(rect.left + fx * rect.width)
        y = int(rect.top  + fy * rect.height)
        positions.append((x, y))
    return positions


# ══════════════════════════════════════════════════════════════════════════════
# Single-step scroll: try every click position until hash changes
# ══════════════════════════════════════════════════════════════════════════════

def _attempt_scroll_step(
    ocr_rect: BoundingRect,
    step_index: int,
    hash_before: str,
) -> tuple[bool, str]:
    """
    Try to scroll the left panel by one step, cycling through all configured
    click positions until the OCR-region hash changes.

    Returns (scrolled: bool, hash_after: str).
    Saves a debug image for every position that fails.
    """
    click_positions = _resolve_click_positions(ocr_rect)

    for pos_idx, (cx, cy) in enumerate(click_positions):
        attempt = click_and_scroll(cx, cy, SCROLL_CLICKS_PER_STEP)
        time.sleep(SCROLL_PAUSE_S)

        hash_after = _sha256_of_region(ocr_rect)

        logger.debug(
            "Scroll step {} pos [{}/{}] at ({},{}) — "
            "pyautogui={} SendInput={} win32={} — "
            "hash_before={:.8} hash_after={:.8} changed={}",
            step_index,
            pos_idx + 1,
            len(click_positions),
            cx, cy,
            attempt["pyautogui_ok"],
            attempt["sendinput_ok"],
            attempt["win32_fallback_ok"],
            hash_before,
            hash_after,
            hash_before != hash_after,
        )

        if hash_before != hash_after:
            logger.debug(
                "Scroll step {} succeeded at position [{}/{}] ({},{}).",
                step_index, pos_idx + 1, len(click_positions), cx, cy,
            )
            return True, hash_after

        # Save failure debug image
        fail_path = SCROLL_FAIL_DEBUG_DIR / f"step{step_index:03d}_pos{pos_idx}.png"
        _save_image(ocr_rect, fail_path)
        logger.debug(
            "Scroll step {} pos [{}/{}] failed — saved {}",
            step_index, pos_idx + 1, len(click_positions), fail_path,
        )

    # All positions exhausted — hash still unchanged
    return False, hash_before


# ══════════════════════════════════════════════════════════════════════════════
# Core read loop
# ══════════════════════════════════════════════════════════════════════════════

def _read_sections(
    ocr_rect: BoundingRect,
    original_rect: BoundingRect,
) -> tuple[list[SectionResult], str]:
    """
    Scroll through the left panel from top to bottom, OCR-ing each view.

    Parameters
    ----------
    ocr_rect      Cropped rect (Shift Details / timer stripped).
                  Used for OCR, SHA-256 hashing, debug screenshots, and
                  click-position resolution.
    original_rect Full rect before bottom crop — passed to save_crop_overlay
                  so the overlay shows both rectangles.

    Termination conditions (first that fires):
      A. All SCROLL_CLICK_POSITIONS failed to change the hash for
         SCROLL_MAX_CONSECUTIVE_FAILURES consecutive full cycles → bottom reached.
      B. SCROLL_MAX_ITERATIONS exhausted (safety cap).
    """
    sections: list[SectionResult] = []
    consecutive_failures: int = 0
    stop_reason = f"SCROLL_MAX_ITERATIONS ({SCROLL_MAX_ITERATIONS}) reached"

    for i in range(SCROLL_MAX_ITERATIONS):

        # ── Save overlay on first iteration (shows both rects) ────────────────
        if i == 0:
            save_crop_overlay(original_rect, ocr_rect)

        # ── Save raw crop for this position (cropped rect only) ───────────────
        save_section_crop(ocr_rect, i)

        # ── OCR ───────────────────────────────────────────────────────────────
        ocr_result = run_ocr(ocr_rect)
        pairs = parse_pairs(ocr_result.lines) if ocr_result.success else {}
        sections.append(SectionResult(scroll_index=i, ocr=ocr_result, pairs=pairs))

        logger.debug(
            "Section {}: OCR success={} lines={} pairs={} mean_conf={:.1f}",
            i, ocr_result.success,
            len(ocr_result.lines), len(pairs), ocr_result.mean_confidence,
        )

        # ── Hash BEFORE scroll ────────────────────────────────────────────────
        hash_before = _sha256_of_region(ocr_rect)

        # ── Attempt scroll — try all click positions ──────────────────────────
        scrolled, hash_after = _attempt_scroll_step(ocr_rect, i, hash_before)

        if scrolled:
            consecutive_failures = 0
            logger.debug("Step {}: scroll confirmed (hash changed).", i)
        else:
            consecutive_failures += 1
            logger.warning(
                "Step {}: left pane did not move after scroll "
                "(all {} positions tried, consecutive_failures={}/{}).",
                i,
                len(SCROLL_CLICK_POSITIONS),
                consecutive_failures,
                SCROLL_MAX_CONSECUTIVE_FAILURES,
            )

            if consecutive_failures >= SCROLL_MAX_CONSECUTIVE_FAILURES:
                stop_reason = (
                    f"Bottom reached — {consecutive_failures} consecutive "
                    f"full-cycle scroll failures (all positions exhausted)"
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
        logger.warning(
            "Bottom detected.  Reason: {}  |  "
            "Sections read: {}  |  Fields extracted: {}",
            stop_reason,
            len(sections),
            sum(len(s.pairs) for s in sections),
        )

    return sections, stop_reason


# ══════════════════════════════════════════════════════════════════════════════
# Merge
# ══════════════════════════════════════════════════════════════════════════════

def _merge_sections(sections: list[SectionResult]) -> tuple[dict[str, str], int]:
    """Merge all per-section pairs; latest value wins on key collision."""
    merged: dict[str, str] = {}
    overwrites = 0
    for section in sections:
        for label, value in section.pairs.items():
            if label in merged:
                overwrites += 1
                logger.debug(
                    "Duplicate key '{}': '{}' → '{}'",
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

    1. Locate the left panel node in the ControlInfo snapshot.
    2. Derive the tight OCR crop rect.
    3. Scroll + OCR using click-to-focus wheel input.
    4. Parse and merge all label/value pairs.
    5. Return a ReadResult with full diagnostics.

    Never raises — returns ReadResult(success=False) on any fatal error.
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
        "Left panel: rect=({},{},{},{})  size={}x{}",
        rect.left, rect.top, rect.right, rect.bottom,
        rect.width, rect.height,
    )

    # ── 2. Derive tight OCR crop rect ─────────────────────────────────────────
    ocr_rect = compute_content_rect(panel_node)
    logger.info(
        "Original OCR rect : ({},{},{},{})  size={}x{}",
        ocr_rect.left, ocr_rect.top, ocr_rect.right, ocr_rect.bottom,
        ocr_rect.width, ocr_rect.height,
    )

    # ── 2b. Strip bottom section (Shift Details / countdown timer) ────────────
    active_rect = _apply_bottom_crop(ocr_rect)
    logger.info(
        "Cropped OCR rect  : ({},{},{},{})  size={}x{}  "
        "(bottom {:.0%} removed, hash image {}x{}px)",
        active_rect.left, active_rect.top,
        active_rect.right, active_rect.bottom,
        active_rect.width, active_rect.height,
        OCR_BOTTOM_CROP_PERCENT,
        active_rect.width, active_rect.height,
    )
    logger.info("Crop percentage   : {:.0%}", OCR_BOTTOM_CROP_PERCENT)

    # ── 3. Scroll + OCR ───────────────────────────────────────────────────────
    # active_rect is used for OCR, SHA-256 hashing, and debug screenshots.
    # ocr_rect is passed to save_crop_overlay only so the overlay shows both.
    sections, stop_reason = _read_sections(active_rect, ocr_rect)

    # ── 4. Aggregate confidence ───────────────────────────────────────────────
    successful = [s for s in sections if s.ocr.success]
    mean_conf = (
        sum(s.ocr.mean_confidence for s in successful) / len(successful)
        if successful else 0.0
    )

    # ── 5. Merge ──────────────────────────────────────────────────────────────
    merged, overwrites = _merge_sections(sections)
    elapsed = time.monotonic() - t0

    # ── 6. Log summary ────────────────────────────────────────────────────────
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
            "OCR returned no parseable pairs. "
            "Check Tesseract install and panel detection."
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
    Always writes output/form_data.json and output/form_data.txt —
    even when result.success is False — so outputs are always present.
    """
    save_form_data_json(result.form_data, FORM_DATA_JSON)
    save_form_data_txt(result.form_data, FORM_DATA_TXT)
