"""
Central configuration for AIFormBotV2.
All constants live here — no magic strings scattered across the codebase.
"""

from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent.parent

# ── Output directories ────────────────────────────────────────────────────────
DEBUG_DIR: Path = BASE_DIR / "debug"
LOGS_DIR: Path = BASE_DIR / "logs"

# ── Target application ────────────────────────────────────────────────────────
APP_TITLE_SUBSTRING: str = "MPF Form Filling"
ROOT_CONTROL_NAME: str = "MPF (Form Filling Page)"

# ── Window discovery ──────────────────────────────────────────────────────────
WINDOW_FIND_TIMEOUT_S: float = 10.0   # seconds to poll before giving up
WINDOW_FIND_INTERVAL_S: float = 0.5   # polling interval

# ── UI inspection ─────────────────────────────────────────────────────────────
MAX_TREE_DEPTH: int = 50               # safety cap on recursion depth

# ── Phase 1 output file paths ─────────────────────────────────────────────────
UI_TREE_JSON: Path = DEBUG_DIR / "ui_tree.json"
UI_TREE_TXT: Path = DEBUG_DIR / "ui_tree.txt"
UI_OVERLAY_PNG: Path = DEBUG_DIR / "ui_overlay.png"

# ── Phase 1 overlay drawing ───────────────────────────────────────────────────
OVERLAY_RECT_COLOR: tuple[int, int, int] = (0, 255, 0)   # BGR green
OVERLAY_RECT_THICKNESS: int = 1
OVERLAY_FONT_SCALE: float = 0.35
OVERLAY_FONT_THICKNESS: int = 1
OVERLAY_LABEL_COLOR: tuple[int, int, int] = (0, 200, 255)  # BGR amber

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FILE: Path = LOGS_DIR / "aiformbot.log"
LOG_ROTATION: str = "10 MB"
LOG_RETENTION: str = "7 days"
LOG_LEVEL: str = "DEBUG"

# =============================================================================
# Phase 2 — Field Map
# =============================================================================

# ── Input control types to collect ───────────────────────────────────────────
INPUT_CONTROL_TYPES: frozenset[str] = frozenset(
    {
        "EditControl",
        "ComboBoxControl",
        "DateTimePickerControl",
        "ButtonControl",
    }
)

# ── TextControl type name used for label candidates ──────────────────────────
TEXT_CONTROL_TYPE: str = "TextControl"

# ── Label-search tolerance: how far LEFT (px) to look for a text label ───────
# A TextControl whose right edge falls within this many pixels to the left of
# the input control's left edge is considered a candidate label.
LABEL_SEARCH_X_TOLERANCE_PX: int = 400

# ── Label-search tolerance: vertical centre alignment (px) ───────────────────
# The vertical centre of the label and the input must be within this many
# pixels of each other to be considered on the same row.
LABEL_SEARCH_Y_TOLERANCE_PX: int = 20

# ── Phase 2 output file paths ─────────────────────────────────────────────────
CONTROL_MAP_JSON: Path = DEBUG_DIR / "control_map.json"
CONTROL_MAP_CSV: Path = DEBUG_DIR / "control_map.csv"
CONTROL_MAP_OVERLAY_PNG: Path = DEBUG_DIR / "control_map_overlay.png"

# ── Phase 2 overlay colors (BGR) ─────────────────────────────────────────────
# Keyed by the normalised control-type string stored on FieldEntry.
MAP_OVERLAY_COLORS: dict[str, tuple[int, int, int]] = {
    "EditControl":            (255, 100,   0),   # blue
    "ComboBoxControl":        (  0, 165, 255),   # orange
    "DateTimePickerControl":  (128,   0, 128),   # purple
    "ButtonControl":          (  0, 200,   0),   # green
}
MAP_OVERLAY_DEFAULT_COLOR: tuple[int, int, int] = (200, 200, 200)  # grey fallback
MAP_OVERLAY_RECT_THICKNESS: int = 2
MAP_OVERLAY_FONT_SCALE: float = 0.38
MAP_OVERLAY_FONT_THICKNESS: int = 1
MAP_OVERLAY_LABEL_COLOR: tuple[int, int, int] = (255, 255, 255)   # white text
