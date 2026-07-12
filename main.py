"""
AIFormBotV2 — Phase 1 entry point.

Execution flow:
  1. Connect to the MPF Form Filling window.
  2. Bring it to the foreground.
  3. Find the root panel 'MPF (Form Filling Page)'.
  4. Print window metadata to stdout.
  5. Recursively enumerate all descendants.
  6. Export control tree → debug/ui_tree.json and debug/ui_tree.txt.
  7. Capture screen and draw bounding-box overlay → debug/ui_overlay.png.
  8. Exit.
"""

import sys

from loguru import logger

from config.settings import (
    LOG_FILE,
    LOG_LEVEL,
    LOG_RETENTION,
    LOG_ROTATION,
    LOGS_DIR,
    DEBUG_DIR,
    UI_OVERLAY_PNG,
    UI_TREE_JSON,
    UI_TREE_TXT,
)
from ui.finder import bring_to_foreground, wait_for_window
from ui.inspector import find_root_panel, flatten_tree, inspect_tree
from automation.exporter import save_json, save_txt
from automation.overlay import save_overlay


# ── Logging setup ─────────────────────────────────────────────────────────────

def _configure_logging() -> None:
    """Remove the default sink and add a console + rotating file sink."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    logger.remove()  # drop default stderr sink

    logger.add(
        sys.stdout,
        level=LOG_LEVEL,
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )
    logger.add(
        LOG_FILE,
        level="DEBUG",
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
    )


# ── Phase steps ───────────────────────────────────────────────────────────────

def step_connect():
    """Step 1-2: Find window and bring to foreground."""
    window = wait_for_window()
    bring_to_foreground(window)
    logger.info("Connected to MPF")
    return window


def step_find_root(window):
    """Step 3-4: Find root panel and print its metadata."""
    root_panel = find_root_panel(window)

    rect = root_panel.BoundingRectangle
    print()
    print("=" * 60)
    print(f"  Window title     : {window.Name}")
    print(f"  AutomationId     : {root_panel.AutomationId or '(none)'}")
    print(
        f"  Bounding rect    : "
        f"({rect.left}, {rect.top}, {rect.right}, {rect.bottom})"
    )
    print("=" * 60)
    print()

    logger.info("Root panel found")
    return root_panel


def step_inspect(root_panel):
    """Step 5: Recursively enumerate all descendants."""
    tree = inspect_tree(root_panel)
    flat = flatten_tree(tree)
    logger.info("All controls exported  ({} total nodes)", len(flat))
    return tree


def step_export(tree) -> None:
    """Step 6: Save control tree to JSON and TXT."""
    save_json(tree, UI_TREE_JSON)
    save_txt(tree, UI_TREE_TXT)


def step_overlay(tree) -> None:
    """Step 7: Draw bounding-box overlay and save PNG."""
    save_overlay(tree, UI_OVERLAY_PNG)
    logger.info("Overlay image saved")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _configure_logging()
    logger.info("AIFormBotV2 Phase 1 starting.")

    try:
        window = step_connect()
        root_panel = step_find_root(window)
        tree = step_inspect(root_panel)
        step_export(tree)
        step_overlay(tree)
    except RuntimeError as exc:
        logger.error("Fatal: {}", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error: {}", exc)
        sys.exit(1)

    logger.info("Finished successfully")


if __name__ == "__main__":
    main()
