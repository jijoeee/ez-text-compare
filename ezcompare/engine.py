"""Comparison logic: which lines were removed, added, changed or moved.

No UI imports, so this module is reusable from a command line, a paid tier or
a lesson. The UI calls ``compare()`` from a worker thread.

Two ways to compare, chosen by ``CompareOptions.ignore_order``:

* **Ignore line order** (the default). Each file is treated as a set of lines.
  A line is "the same" if the other file has it anywhere. What is left over is
  either *changed* (a similar line exists on the other side, for example the
  same interface with a new IP address) or *only in one file*. This answers
  "what is different between these two logs or configs" even when lines moved
  around, which a classic diff reports as a wall of red and green.

* **Line order matters**. A classic side-by-side diff, like the Compare plugin
  in Notepad++ or WinMerge: the two files are lined up, with an empty gap where
  one side has lines the other doesn't. Optionally detects lines that moved.

Every line keeps its real line number, so "line 42" in the app is line 42 in
the file.
"""

from __future__ import annotations

import bisect
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from .textfile import CompareError, TextSource

Cancel = Optional[threading.Event]

# Line kinds. FILLER is the empty gap opposite an added or removed line (ordered view only).
SAME = "same"
REMOVED = "removed"      # only in the left file
ADDED = "added"          # only in the right file
CHANGED = "changed"      # a similar line is on the other side; ``spans`` mark what differs
MOVED = "moved"          # the same line is on the other side, somewhere else (ordered view)
IGNORED = "ignored"      # left out: an empty line, or one without the "only lines containing" text
FILLER = "filler"

DIFF_KINDS = frozenset({REMOVED, ADDED, CHANGED, MOVED})

# Two lines count as "changed" rather than "removed + added" when at least this much of
# them is the same. 0.6 pairs "ip address 10.1.1.1 255.255.255.0" with "...10.1.1.2 ..."
# but not "shutdown" with "description uplink".
DEFAULT_SIMILARITY = 0.6

# Pairing similar lines compares leftover lines with each other, and one comparison of two
# similar log lines costs about 0.2 ms on a slow PC. This many comparisons at most per run
# (about 10 s on a Raspberry Pi class machine, a few seconds on an office laptop). Above
# it, each line is only compared with the lines nearest to its own position.
PAIRING_BUDGET = 60_000
# When two candidates are about equally similar, the one in a similar place in its file
# wins: "description Printers" pairs with "description Printers and scanners" three
# lines away, not with "description Cameras" at the other end of the file. A line at
# the opposite end costs 0.25 of similarity.
POSITION_WEIGHT = 0.25
SIMILARITY_CHARS = 400      # long lines: similarity is judged on the first 400 characters

# Above this many lines in the part that differs, the ordered diff lets difflib skip very
# common lines while matching (autojunk). Exact, just less tidy around repeated lines.
AUTOJUNK_FROM = 20_000

# "Ignore timestamps": the date and time formats found in network device and server logs.
#   2026-10-11 09:12:33.120   2026-10-11T09:12:33Z   Oct 11 09:12:33   Oct 11 2026 09:12:33
#   *Mar  1 00:01:02.345:     11/10/2026 09:12:33    09:12:33.120
TIMESTAMP_PATTERN = (
    r"\b\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:\s+\d{4})?\s+"
    r"\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?"
    r"|\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}[ T]\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?"
    r"|\b\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?\b"
)

_TOKEN = re.compile(r"\w+|\s+|[^\w\s]")


# ================================================================ data
@dataclass(frozen=True)
class CompareOptions:
    ignore_order: bool = True
    detect_moves: bool = True          # ordered view only
    char_diffs: bool = True            # highlight the characters that changed
    ignore_empty: bool = False
    ignore_changed_spaces: bool = False   # "a  b " equals "a b"
    ignore_all_spaces: bool = False       # "a b" equals "ab"
    ignore_case: bool = False
    ignore_timestamps: bool = False    # dates and times, see TIMESTAMP_PATTERN
    ignore_pattern: str = ""           # regular expression; matching text is not compared
    only_containing: str = ""          # compare only lines containing this text (any case)
    similarity: float = DEFAULT_SIMILARITY


DEFAULT_OPTIONS = CompareOptions()


@dataclass
class Line:
    """One row of one side of the comparison."""

    kind: str
    number: Optional[int]               # 1-based line number in its file; None for FILLER
    text: str = ""
    spans: tuple[tuple[int, int], ...] = ()   # character ranges that differ (CHANGED lines)
    partner: Optional[int] = None       # index of the matching row on the other side


@dataclass(frozen=True)
class Block:
    """A run of differences, for Next / Previous navigation. Row indices, either may be None."""

    left: Optional[int]
    right: Optional[int]
    kind: str


@dataclass
class CompareResult:
    left: list[Line]
    right: list[Line]
    aligned: bool                       # True: row i on the left sits next to row i on the right
    blocks: list[Block] = field(default_factory=list)
    removed: int = 0                    # lines only in the left file
    added: int = 0                      # lines only in the right file
    changed: int = 0                    # pairs of similar lines
    moved: int = 0                      # pairs of identical lines in different places
    same: int = 0                       # pairs of identical lines
    ignored: int = 0                    # lines skipped by an Ignore option (both files)
    pairing_limited: bool = False       # too many differences to compare every pair
    seconds: float = 0.0

    @property
    def differences(self) -> int:
        """Lines that differ, counting a changed or moved pair once."""
        return self.removed + self.added + self.changed + self.moved

    @property
    def identical(self) -> bool:
        return self.differences == 0


# ================================================================ normalising
def build_ignore_pattern(text: str, timestamps: bool = False) -> Optional[re.Pattern]:
    """Compile the text to ignore: the user's pattern, timestamps, or both.

    Raises CompareError saying what is wrong with a pattern that doesn't compile.
    """
    parts = []
    if text.strip():
        try:
            re.compile(text)
        except re.error as exc:
            where = f" (at character {exc.pos + 1})" if exc.pos is not None else ""
            raise CompareError(f"The ignore pattern has a mistake: {exc.msg}{where}.") from None
        parts.append(f"(?:{text})")
    if timestamps:
        parts.append(f"(?:{TIMESTAMP_PATTERN})")
    return re.compile("|".join(parts)) if parts else None


def make_key(text: str, options: CompareOptions, pattern: Optional[re.Pattern]) -> str:
    """The version of a line that is actually compared, after every Ignore option."""
    key = pattern.sub("", text) if pattern else text
    if options.ignore_all_spaces:
        key = "".join(key.split())
    elif options.ignore_changed_spaces:
        key = " ".join(key.split())
    if options.ignore_case:
        key = key.casefold()
    return key


def _keys(source: TextSource, options: CompareOptions,
          pattern: Optional[re.Pattern]) -> tuple[list[str], list[bool]]:
    keys = [make_key(t, options, pattern) for t in source.lines]
    skip = [options.ignore_empty and not k.strip() for k in keys]
    wanted = options.only_containing.strip().casefold()
    if wanted:
        # Every line without the text is left out, so only those lines are compared.
        skip = [s or wanted not in t.casefold() for s, t in zip(skip, source.lines)]
    return keys, skip


# ================================================================ similarity
def similarity(a: str, b: str) -> float:
    """0.0 (nothing alike) to 1.0 (identical), judged on the first few hundred characters."""
    a, b = a[:SIMILARITY_CHARS], b[:SIMILARITY_CHARS]
    if not a and not b:
        return 1.0
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    return matcher.ratio()


def _similar_enough(a: str, b: str, threshold: float) -> float:
    """The similarity if it reaches ``threshold``, else 0. Cheap upper bounds first."""
    a, b = a[:SIMILARITY_CHARS], b[:SIMILARITY_CHARS]
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
        return 0.0
    ratio = matcher.ratio()
    return ratio if ratio >= threshold else 0.0


def pair_similar(left: list[tuple[int, str]], right: list[tuple[int, str]], threshold: float,
                 cancel: Cancel = None, left_total: int = 0,
                 right_total: int = 0) -> tuple[list[tuple[int, int]], bool]:
    """Match leftover lines that are similar, regardless of where they are.

    ``left`` and ``right`` are (index, key) lists; ``left_total`` and ``right_total`` are
    the files' line counts, used to compare positions (line 10 of 20 is "halfway").
    Returns (pairs of indices, limited), best matches first; each line is used at most
    once. ``limited`` is True when there were too many lines to compare every pair, so
    each line was only compared with lines in a similar place in the other file.
    """
    if not left or not right:
        return [], False
    n_left = max(left_total or left[-1][0] + 1, 1)
    n_right = max(right_total or right[-1][0] + 1, 1)
    right_rel = [(j, kj, j / n_right) for j, kj in right]
    limited = len(left) * len(right) > PAIRING_BUDGET
    # Within budget: every pair. Over it: the ``near`` lines closest in position.
    near = max(1, PAIRING_BUDGET // len(left)) if limited else len(right)
    positions = [rel for _j, _kj, rel in right_rel]
    candidates: list[tuple[float, float, int, int]] = []
    for count, (i, ki) in enumerate(left):
        if cancel is not None and count % 200 == 0 and cancel.is_set():
            return [], False
        rel_i = i / n_left
        if limited:
            centre = bisect.bisect_left(positions, rel_i)
            lo = max(0, centre - near // 2 - 1)
            group = right_rel[lo:lo + near + 1]
        else:
            group = right_rel
        for j, kj, rel_j in group:
            score = _similar_enough(ki, kj, threshold)
            if score:
                distance = abs(rel_i - rel_j)
                candidates.append((score - POSITION_WEIGHT * distance, -distance, i, j))

    candidates.sort(reverse=True)
    used_left: set[int] = set()
    used_right: set[int] = set()
    pairs = []
    for _score, _closeness, i, j in candidates:
        if i not in used_left and j not in used_right:
            used_left.add(i)
            used_right.add(j)
            pairs.append((i, j))
    return pairs, limited


# ================================================================ character differences
def _subtract(spans: list[tuple[int, int]], holes: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove the ``holes`` (ignored text) from ``spans``."""
    for h0, h1 in holes:
        out = []
        for s0, s1 in spans:
            if s1 <= h0 or s0 >= h1:
                out.append((s0, s1))
                continue
            if s0 < h0:
                out.append((s0, h0))
            if s1 > h1:
                out.append((h1, s1))
        spans = out
    return spans


def char_spans(a: str, b: str, options: CompareOptions = DEFAULT_OPTIONS,
               pattern: Optional[re.Pattern] = None) -> tuple[tuple[tuple[int, int], ...],
                                                              tuple[tuple[int, int], ...]]:
    """The character ranges that differ between two similar lines.

    Compared word by word rather than letter by letter, so 10.1.1.1 -> 10.1.1.25
    highlights "1" -> "25" instead of a scatter of single characters. Text hidden
    by an Ignore option is never highlighted.
    """
    ta, tb = _TOKEN.findall(a), _TOKEN.findall(b)

    def norm(tok: str) -> str:
        if tok.isspace() and (options.ignore_changed_spaces or options.ignore_all_spaces):
            return " "
        return tok.casefold() if options.ignore_case else tok

    def offsets(tokens: list[str]) -> list[int]:
        pos, out = 0, []
        for tok in tokens:
            out.append(pos)
            pos += len(tok)
        out.append(pos)
        return out

    oa, ob = offsets(ta), offsets(tb)
    matcher = SequenceMatcher(None, [norm(t) for t in ta], [norm(t) for t in tb], autojunk=False)
    sa: list[tuple[int, int]] = []
    sb: list[tuple[int, int]] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if i2 > i1:
            sa.append((oa[i1], oa[i2]))
        if j2 > j1:
            sb.append((ob[j1], ob[j2]))
    if pattern is not None:
        sa = _subtract(sa, [m.span() for m in pattern.finditer(a)])
        sb = _subtract(sb, [m.span() for m in pattern.finditer(b)])
    if options.ignore_changed_spaces or options.ignore_all_spaces:
        sa = [s for s in sa if a[s[0]:s[1]].strip()]
        sb = [s for s in sb if b[s[0]:s[1]].strip()]
    return tuple(sa), tuple(sb)


# ================================================================ compare
def compare(left: TextSource, right: TextSource, options: CompareOptions = DEFAULT_OPTIONS,
            cancel: Cancel = None) -> CompareResult:
    """Compare two texts. Raises CompareError for a bad option; returns None-free results."""
    started = time.perf_counter()
    pattern = build_ignore_pattern(options.ignore_pattern, options.ignore_timestamps)
    lkeys, lskip = _keys(left, options, pattern)
    rkeys, rskip = _keys(right, options, pattern)
    if options.ignore_order:
        result = _compare_unordered(left, right, lkeys, rkeys, lskip, rskip, options, cancel)
    else:
        result = _compare_ordered(left, right, lkeys, rkeys, lskip, rskip, options, cancel)
    if cancel is not None and cancel.is_set():
        raise CompareError("Comparison stopped.")
    if options.char_diffs:
        _add_char_spans(result, options, pattern)
    _count(result)
    result.blocks = _blocks(result)
    result.seconds = time.perf_counter() - started
    return result


def _compare_unordered(left: TextSource, right: TextSource, lkeys: list[str], rkeys: list[str],
                       lskip: list[bool], rskip: list[bool], options: CompareOptions,
                       cancel: Cancel) -> CompareResult:
    lines_l = [Line(IGNORED if lskip[i] else REMOVED, i + 1, t) for i, t in enumerate(left.lines)]
    lines_r = [Line(IGNORED if rskip[j] else ADDED, j + 1, t) for j, t in enumerate(right.lines)]

    # 1. Identical lines, anywhere. A line that is in the left file twice and the right
    #    file once is "the same" once and "only in left" once.
    waiting: dict[str, deque[int]] = defaultdict(deque)
    for j, key in enumerate(rkeys):
        if not rskip[j]:
            waiting[key].append(j)
    for i, key in enumerate(lkeys):
        if lskip[i]:
            continue
        queue = waiting.get(key)
        if queue:
            j = queue.popleft()
            lines_l[i].kind, lines_l[i].partner = SAME, j
            lines_r[j].kind, lines_r[j].partner = SAME, i

    # 2. What is left over: similar lines become "changed" pairs.
    rest_l = [(i, lkeys[i]) for i, ln in enumerate(lines_l) if ln.kind == REMOVED]
    rest_r = [(j, rkeys[j]) for j, ln in enumerate(lines_r) if ln.kind == ADDED]
    pairs, limited = pair_similar(rest_l, rest_r, options.similarity, cancel,
                                  len(lines_l), len(lines_r))
    for i, j in pairs:
        lines_l[i].kind, lines_l[i].partner = CHANGED, j
        lines_r[j].kind, lines_r[j].partner = CHANGED, i
    return CompareResult(left=lines_l, right=lines_r, aligned=False, pairing_limited=limited)


def _compare_ordered(left: TextSource, right: TextSource, lkeys: list[str], rkeys: list[str],
                     lskip: list[bool], rskip: list[bool], options: CompareOptions,
                     cancel: Cancel) -> CompareResult:
    # Ignored lines take no part in the matching; they are put back in place afterwards.
    li = [i for i in range(len(lkeys)) if not lskip[i]]
    ri = [j for j in range(len(rkeys)) if not rskip[j]]
    ids: dict[str, int] = {}
    a = [ids.setdefault(lkeys[i], len(ids)) for i in li]
    b = [ids.setdefault(rkeys[j], len(ids)) for j in ri]

    # Common start and end are matched directly: the usual case is two long files that
    # differ in a few places, and this keeps difflib's work to the part that differs.
    head = 0
    while head < len(a) and head < len(b) and a[head] == b[head]:
        head += 1
    tail = 0
    while tail < len(a) - head and tail < len(b) - head and a[-1 - tail] == b[-1 - tail]:
        tail += 1
    mid_a, mid_b = a[head:len(a) - tail], b[head:len(b) - tail]
    matcher = SequenceMatcher(None, mid_a, mid_b, autojunk=len(mid_b) >= AUTOJUNK_FROM)

    pairs: list[tuple[Optional[int], Optional[int], str]] = [(li[k], ri[k], SAME) for k in range(head)]
    budget = [PAIRING_BUDGET]   # similarity checks left, shared by every block
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if cancel is not None and cancel.is_set():
            break
        ls = [li[head + k] for k in range(i1, i2)]
        rs = [ri[head + k] for k in range(j1, j2)]
        if op == "equal":
            pairs.extend((x, y, SAME) for x, y in zip(ls, rs))
        elif op == "delete":
            pairs.extend((x, None, REMOVED) for x in ls)
        elif op == "insert":
            pairs.extend((None, y, ADDED) for y in rs)
        else:
            pairs.extend(_pair_block(ls, rs, lkeys, rkeys, options.similarity, budget))
    pairs.extend((li[len(a) - tail + k], ri[len(b) - tail + k], SAME) for k in range(tail))

    rows_l, rows_r = _rows_with_ignored(pairs, left, right, lskip, rskip)
    result = CompareResult(left=rows_l, right=rows_r, aligned=True, pairing_limited=budget[0] <= 0)
    if options.detect_moves:
        _detect_moves(result, lkeys, rkeys)
    return result


def _pair_block(ls: list[int], rs: list[int], lkeys: list[str], rkeys: list[str],
                threshold: float, budget: list[int]) -> list[tuple[Optional[int], Optional[int], str]]:
    """Inside a block where both sides differ, line up the lines that are similar.

    Walks down the left lines; each one looks ahead on the right for its best similar
    line. Right lines skipped over are additions, left lines with no partner are removals.
    ``budget`` is the number of similarity checks left; once it runs out, each line is
    only compared with the next line on the right.
    """
    out: list[tuple[Optional[int], Optional[int], str]] = []
    k = 0
    for x in ls:
        lookahead = 50 if budget[0] > 0 else 1
        budget[0] -= min(lookahead, len(rs) - k)
        best, best_score = None, 0.0
        for n in range(k, min(len(rs), k + lookahead)):
            score = _similar_enough(lkeys[x], rkeys[rs[n]], threshold)
            if score > best_score:
                best, best_score = n, score
        if best is None:
            out.append((x, None, REMOVED))
            continue
        out.extend((None, y, ADDED) for y in rs[k:best])
        out.append((x, rs[best], CHANGED))
        k = best + 1
    out.extend((None, y, ADDED) for y in rs[k:])
    return out


def _rows_with_ignored(pairs: list[tuple[Optional[int], Optional[int], str]], left: TextSource,
                       right: TextSource, lskip: list[bool],
                       rskip: list[bool]) -> tuple[list[Line], list[Line]]:
    """Turn matched pairs into two equally long row lists, putting ignored lines back."""
    rows_l: list[Line] = []
    rows_r: list[Line] = []
    next_l = next_r = 0

    def flush(upto_l: int, upto_r: int) -> None:
        nonlocal next_l, next_r
        wait_l = [i for i in range(next_l, upto_l) if lskip[i]]
        wait_r = [j for j in range(next_r, upto_r) if rskip[j]]
        next_l, next_r = max(next_l, upto_l), max(next_r, upto_r)
        for n in range(max(len(wait_l), len(wait_r))):
            x = wait_l[n] if n < len(wait_l) else None
            y = wait_r[n] if n < len(wait_r) else None
            rows_l.append(Line(IGNORED, x + 1, left.lines[x]) if x is not None else Line(FILLER, None))
            rows_r.append(Line(IGNORED, y + 1, right.lines[y]) if y is not None else Line(FILLER, None))

    for x, y, kind in pairs:
        flush(x if x is not None else next_l, y if y is not None else next_r)
        row = len(rows_l)
        if x is not None:
            rows_l.append(Line(kind, x + 1, left.lines[x], partner=row if y is not None else None))
            next_l = x + 1
        else:
            rows_l.append(Line(FILLER, None))
        if y is not None:
            rows_r.append(Line(kind, y + 1, right.lines[y], partner=row if x is not None else None))
            next_r = y + 1
        else:
            rows_r.append(Line(FILLER, None))
    flush(len(left.lines), len(right.lines))
    return rows_l, rows_r


def _detect_moves(result: CompareResult, lkeys: list[str], rkeys: list[str]) -> None:
    """A removed line that is added, unchanged, somewhere else was moved, not deleted."""
    added: dict[str, deque[int]] = defaultdict(deque)
    for row, ln in enumerate(result.right):
        if ln.kind == ADDED:
            added[rkeys[ln.number - 1]].append(row)
    for row, ln in enumerate(result.left):
        if ln.kind != REMOVED:
            continue
        queue = added.get(lkeys[ln.number - 1])
        if queue:
            other = queue.popleft()
            ln.kind, ln.partner = MOVED, other
            result.right[other].kind, result.right[other].partner = MOVED, row


def _add_char_spans(result: CompareResult, options: CompareOptions,
                    pattern: Optional[re.Pattern]) -> None:
    for ln in result.left:
        if ln.kind == CHANGED and ln.partner is not None:
            other = result.right[ln.partner]
            ln.spans, other.spans = char_spans(ln.text, other.text, options, pattern)


def _count(result: CompareResult) -> None:
    def tally(lines: list[Line], kind: str) -> int:
        return sum(1 for ln in lines if ln.kind == kind)

    result.removed = tally(result.left, REMOVED)
    result.added = tally(result.right, ADDED)
    result.changed = tally(result.left, CHANGED)
    result.moved = tally(result.left, MOVED)
    result.same = tally(result.left, SAME)
    result.ignored = tally(result.left, IGNORED) + tally(result.right, IGNORED)


def _blocks(result: CompareResult) -> list[Block]:
    """Runs of differing lines, in reading order, for Next / Previous."""
    blocks: list[Block] = []
    if result.aligned:
        start = None
        for row in range(len(result.left) + 1):
            left = result.left[row] if row < len(result.left) else None
            right = result.right[row] if row < len(result.right) else None
            differs = left is not None and (left.kind in DIFF_KINDS
                                            or (right is not None and right.kind in DIFF_KINDS))
            if differs and start is None:
                start = row
            elif not differs and start is not None:
                kind = result.left[start].kind if result.left[start].kind in DIFF_KINDS \
                    else result.right[start].kind
                blocks.append(Block(start, start, kind))
                start = None
        return blocks

    # Unordered: runs on the left (removed or changed), then right-only runs, merged by
    # where they sit in their file so Next walks down both files together.
    def runs(lines: list[Line], kinds: frozenset[str]) -> list[int]:
        out, previous = [], False
        for row, ln in enumerate(lines):
            now = ln.kind in kinds
            if now and not previous:
                out.append(row)
            previous = now
        return out

    n_l, n_r = max(len(result.left), 1), max(len(result.right), 1)
    found = []
    for row in runs(result.left, frozenset({REMOVED, CHANGED})):
        ln = result.left[row]
        found.append((row / n_l, Block(row, ln.partner if ln.kind == CHANGED else None, ln.kind)))
    for row in runs(result.right, frozenset({ADDED})):
        found.append((row / n_r, Block(None, row, ADDED)))
    found.sort(key=lambda item: item[0])
    return [b for _pos, b in found]


# ================================================================ formatting
def plural(n: int, word: str, many: str = "") -> str:
    """plural(1, "line") -> "1 line", plural(3, "match", "matches") -> "3 matches"."""
    return f"{n:,} {word if n == 1 else (many or word + 's')}"


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if n >= 10 else f"{n:.1f} {unit}"
    return f"{n:.1f} GB"


def short_path(path: str, limit: int = 60) -> str:
    """Shorten a long path in the middle, keeping the drive and the last folders."""
    if len(path) <= limit:
        return path
    keep = limit - 1
    head = keep // 3
    return path[:head] + "…" + path[-(keep - head):]


def summary_lines(result: CompareResult) -> list[str]:
    """The counts as short sentences, used by the result panel and the Excel summary."""
    out = []
    if result.removed:
        out.append(f"{plural(result.removed, 'line')} only in the left file")
    if result.added:
        out.append(f"{plural(result.added, 'line')} only in the right file")
    if result.changed:
        out.append(f"{plural(result.changed, 'line')} changed")
    if result.moved:
        out.append(f"{plural(result.moved, 'line')} moved")
    out.append(f"{plural(result.same, 'line')} the same")
    if result.ignored:
        out.append(f"{plural(result.ignored, 'line')} left out (not compared)")
    return out
