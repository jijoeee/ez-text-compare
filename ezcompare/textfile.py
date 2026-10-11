"""Read a text file (or pasted text) into lines, whatever its encoding.

No UI imports. Every expected failure is a CompareError with a sentence the
user can act on.
"""

from __future__ import annotations

import codecs
import os
import re
from dataclasses import dataclass
from typing import Optional

# Bigger than this is almost certainly not a file anyone wants to read side by side,
# and holding two of them in a text widget would make the window crawl.
MAX_FILE_MB = 50


class CompareError(Exception):
    """The comparison can't run or can't be saved. ``str(exc)`` is shown to the user as is."""


@dataclass(frozen=True)
class TextSource:
    """One side of the comparison: where it came from and its lines."""

    name: str                   # file name, or "Pasted text"
    path: Optional[str]         # None for pasted text
    lines: tuple[str, ...]
    encoding: str = "UTF-8"
    line_ending: str = ""       # "Windows (CRLF)", "Unix (LF)", "Mixed" or "" (one line, or pasted)
    size: int = 0               # bytes on disk; characters for pasted text
    modified: Optional[float] = None

    @property
    def pasted(self) -> bool:
        return self.path is None


# Friendly names for the encodings detect_encoding() returns.
_ENCODING_NAMES = {
    "utf-8": "UTF-8",
    "utf-8-sig": "UTF-8 with BOM",
    "utf-16": "UTF-16",
    "utf-16-le": "UTF-16 LE",
    "utf-16-be": "UTF-16 BE",
    "cp1252": "Windows-1252",
}


def detect_encoding(head: bytes) -> str:
    """Pick the encoding of a text file from its first bytes.

    Windows tools write UTF-16 (PowerShell output, some exported logs), Notepad
    writes UTF-8, older programs and many network devices write Windows-1252 or
    plain ASCII. Getting this wrong makes every line look different.
    """
    if head.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    if b"\x00" in head:
        # UTF-16 saved without a BOM: every other byte of plain text is zero.
        half = max(1, len(head) // 2)
        zeros_even, zeros_odd = head[0::2].count(0), head[1::2].count(0)
        if zeros_odd > half * 0.6 and zeros_even < half * 0.1:
            return "utf-16-le"
        if zeros_even > half * 0.6 and zeros_odd < half * 0.1:
            return "utf-16-be"
        raise CompareError("binary")
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


def line_ending_of(text: str) -> str:
    """Describe the line endings, so "every line is different" has an explanation."""
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    kinds = [name for name, count in (("Windows (CRLF)", crlf), ("Unix (LF)", lf), ("Old Mac (CR)", cr))
             if count]
    if len(kinds) > 1:
        return "Mixed"
    return kinds[0] if kinds else ""


_NEWLINE = re.compile(r"\r\n|\r|\n")


def split_lines(text: str) -> tuple[str, ...]:
    """Lines without their endings. A final newline does not make an extra empty line.

    Only CR, LF and CRLF end a line. str.splitlines() also splits on form feeds and
    other control characters, which would put our line numbers out of step with
    Notepad and every other editor.
    """
    if not text:
        return ()
    lines = _NEWLINE.split(text)
    if lines[-1] == "":
        lines.pop()
    return tuple(lines)


def read_text_file(path: str) -> TextSource:
    """Read a whole text file. Raises CompareError with a reason the user understands."""
    name = os.path.basename(path) or path
    try:
        info = os.stat(path)
        if os.path.isdir(path):
            raise CompareError(f"{name} is a folder. Drop or choose a text file.")
        if info.st_size > MAX_FILE_MB * 1024 * 1024:
            raise CompareError(f"{name} is larger than {MAX_FILE_MB} MB. Split it, or compare a "
                               "smaller part of it.")
        with open(path, "rb") as f:
            data = f.read()
    except CompareError:
        raise
    except FileNotFoundError:
        raise CompareError(f"{name} can't be found. It may have been moved or renamed.") from None
    except PermissionError:
        raise CompareError(f"{name} can't be opened. Close it if another program has it locked, "
                           "or check you have permission to read it.") from None
    except OSError as exc:
        raise CompareError(f"{name} can't be read: {exc.strerror or 'disk error'}.") from None

    try:
        encoding = detect_encoding(data[:65536])
    except CompareError:
        raise CompareError(f"{name} is not a text file (it contains binary data). "
                           "EZ Text Compare compares text, log and config files.") from None
    text = data.decode(encoding, errors="replace")
    return TextSource(
        name=name, path=os.path.abspath(path), lines=split_lines(text),
        encoding=_ENCODING_NAMES.get(encoding, encoding), line_ending=line_ending_of(text),
        size=info.st_size, modified=info.st_mtime,
    )


def text_from_string(text: str, name: str = "Pasted text") -> TextSource:
    """Text pasted from the clipboard, e.g. command output copied out of a terminal."""
    return TextSource(name=name, path=None, lines=split_lines(text), encoding="",
                      line_ending="", size=len(text), modified=None)
