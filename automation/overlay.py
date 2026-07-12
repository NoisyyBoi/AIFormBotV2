"""
Capture the screen and draw bounding-rectangle overlays for every control.

Responsibilities:
  - Take a full-screen screenshot using Pillow.
  - Draw a labelled rectangle for every visible ControlInfo node.
  - Save the annotated image to debug/ui_overlay.png.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab
from loguru import logger

from config.settings import (
    OVERLAY_FONT_SCALE,
    OVERLAY_FONT_THICKNESS,
    OVERLAY_LABEL_COLOR,
    OVERLAY_RECT_COLOR,
    OVERLAY_RECT_THICKNESS,
)
from ui.inspector import ControlInfo, flatten_tree


def _grab_screen() -> np.ndarray:
    """Capture the entire primary display and return a BGR numpy array."""
    pil_image = ImageGrab.grab(all_screens=False)
    rgb_array = np.array(pil_image)
    bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
    return bgr_array


def _has_valid_rect(node: ControlInfo) -> bool:
    """Return True only when the bounding rectangle has positive area."""
    r = node.bounding_rect
    return r.width > 0 and r.height > 0


def _draw_rect(image: np.ndarray, node: ControlInfo) -> None:
    """Draw one labelled rectangle onto *image* in place."""
    r = node.bounding_rect
    top_left = (r.left, r.top)
    bottom_right = (r.right, r.bottom)

    cv2.rectangle(image, top_left, bottom_right, OVERLAY_RECT_COLOR, OVERLAY_RECT_THICKNESS)

    label = f"{node.control_type}:{node.name}" if node.name else node.control_type
    label_pos = (r.left + 2, max(r.top - 3, 8))  # just above the top edge
    cv2.putText(
        image,
        label,
        label_pos,
        cv2.FONT_HERSHEY_SIMPLEX,
        OVERLAY_FONT_SCALE,
        OVERLAY_LABEL_COLOR,
        OVERLAY_FONT_THICKNESS,
        cv2.LINE_AA,
    )


def save_overlay(root: ControlInfo, path: Path) -> None:
    """
    Screenshot the screen, annotate every control bounding box,
    and save the result to *path*.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug("Capturing screen for overlay image.")
    image = _grab_screen()

    all_controls = flatten_tree(root)
    drawn = 0

    for node in all_controls:
        if _has_valid_rect(node):
            _draw_rect(image, node)
            drawn += 1

    cv2.imwrite(str(path), image)
    logger.info(
        "Overlay image saved → {}  ({}/{} controls drawn)",
        path,
        drawn,
        len(all_controls),
    )
