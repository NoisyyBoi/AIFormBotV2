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

# =============================================================================
# Phase 3 — Left Panel Reader
# =============================================================================

# ── Output directory and files ────────────────────────────────────────────────
OUTPUT_DIR: Path = BASE_DIR / "output"
FORM_DATA_JSON: Path = OUTPUT_DIR / "form_data.json"
FORM_DATA_TXT: Path = OUTPUT_DIR / "form_data.txt"

# ── Tesseract ─────────────────────────────────────────────────────────────────
# Default Windows install path. Change if Tesseract is installed elsewhere.
TESSERACT_CMD: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Tesseract page-segmentation mode:
#   --psm 6  = Assume a single uniform block of text  (good for form panels)
#   --oem 3  = Default engine (LSTM + legacy)
TESSERACT_CONFIG: str = "--psm 6 --oem 3"

# ── OCR quality ───────────────────────────────────────────────────────────────
# Scale factor applied to the captured image before OCR (>1 upscales).
OCR_SCALE_FACTOR: float = 2.0

# Mean word confidence below this value triggers a warning log (0–100).
OCR_CONFIDENCE_THRESHOLD: float = 50.0

# ── Scroll behaviour ──────────────────────────────────────────────────────────
# Number of wheel clicks sent per scroll step.
SCROLL_CLICKS_PER_STEP: int = 3

# Pause (seconds) after each scroll step to let the panel repaint.
SCROLL_PAUSE_S: float = 0.4

# Maximum scroll iterations before giving up (safety cap).
SCROLL_MAX_ITERATIONS: int = 100

# ── Label / value parsing ─────────────────────────────────────────────────────
# Separator patterns tried in order when splitting a line into label : value.
# Each entry is a plain string that is split on once (from the left).
LABEL_VALUE_SEPARATORS: list[str] = [":", "=", "\t"]

# Minimum label length (chars) — shorter strings are discarded as noise.
LABEL_MIN_LENGTH: int = 2

# Maximum label length (chars) — longer strings are treated as plain text, not labels.
LABEL_MAX_LENGTH: int = 60
