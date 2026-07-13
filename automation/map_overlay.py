"""
Phase 2 — Color-coded field-map overlay.

Responsibilities:
  - Capture a fresh full-screen screenshot.
  - Draw a colored rectangle around each input control.
      Blue   = EditControl
      Orange = ComboBoxControl
      Purple = DateTimePickerControl
      Green  = ButtonControl
  - Print the resolved label beside each rectangle.
  - Save to debug/control_map_overlay.png.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab
from loguru import logger

from config.settings import (
    MAP_OVERLAY_COLORS,
    MAP_OVERLAY_DEFAULT_COLOR,
    MAP_OVERLAY_FONT_SCALE,
    MAP_OVERLAY_FONT_THICKNESS,
    MAP_OVERLAY_LABEL_COLOR,
    MAP_OVERLAY_RECT_THICKNESS,
)
from ui.field_mapper import FieldEntry
from ui.inspector import BoundingRect


# ── Screen capture ────────────────────────────────────────────────────────────

def _grab_screen() -> np.ndarray:
    """Return a BGR numpy array of the full primary display."""
    pil_image = ImageGrab.grab(all_screens=False)
    rgb_array = np.array(pil_image)
    return cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _has_valid_rect(rect: BoundingRect) -> bool:
    return rect.width > 0 and rect.height > 0


def _color_for(control_type: str) -> tuple[int, int, int]:
    return MAP_OVERLAY_COLORS.get(control_type, MAP_OVERLAY_DEFAULT_COLOR)


def _draw_entry(image: np.ndarray, entry: FieldEntry) -> None:
    """Draw one colored rectangle and its label onto *image* in place."""
    r = entry.bounding_rect
    color = _color_for(entry.control_type)

    # rectangle
    cv2.rectangle(
        image,
        (r.left, r.top),
        (r.right, r.bottom),
        color,
        MAP_OVERLAY_RECT_THICKNESS,
    )

    # label text — prefer resolved label, fall back to automation_id
    display_text = entry.label if entry.label else entry.automation_id
    label_x = r.left + 2
    label_y = max(r.top - 4, 10)

    # thin dark shadow for readability on any background
    cv2.putText(
        image,
        display_text,
        (label_x + 1, label_y + 1),
        cv2.FONT_HERSHEY_SIMPLEX,
        MAP_OVERLAY_FONT_SCALE,
        (0, 0, 0),
        MAP_OVERLAY_FONT_THICKNESS + 1,
        cv2.LINE_AA,
    )
    # foreground text
    cv2.putText(
        image,
        display_text,
        (label_x, label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        MAP_OVERLAY_FONT_SCALE,
        MAP_OVERLAY_LABEL_COLOR,
        MAP_OVERLAY_FONT_THICKNESS,
        cv2.LINE_AA,
    )


def _draw_legend(image: np.ndarray) -> None:
    """Draw a color legend in the top-left corner of the image."""
    legend = [
        ("Edit",         MAP_OVERLAY_COLORS["EditControl"]),
        ("ComboBox",     MAP_OVERLAY_COLORS["ComboBoxControl"]),
        ("DatePicker",   MAP_OVERLAY_COLORS["DateTimePickerControl"]),
        ("Button",       MAP_OVERLAY_COLORS["ButtonControl"]),
    ]
    x0, y0, box_w, box_h, pad = 8, 8, 12, 12, 4
    font = cv2.FONT_HERSHEY_SIMPLEX

    for i, (label, color) in enumerate(legend):
        y = y0 + i * (box_h + pad)
        cv2.rectangle(image, (x0, y), (x0 + box_w, y + box_h), color, -1)
        cv2.putText(
            image,
            label,
            (x0 + box_w + 4, y + box_h - 2),
            font,
            0.35,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )


# ── Public API ────────────────────────────────────────────────────────────────

def save_map_overlay(entries: list[FieldEntry], path: Path) -> None:
    """
    Capture the screen, annotate every FieldEntry with its type-specific
    color and label, and save the result to *path*.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug("Capturing screen for control-map overlay.")
    image = _grab_screen()

    drawn = 0
    skipped = 0

    for entry in entries:
        if _has_valid_rect(entry.bounding_rect):
            _draw_entry(image, entry)
            drawn += 1
        else:
            skipped += 1
            logger.debug(
                "Skipping zero-rect control: {} '{}'",
                entry.control_type,
                entry.automation_id,
            )

    _draw_legend(image)
    cv2.imwrite(str(path), image)

    logger.info(
        "Control map overlay saved → {}  ({} drawn, {} skipped)",
        path,
        drawn,
        skipped,
    )
