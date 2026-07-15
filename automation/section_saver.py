"""
Phase 3.1 — OCR section image saver.

Responsibilities:
  - Save the raw (pre-preprocessing) PIL crop for each scroll step to
    debug/ocr_sections/section_NNN.png.
  - On the first call, also save a full-screen overlay PNG that draws both
    the original OCR rectangle and the bottom-cropped rectangle so the
    active capture region can be visually audited.
  - Never raise — log errors and return.
  - Never modify OCR preprocessing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import ImageGrab
from loguru import logger

from config.settings import (
    OCR_CROP_OVERLAY_PNG,
    OCR_SECTIONS_DIR,
)
from ui.inspector import BoundingRect


# ── Section crop saver ────────────────────────────────────────────────────────

def save_section_crop(rect: BoundingRect, index: int) -> None:
    """
    Capture the screen region *rect* and save it as
    debug/ocr_sections/section_NNN.png.

    *index* is the zero-based scroll iteration number.
    *rect* must already be the CROPPED rect (timer excluded).
    """
    OCR_SECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    filename = OCR_SECTIONS_DIR / f"section_{index:03d}.png"

    try:
        img = ImageGrab.grab(
            bbox=(rect.left, rect.top, rect.right, rect.bottom),
            all_screens=False,
        )
        img.save(str(filename))
        logger.debug("Section crop saved → {}", filename)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not save section crop {}: {}", filename, exc)


# ── Crop overlay saver ────────────────────────────────────────────────────────

def save_crop_overlay(
    original_rect: BoundingRect,
    cropped_rect: Optional[BoundingRect] = None,
) -> None:
    """
    Capture a full-screen screenshot and draw the OCR rectangles on it.

    - *original_rect* (cyan)  — the full OCR region before bottom-crop.
    - *cropped_rect*  (green) — the active region actually used for OCR,
                                hashing, and debug screenshots.
                                Omitted when equal to original_rect.

    Saved to debug/ocr_crop_overlay.png.
    """
    OCR_CROP_OVERLAY_PNG.parent.mkdir(parents=True, exist_ok=True)

    try:
        pil_img = ImageGrab.grab(all_screens=False)
        bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # Draw original OCR rect — cyan, thin
        cv2.rectangle(
            bgr,
            (original_rect.left, original_rect.top),
            (original_rect.right, original_rect.bottom),
            (255, 255, 0),  # BGR cyan
            2,
        )
        cv2.putText(
            bgr,
            f"OCR region  {original_rect.width}x{original_rect.height}px",
            (original_rect.left + 4, max(original_rect.top - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45,
            (255, 255, 0), 1, cv2.LINE_AA,
        )

        # Draw cropped rect — bright green, thicker, only when different
        if cropped_rect is not None and cropped_rect != original_rect:
            cv2.rectangle(
                bgr,
                (cropped_rect.left, cropped_rect.top),
                (cropped_rect.right, cropped_rect.bottom),
                (0, 255, 0),  # BGR green
                3,
            )
            cv2.putText(
                bgr,
                f"Active crop  {cropped_rect.width}x{cropped_rect.height}px",
                (cropped_rect.left + 4, cropped_rect.bottom + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 255, 0), 1, cv2.LINE_AA,
            )

        cv2.imwrite(str(OCR_CROP_OVERLAY_PNG), bgr)
        logger.info("OCR crop overlay saved → {}", OCR_CROP_OVERLAY_PNG)

    except Exception as exc:  # noqa: BLE001
        logger.error("Could not save crop overlay: {}", exc)
