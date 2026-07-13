"""
AIFormBotV2 — entry point.

Phase 1 flow:
  1. Connect to the MPF Form Filling window.
  2. Bring it to the foreground.
  3. Find the root panel 'MPF (Form Filling Page)' (deep search, falls back
     to window root if missing).
  4. Print window metadata to stdout.
  5. Recursively enumerate all descendants.
  6. Export full control tree → debug/ui_tree.json and debug/ui_tree.txt.
  7. Capture screen and draw generic bounding-box overlay → debug/ui_overlay.png.

Phase 2 flow (runs immediately after Phase 1):
  8.  Build the field map — extract every input control and resolve its label.
  9.  Log type totals.
  10. Validate — duplicate ids, missing labels, duplicate labels.
  11. Export field map → debug/control_map.json and debug/control_map.csv.
  12. Save color-coded overlay → debug/control_map_overlay.png.

Phase 3 flow (runs immediately after Phase 2):
  13. Detect left information panel from the UI tree.
  14. Scroll through the entire panel, OCR-ing each visible section.
  15. Parse and merge all label/value pairs (latest value wins on duplicates).
  16. Save merged data → output/form_data.json and output/form_data.txt.
"""

import sys

from loguru import logger

from config.settings import (
    CONTROL_MAP_CSV,
    CONTROL_MAP_JSON,
    CONTROL_MAP_OVERLAY_PNG,
    DEBUG_DIR,
    FORM_DATA_JSON,
    FORM_DATA_TXT,
    LOG_FILE,
    LOG_LEVEL,
    LOG_RETENTION,
    LOG_ROTATION,
    LOGS_DIR,
    OUTPUT_DIR,
    ROOT_CONTROL_NAME,
    UI_OVERLAY_PNG,
    UI_TREE_JSON,
    UI_TREE_TXT,
)
from ui.finder import bring_to_foreground, wait_for_window
from ui.inspector import find_root_panel, flatten_tree, inspect_tree
from ui.field_mapper import build_field_map, log_totals
from automation.exporter import save_json, save_txt
from automation.overlay import save_overlay
from automation.map_exporter import save_map_json, save_map_csv
from automation.map_overlay import save_map_overlay
from automation.validator import validate_field_map
from automation.left_panel_reader import read_left_panel, save_read_result


# ── Logging setup ─────────────────────────────────────────────────────────────

def _configure_logging() -> None:
    """Remove the default sink and add a console + rotating file sink."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1 steps
# ══════════════════════════════════════════════════════════════════════════════

def step_connect():
    """Step 1-2: Find window and bring to foreground."""
    window = wait_for_window()
    bring_to_foreground(window)
    logger.info("Connected to MPF")
    return window


def step_find_root(window):
    """
    Step 3-4: Deep-search the full descendant tree for the expected root panel.

    If found   — use it as the inspection root and print its metadata.
    If missing — log a warning and fall back to the window itself so the
                 full tree is still exported (never terminates on missing panel).
    """
    root_panel = find_root_panel(window)

    if root_panel is None:
        logger.warning(
            "'{}' not found — exporting the entire window tree instead.",
            ROOT_CONTROL_NAME,
        )
        root_panel = window
    else:
        logger.info("Root panel found")

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

    return root_panel


def step_inspect(root_panel):
    """Step 5: Recursively enumerate all descendants."""
    tree = inspect_tree(root_panel)
    flat = flatten_tree(tree)
    logger.info("All controls exported  ({} total nodes)", len(flat))
    return tree


def step_export_tree(tree) -> None:
    """Step 6: Save full control tree to JSON and TXT."""
    save_json(tree, UI_TREE_JSON)
    save_txt(tree, UI_TREE_TXT)


def step_generic_overlay(tree) -> None:
    """Step 7: Draw generic bounding-box overlay and save PNG."""
    save_overlay(tree, UI_OVERLAY_PNG)
    logger.info("Overlay image saved")


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2 steps
# ══════════════════════════════════════════════════════════════════════════════

def step_build_field_map(tree):
    """Step 8-9: Extract input controls, resolve labels, log type totals."""
    entries = build_field_map(tree)
    log_totals(entries)
    return entries


def step_validate(entries) -> None:
    """Step 10: Validate field map — log warnings, never abort."""
    validate_field_map(entries)


def step_export_map(entries) -> None:
    """Step 11: Save field map to JSON and CSV."""
    save_map_json(entries, CONTROL_MAP_JSON)
    save_map_csv(entries, CONTROL_MAP_CSV)


def step_map_overlay(entries) -> None:
    """Step 12: Save color-coded control-map overlay PNG."""
    save_map_overlay(entries, CONTROL_MAP_OVERLAY_PNG)
    logger.info("Control map overlay saved")


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3 steps
# ══════════════════════════════════════════════════════════════════════════════

def step_read_left_panel(tree):
    """
    Step 13-15: Detect left panel, scroll + OCR, parse and merge all
    label/value pairs.  Never aborts the run — logs warnings on partial
    or empty results.
    """
    result = read_left_panel(tree)

    if not result.panel_found:
        logger.warning(
            "Phase 3: left panel not detected — "
            "form_data files will be empty."
        )
    elif not result.success:
        logger.warning(
            "Phase 3: OCR produced no parseable pairs — "
            "form_data files will be empty. "
            "Verify Tesseract is installed and TESSERACT_CMD is correct."
        )
    else:
        logger.info(
            "Phase 3 complete: {} fields read in {:.2f}s "
            "(mean OCR confidence {:.1f}).",
            result.total_fields,
            result.total_elapsed_s,
            result.mean_confidence,
        )

    return result


def step_save_form_data(result) -> None:
    """Step 16: Persist form data to output/form_data.json and .txt."""
    save_read_result(result)
    logger.info(
        "Form data saved → {}  and  {}",
        FORM_DATA_JSON,
        FORM_DATA_TXT,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    _configure_logging()
    logger.info("AIFormBotV2 starting.")

    try:
        # ── Phase 1 ───────────────────────────────────────────────────────────
        window     = step_connect()
        root_panel = step_find_root(window)
        tree       = step_inspect(root_panel)
        step_export_tree(tree)
        step_generic_overlay(tree)

        # ── Phase 2 ───────────────────────────────────────────────────────────
        entries = step_build_field_map(tree)
        step_validate(entries)
        step_export_map(entries)
        step_map_overlay(entries)

        # ── Phase 3 ───────────────────────────────────────────────────────────
        result = step_read_left_panel(tree)
        step_save_form_data(result)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error: {}", exc)
        sys.exit(1)

    logger.info("Finished successfully")


if __name__ == "__main__":
    main()
