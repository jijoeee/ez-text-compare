# EZ Text Compare — source

Compare two text, log or config files and see which lines were added, removed or changed.
Offline. Free, MIT licence. The public tool page is `../README.md`.

## Build the Windows installer

1. Install **Python 3.12 64-bit** from python.org (3.13 also works) and, for the installer,
   **Inno Setup** (free): https://jrsoftware.org/isdl.php
2. Double-click **`build.bat`**. It makes a clean `.venv`, installs the pinned packages, runs the
   tests (the build stops if any fail), builds the app and the installer.
3. In `dist\` you get:
   - `EZ-Text-Compare-Setup-1.0.0.exe` — the installer to publish
   - `EZ-Text-Compare-1.0.0-portable.zip` — the no-install version
   - `sandbox-test.wsb` — double-click to test on a clean Windows Sandbox
   - the SHA-256 of each file is printed at the end

Then work through `RELEASE_CHECKLIST.md` and `ANTIVIRUS.md`.

## Run from source

```bat
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python main.py                 & rem or: main.py before.txt after.txt
.venv\Scripts\python -m pytest -q
python check_palette.py ezcompare\theme.py   & rem 42/42 must pass
```

## Layout

```
main.py                 entry point: logging, crash handler, up to two file arguments
ezcompare/
  __init__.py           version and identity (the only place the version lives)
  textfile.py           reading a file: encoding, line endings, binary and size checks. No UI.
  engine.py             the comparison: unordered and ordered, pairing, moves, character diffs. No UI.
  export.py             the Excel report. No UI.
  tools.py              the compare screen: panes, options, navigation, export
  widgets.py            buttons, drop zone, result panel, file slot, diff pane
  app.py                main window, header, status bar, keys, theme, About
  theme.py              colours (raspberry 320, plus the diff colours), fonts, icons
  system.py             paths, settings, logging, Explorer, window icon
tests/                  pytest: engine, files and report, palette contrast
assets/                 app.ico, logo.png, drop_orb.png, icons/ (already generated)
brand/                  logo master + mark font
installer/installer.iss Inno Setup script (AppId never changes)
```

`assets/` is already generated. Only re-run the generators if the icons change:
`python make_icons.py` then `python make_assets.py --mark CMP --hue 320 --glyph compare`.

Settings and logs: `%APPDATA%\EZKerja\EZ Text Compare\`.

## How the comparison works (for the course)

`engine.compare()` turns each line into a *key* (the line after every Ignore option), then:

- **Ignore line order:** identical keys are matched wherever they are (a count per key, so
  duplicates are handled). Leftovers are paired by similarity with `difflib.SequenceMatcher`,
  a nearby line winning a close call. Over 60,000 similarity checks, each line is only
  compared with lines in a similar place, so the worst case stays bounded.
- **Line order matters:** common start and end are matched directly, `SequenceMatcher` aligns
  the middle, and inside each block where both sides differ, similar lines are lined up as
  "changed". Removed lines that reappear unchanged elsewhere become "moved".
- Changed lines are compared again word by word for the character highlight.
