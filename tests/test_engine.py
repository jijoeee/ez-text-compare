"""Engine tests: what counts as removed, added, changed, moved and the same."""

import threading
import time

import pytest

from ezcompare.engine import (ADDED, CHANGED, FILLER, IGNORED, MOVED, REMOVED, SAME, CompareOptions,
                              build_ignore_pattern, char_spans, compare, make_key, similarity)
from ezcompare.textfile import CompareError, text_from_string

BEFORE = """hostname core-sw01
interface Vlan10
 ip address 192.0.2.1 255.255.255.0
 shutdown
!
ntp server 203.0.113.10
logging host 203.0.113.20
"""

AFTER = """hostname core-sw01
logging host 203.0.113.20
interface Vlan10
 ip address 192.0.2.25 255.255.255.0
!
ntp server 203.0.113.10
snmp-server community demo RO
"""


def kinds(lines):
    return [ln.kind for ln in lines]


def by_text(lines, text):
    return next(ln for ln in lines if ln.text == text)


# ---------------------------------------------------------------- ignore line order (default)
def test_identical_files():
    r = compare(text_from_string(BEFORE), text_from_string(BEFORE))
    assert r.identical
    assert r.same == 7 and r.differences == 0
    assert r.blocks == []


def test_unordered_finds_removed_added_changed():
    r = compare(text_from_string(BEFORE), text_from_string(AFTER))
    assert not r.aligned
    assert r.removed == 1                       # " shutdown"
    assert r.added == 1                         # "snmp-server ..."
    assert r.changed == 1                       # the IP address line
    assert r.moved == 0                         # order is ignored, so nothing "moved"
    assert by_text(r.left, " shutdown").kind == REMOVED
    assert by_text(r.right, "snmp-server community demo RO").kind == ADDED
    # A moved line is simply "the same" when order is ignored.
    assert by_text(r.left, "logging host 203.0.113.20").kind == SAME


def test_changed_lines_point_at_each_other():
    r = compare(text_from_string(BEFORE), text_from_string(AFTER))
    left = by_text(r.left, " ip address 192.0.2.1 255.255.255.0")
    assert left.kind == CHANGED
    right = r.right[left.partner]
    assert right.text == " ip address 192.0.2.25 255.255.255.0"
    assert r.left[right.partner] is left


def test_char_spans_mark_only_what_changed():
    r = compare(text_from_string(BEFORE), text_from_string(AFTER))
    left = by_text(r.left, " ip address 192.0.2.1 255.255.255.0")
    right = r.right[left.partner]
    assert [left.text[a:b] for a, b in left.spans] == ["1"]
    assert [right.text[a:b] for a, b in right.spans] == ["25"]


def test_char_diffs_can_be_switched_off():
    r = compare(text_from_string(BEFORE), text_from_string(AFTER), CompareOptions(char_diffs=False))
    assert all(not ln.spans for ln in r.left + r.right)


def test_duplicate_lines_are_counted():
    # The left file has "!" twice, the right once: one is the same, one is only in the left.
    r = compare(text_from_string("a\n!\n!\n"), text_from_string("!\na\n"))
    assert r.same == 2
    assert r.removed == 1


def test_similar_line_in_a_similar_place_wins():
    # "Printers" must pair with the nearby "Printers and scanners", not "Cameras" at the end.
    left = "interface Vlan20\n description Printers\nx\nx\nx\nx\nx\nx\n"
    right = ("interface Vlan20\n description Printers and scanners\nx\nx\nx\nx\nx\nx\n"
             "interface Vlan30\n description Cameras\n")
    r = compare(text_from_string(left), text_from_string(right))
    line = by_text(r.left, " description Printers")
    assert r.right[line.partner].text == " description Printers and scanners"


def test_unrelated_lines_are_not_paired():
    r = compare(text_from_string("shutdown\n"), text_from_string("description uplink to core\n"))
    assert kinds(r.left) == [REMOVED]
    assert kinds(r.right) == [ADDED]


# ---------------------------------------------------------------- line order matters
def test_ordered_view_is_aligned_with_fillers():
    r = compare(text_from_string(BEFORE), text_from_string(AFTER), CompareOptions(ignore_order=False))
    assert r.aligned
    assert len(r.left) == len(r.right)
    for left, right in zip(r.left, r.right):
        if left.kind == FILLER:
            assert right.kind in (ADDED, MOVED, IGNORED)
        if right.kind == FILLER:
            assert left.kind in (REMOVED, MOVED, IGNORED)
    # Real line numbers are kept, in order, with no gaps.
    assert [ln.number for ln in r.left if ln.number] == list(range(1, 8))
    assert [ln.number for ln in r.right if ln.number] == list(range(1, 8))


def test_ordered_view_detects_moves():
    r = compare(text_from_string(BEFORE), text_from_string(AFTER), CompareOptions(ignore_order=False))
    assert r.moved == 1
    left = by_text(r.left, "logging host 203.0.113.20")
    assert left.kind == MOVED
    assert r.right[left.partner].text == "logging host 203.0.113.20"


def test_ordered_view_without_move_detection():
    options = CompareOptions(ignore_order=False, detect_moves=False)
    r = compare(text_from_string(BEFORE), text_from_string(AFTER), options)
    assert r.moved == 0
    assert by_text(r.left, "logging host 203.0.113.20").kind == REMOVED


def test_ordered_view_pairs_changed_lines_in_place():
    r = compare(text_from_string("a\nip 10.0.0.1\nb\n"), text_from_string("a\nip 10.0.0.2\nb\n"),
                CompareOptions(ignore_order=False))
    assert kinds(r.left) == [SAME, CHANGED, SAME]
    assert r.left[1].partner == 1


def test_blocks_walk_down_the_files():
    r = compare(text_from_string(BEFORE), text_from_string(AFTER), CompareOptions(ignore_order=False))
    starts = [b.left for b in r.blocks]
    assert starts == sorted(starts)
    assert len(r.blocks) >= 3


# ---------------------------------------------------------------- ignore options
def test_ignore_case_and_spaces():
    a, b = text_from_string("Interface  Vlan10 \n"), text_from_string("interface vlan10\n")
    assert not compare(a, b).identical
    assert compare(a, b, CompareOptions(ignore_case=True, ignore_changed_spaces=True)).identical


def test_ignore_all_spaces():
    a, b = text_from_string("ip address 1.1.1.1\n"), text_from_string("ipaddress1.1.1.1\n")
    assert compare(a, b, CompareOptions(ignore_all_spaces=True)).identical
    assert not compare(a, b, CompareOptions(ignore_changed_spaces=True)).identical


def test_ignore_empty_lines():
    a, b = text_from_string("a\n\nb\n"), text_from_string("a\nb\n\n\n")
    assert not compare(a, b).identical
    for order in (True, False):
        r = compare(a, b, CompareOptions(ignore_empty=True, ignore_order=order))
        assert r.identical, order
        assert r.ignored == 3


def test_ignore_timestamps():
    a = text_from_string("2026-10-10 09:00:01 %LINK-3-UPDOWN: Gi1/0/1 up\nOct 10 09:00:02 R1 BGP up\n")
    b = text_from_string("2026-10-11 21:15:44 %LINK-3-UPDOWN: Gi1/0/1 up\nOct 11 21:15:45 R1 BGP up\n")
    assert not compare(a, b).identical
    assert compare(a, b, CompareOptions(ignore_timestamps=True)).identical


def test_ignore_pattern():
    a, b = text_from_string("seq 10 permit any\n"), text_from_string("seq 20 permit any\n")
    assert compare(a, b, CompareOptions(ignore_pattern=r"seq \d+")).identical


def test_ignored_text_is_not_highlighted():
    options = CompareOptions(ignore_timestamps=True)
    pattern = build_ignore_pattern("", True)
    sa, sb = char_spans("09:00:01 link up", "21:15:44 link down", options, pattern)
    assert [("21:15:44 link down")[x:y] for x, y in sb] == ["down"]


def test_bad_pattern_is_explained():
    with pytest.raises(CompareError, match="ignore pattern has a mistake"):
        compare(text_from_string("a"), text_from_string("b"), CompareOptions(ignore_pattern="([a-z"))


def test_make_key():
    options = CompareOptions(ignore_case=True, ignore_changed_spaces=True)
    assert make_key("  Shut   Down ", options, None) == "shut down"


def test_similarity_range():
    assert similarity("abc", "abc") == 1.0
    assert similarity("abc", "xyz") == 0.0


# ---------------------------------------------------------------- size and stopping
def _log(n: int, seed: int) -> str:
    lines = [f"2026-10-1{seed} 09:{i // 60 % 60:02d}:{i % 60:02d} R{i % 7} %LINK-3-UPDOWN: "
             f"Interface Gi1/0/{i % 48} changed state to {'up' if (i + seed) % 5 else 'down'}"
             for i in range(n)]
    return "\n".join(lines)


@pytest.mark.parametrize("ignore_order", [True, False])
def test_large_logs_finish_quickly(ignore_order):
    a, b = text_from_string(_log(20_000, 0)), text_from_string(_log(20_000, 1))
    started = time.perf_counter()
    r = compare(a, b, CompareOptions(ignore_order=ignore_order, ignore_timestamps=True))
    assert time.perf_counter() - started < 60
    assert r.differences > 0
    assert len([ln for ln in r.left if ln.number]) == 20_000


def test_stop_raises_a_clear_error():
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CompareError, match="stopped"):
        compare(text_from_string(_log(500, 0)), text_from_string(_log(500, 1)), cancel=cancel)


@pytest.mark.parametrize("ignore_order", [True, False])
def test_every_line_different_stays_within_budget(ignore_order):
    # Two logs whose every line differs (timestamps not ignored): the worst case for
    # pairing similar lines. It must still finish, and say the pairing was limited.
    a, b = text_from_string(_log(20_000, 0)), text_from_string(_log(20_000, 1))
    started = time.perf_counter()
    r = compare(a, b, CompareOptions(ignore_order=ignore_order))
    assert time.perf_counter() - started < 60
    assert r.pairing_limited
    assert r.changed > 0


# ---------------------------------------------------------------- only lines containing
def test_only_lines_containing_text_are_compared():
    a = text_from_string("hostname R1\ninterface Gi1\n description old\ninterface Gi2\n")
    b = text_from_string("hostname R2\nINTERFACE Gi1\n description new\ninterface Gi3\n")
    for order in (True, False):
        r = compare(a, b, CompareOptions(only_containing="Interface", ignore_case=True, ignore_order=order))
        compared = [ln.text for ln in r.left if ln.kind not in (IGNORED, FILLER)]
        assert compared == ["interface Gi1", "interface Gi2"], order
        # hostname and description lines differ, but they are left out, not counted.
        assert by_text(r.left, "hostname R1").kind == IGNORED
        assert r.ignored == 4
        assert r.same == 1 and r.changed == 1 and r.differences == 1


def test_only_lines_containing_is_not_case_sensitive():
    a, b = text_from_string("Speed 100\nmtu 1500\n"), text_from_string("speed 1000\nmtu 9000\n")
    r = compare(a, b, CompareOptions(only_containing="SPEED"))
    assert r.changed == 1
    assert by_text(r.left, "mtu 1500").kind == IGNORED


def test_only_lines_containing_with_no_match_is_identical():
    r = compare(text_from_string("a\n"), text_from_string("b\n"), CompareOptions(only_containing="zzz"))
    assert r.identical and r.ignored == 2
