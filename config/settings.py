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

# ── Output file paths ─────────────────────────────────────────────────────────
UI_TREE_JSON: Path = DEBUG_DIR / "ui_tree.json"
UI_TREE_TXT: Path = DEBUG_DIR / "ui_tree.txt"
UI_OVERLAY_PNG: Path = DEBUG_DIR / "ui_overlay.png"

# ── Overlay drawing ───────────────────────────────────────────────────────────
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
