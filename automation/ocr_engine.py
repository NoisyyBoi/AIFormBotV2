"""
Phase 3 — OCR engine (Tesseract via pytesseract).

Responsibilities:
  - Capture an arbitrary screen region defined by a BoundingRect.
  - Pre-process the captured image for better OCR accuracy
    (grayscale → mild sharpen → threshold).
  - Run pytesseract and return structured results:
      * Raw text lines (non-empty only).
      * Per-word confidence values (mean + minimum).
  - Never raise on OCR failure — return an empty OcrResult and log the error.

Tesseract installation note (Windows):
  Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki
  Default path: C:\\Program Files\\Tesseract-OCR\\tesseract.exe
  Set TESSERACT_CMD in config/settings.py if installed elsewhere.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytesseract
from PIL import ImageGrab
from loguru import logger

from config.settings import (
    OCR_CONFIDENCE_THRESHOLD,
    OCR_SCALE_FACTOR,
    TESSERACT_CMD,
    TESSERACT_CONFIG,
)
from ui.inspector import BoundingRect

# Point pytesseract at the correct executable.
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


# ── Result model ──────────────────────────────────────────────────────────────

@dataclass
class OcrResult:
    lines: list[str] = field(default_factory=list)      # non-blank text lines
    mean_confidence: float = 0.0                         # 0–100
    min_confidence: float = 0.0                          # lowest word confidence
    elapsed_s: float = 0.0
    success: bool = False


# ── Image capture ─────────────────────────────────────────────────────────────

def _capture_region(rect: BoundingRect) -> np.ndarray:
    """
    Screenshot the screen region defined by *rect*.
    Returns a BGR numpy array.
    """
    pil_img = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom),
        all_screens=False,
    )
    rgb = np.array(pil_img)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


# ── Pre-processing ────────────────────────────────────────────────────────────

def _preprocess(image: np.ndarray) -> np.ndarray:
    """
    Prepare *image* for Tesseract:
      1. Upscale by OCR_SCALE_FACTOR (improves recognition of small text).
      2. Convert to grayscale.
      3. Mild unsharp-mask sharpening.
      4. Adaptive thresholding to binary.
    """
    # 1. Upscale
    if OCR_SCALE_FACTOR != 1.0:
        h, w = image.shape[:2]
        image = cv2.resize(
            image,
            (int(w * OCR_SCALE_FACTOR), int(h * OCR_SCALE_FACTOR)),
            interpolation=cv2.INTER_CUBIC,
        )

    # 2. Grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 3. Sharpen
    blurred = cv2.GaussianBlur(gray, (0, 0), 3)
    sharpened = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)

    # 4. Adaptive threshold
    binary = cv2.adaptiveThreshold(
        sharpened,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15,
        C=8,
    )
    return binary


# ── Confidence extraction ─────────────────────────────────────────────────────

def _confidence_stats(data: dict) -> tuple[float, float]:
    """
    Extract mean and minimum word confidence from pytesseract image_to_data output.
    Returns (mean_conf, min_conf). Both are 0.0 when no valid words exist.
    """
    confs = [
        int(c)
        for c in data.get("conf", [])
        if str(c).lstrip("-").isdigit() and int(c) >= 0
    ]
    if not confs:
        return 0.0, 0.0
    return float(sum(confs) / len(confs)), float(min(confs))


# ── Public API ────────────────────────────────────────────────────────────────

def run_ocr(rect: BoundingRect) -> OcrResult:
    """
    Capture the screen region *rect*, pre-process, and run Tesseract OCR.

    Returns an OcrResult.  On any error (Tesseract not installed, empty image,
    etc.) returns an OcrResult with success=False and logs the failure.
    """
    t0 = time.monotonic()

    try:
        raw_image = _capture_region(rect)
        processed = _preprocess(raw_image)

        # Run OCR for structured confidence data
        data = pytesseract.image_to_data(
            processed,
            config=TESSERACT_CONFIG,
            output_type=pytesseract.Output.DICT,
        )
        mean_conf, min_conf = _confidence_stats(data)

        # Run OCR again for clean plain text
        raw_text: str = pytesseract.image_to_string(
            processed,
            config=TESSERACT_CONFIG,
        )

        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        elapsed = time.monotonic() - t0

        if not lines:
            logger.warning(
                "OCR returned no text for region ({},{},{},{}) in {:.2f}s.",
                rect.left, rect.top, rect.right, rect.bottom, elapsed,
            )
            return OcrResult(elapsed_s=elapsed, success=False)

        logger.debug(
            "OCR: {} lines, mean_conf={:.1f}, min_conf={:.1f}, elapsed={:.2f}s "
            "for region ({},{},{},{}).",
            len(lines), mean_conf, min_conf, elapsed,
            rect.left, rect.top, rect.right, rect.bottom,
        )

        # Warn if overall confidence is low
        if mean_conf < OCR_CONFIDENCE_THRESHOLD:
            logger.warning(
                "OCR mean confidence {:.1f} is below threshold {}.",
                mean_conf, OCR_CONFIDENCE_THRESHOLD,
            )

        return OcrResult(
            lines=lines,
            mean_confidence=mean_conf,
            min_confidence=min_conf,
            elapsed_s=elapsed,
            success=True,
        )

    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        logger.error(
            "OCR failed for region ({},{},{},{}) after {:.2f}s: {}",
            rect.left, rect.top, rect.right, rect.bottom, elapsed, exc,
        )
        return OcrResult(elapsed_s=elapsed, success=False)
