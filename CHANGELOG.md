# Changelog

## 1.0.0 — not released yet

First version, built to the EZKerja tool standard from EZ File Searcher's source.

**Compare**
- Two text, log or config files side by side. Drop both at once: the older file goes on
  the left. Or open, or paste text from the clipboard, one side at a time.
- **Ignore line order** (default): a line counts as the same wherever it is in the other
  file. Leftover lines are paired with a similar line on the other side as "changed", the
  nearby one winning when two are about equally similar; the rest are "only in left" or
  "only in right".
- **Line order matters**: a classic side-by-side diff with gaps, both sides scrolling
  together, and optional moved-line detection.
- Changed characters highlighted word by word (10.1.1.1 → 10.1.1.25 marks "1" → "25").
- Click a changed or moved line to show the line it pairs with.

- Nothing is compared until you click **Compare** (F5 or Ctrl+Enter). Loading files, pasting,
  swapping or changing an option never starts a comparison; Compare reads both files from disk again.
- **Reset** clears both files and the result. The options are kept.
- **Only compare lines containing** a text (not case sensitive): every other line is left out,
  shown greyed and not counted.

**Ignore**
- Empty lines, changes in spaces, all spaces, upper and lower case, dates and times
  (ISO, syslog, Cisco-style and plain clock times), and any regular expression.
  Ignored text is never highlighted.

**Navigate and report**
- Next / previous / first / last difference: buttons, F3 / Shift+F3, Alt+Up / Alt+Down.
- Show only differences.
- Summary: lines only in left, only in right, changed, moved, the same. Notes when line
  endings or encodings differ, which are not counted as differences.
- Export to Excel: one row per difference with both sides, plus a summary sheet.
  Lines starting with "=" are stored as text, never as formulas.

**Reliability**
- Reads UTF-8, UTF-8 with BOM, UTF-16 (with or without BOM) and Windows-1252. Refuses
  binary files and files over 50 MB with a clear message.
- Line numbers match Notepad: only CR, LF and CRLF end a line.
- Comparison runs off the UI thread, with a Stop button. Pairing similar lines has a fixed
  budget, so two large files where every line differs still finish (measured: two
  20,000-line logs, every line different, 16 s on an Orange Pi; 1 s when timestamps are ignored).
- EZKerja look: light and dark mode, Segoe UI, raspberry 320°, CMP icon, status bar.
- Settings remembered; log in `%APPDATA%\EZKerja\EZ Text Compare\logs`.
- Installer without admin rights, and a portable zip. No file associations and no
  Explorer right-click menu.
