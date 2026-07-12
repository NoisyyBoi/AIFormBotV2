# AIFormBotV2 — Phase 1

Windows UI automation bot that inspects the **MPF Form Filling** desktop application,
exports the full control tree, and saves an annotated overlay screenshot.

---

## Requirements

- Windows 10 / 11
- Python 3.10+
- The **MPF Form Filling** application must be running before you start the bot.

---

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
```

---

## Usage

```bash
python main.py
```

### Expected console output

```
Connected to MPF
============================================================
  Window title     : MPF Form Filling — <version>
  AutomationId     : (none or actual id)
  Bounding rect    : (x1, y1, x2, y2)
============================================================
Root panel found
All controls exported  (N total nodes)
Overlay image saved
Finished successfully
```

---

## Output files

| File | Description |
|------|-------------|
| `debug/ui_tree.json` | Full nested control tree (JSON) |
| `debug/ui_tree.txt` | Human-readable indented text tree |
| `debug/ui_overlay.png` | Full-screen screenshot with bounding boxes drawn |
| `logs/aiformbot.log` | Rotating debug log |

---

## Project structure

```
AIFormBotV2/
├── main.py                  # Entry point
├── requirements.txt
├── config/
│   └── settings.py          # All constants and paths
├── ui/
│   ├── finder.py            # Window discovery + foreground
│   └── inspector.py         # Recursive control enumeration
├── automation/
│   ├── exporter.py          # JSON + TXT serialisation
│   └── overlay.py           # Screen capture + bounding-box drawing
├── debug/                   # Generated output (gitignored)
└── logs/                    # Rotating log files (gitignored)
```

---

## Phase 1 scope

Phase 1 **only** inspects and exports. It does **not**:

- Read or match any field values
- Write to any control
- Click any button
- Submit any form
- Scroll
- Use OCR

---

## Troubleshooting

**Window not found**
: Make sure **MPF Form Filling** is open and visible before running the bot.
  The bot polls for up to 10 seconds before giving up.

**Empty bounding rectangles**
: Some controls report zero-size rectangles when they are off-screen or hidden.
  These are still recorded in the JSON/TXT but are skipped in the overlay image.

**`uiautomation` access errors**
: Run your terminal / IDE **as Administrator** if the target app runs elevated.
