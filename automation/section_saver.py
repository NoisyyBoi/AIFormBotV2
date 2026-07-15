"""
Phase 3.1 — OCR section image saver.

Responsibilities:
  - Save the raw (pre-preprocessing) PIL crop for each scroll step to
    debug/ocr_sections/section_NNN.png.
  - On the first call, also save a full-screen overlay PNG that draws the
    exact OCR rectangle so it can be visually audited.
  - Never raise — log errors and return.
  - Never modify OCR preprocessing.
"""

from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
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

def save_crop_overlay(rect: BoundingRect) -> None:
    """
    Capture a full-screen screenshot, draw the OCR rectangle on it,
    and save to debug/ocr_crop_overlay.png.

    Called once (on the first scroll step) so the user can visually confirm
    the crop region before reviewing individual section crops.
    """
    OCR_CROP_OVERLAY_PNG.parent.mkdir(parents=True, exist_ok=True)

    try:
        pil_img = ImageGrab.grab(all_screens=False)
        bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # Draw the OCR rect in bright cyan, thick enough to be visible
        cv2.rectangle(
            bgr,
            (rect.left, rect.top),
            (rect.right, rect.bottom),
            (255, 255, 0),   # BGR cyan
            3,
        )

        # Label the rect
        label = f"OCR crop  {rect.width}x{rect.height}px"
        cv2.putText(
            bgr,
            label,
            (rect.left + 4, max(rect.top - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 0),
            1,
            cv2.LINE_AA,
        )

        cv2.imwrite(str(OCR_CROP_OVERLAY_PNG), bgr)
        logger.info("OCR crop overlay saved → {}", OCR_CROP_OVERLAY_PNG)

    except Exception as exc:  # noqa: BLE001
        logger.error("Could not save crop overlay: {}", exc)
