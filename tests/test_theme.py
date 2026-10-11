"""Every text colour must stay readable (WCAG AA) on the colours it sits on, light and dark."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import check_palette  # noqa: E402


def test_palette_passes_contrast(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["check_palette.py", os.path.join(ROOT, "ezcompare", "theme.py")])
    assert check_palette.main() == 0, capsys.readouterr().out
