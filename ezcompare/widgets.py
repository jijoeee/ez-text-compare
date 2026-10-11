"""Reusable widgets: buttons, inputs, drop zone, result panel, file slots, diff panes."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from . import engine
from . import theme as T
from .engine import ADDED, CHANGED, FILLER, IGNORED, MOVED, REMOVED, Line
from .textfile import TextSource

log = logging.getLogger("ezcompare.ui")


# ======================================================================
# Buttons and inputs
# ======================================================================

def primary_button(parent, text, command, icon=None, height=44, **kw):
    return ctk.CTkButton(
        parent, text=text, command=command, height=height, corner_radius=T.RADIUS_M,
        fg_color=T.PRIMARY, hover_color=T.PRIMARY_HOVER, text_color=T.ON_PRIMARY,
        text_color_disabled=("#F5E8F0", "#AB8FA2"), font=T.font(14, True),
        image=T.icon(icon, 18, T.ON_PRIMARY) if icon else None, compound="left", **kw)


def secondary_button(parent, text, command, icon=None, height=34, danger=False, **kw):
    color = T.DANGER if danger else T.TEXT
    return ctk.CTkButton(
        parent, text=text, command=command, height=height, corner_radius=T.RADIUS_S,
        fg_color=T.SURFACE, hover_color=T.HOVER, border_width=1, border_color=T.BORDER,
        text_color=color, text_color_disabled=T.TEXT_3, font=T.font(12),
        image=T.icon(icon, 16, T.DANGER if danger else T.TEXT_2) if icon else None,
        compound="left", **kw)


def icon_button(parent, icon, command, size=18, color=T.TEXT_2, **kw):
    kw.setdefault("width", 34)
    kw.setdefault("height", 34)
    return ctk.CTkButton(
        parent, text="", corner_radius=T.RADIUS_S, command=command,
        fg_color="transparent", hover_color=T.HOVER, image=T.icon(icon, size, color), **kw)


def divider(parent, **pack):
    # height=2: CustomTkinter skips drawing 1px frames on some scalings
    line = ctk.CTkFrame(parent, height=2, fg_color=T.BORDER, corner_radius=0)
    line.pack(fill="x", **pack)
    return line


def section_label(parent, text, top=T.SPACE_3):
    label = ctk.CTkLabel(parent, text=text, font=T.font(12, True), text_color=T.TEXT_2, anchor="w")
    label.pack(fill="x", pady=(top, T.SPACE_1))
    return label


def text_entry(parent, placeholder: str, **kw) -> ctk.CTkEntry:
    """A text box. No textvariable on purpose: with one, CTkEntry never shows its placeholder."""
    entry = ctk.CTkEntry(parent, placeholder_text=placeholder, height=36, corner_radius=T.RADIUS_S,
                         border_width=1, border_color=T.BORDER, fg_color=T.SURFACE_2,
                         text_color=T.TEXT, placeholder_text_color=T.TEXT_3, font=T.font(13), **kw)
    entry.bind("<FocusIn>", lambda e: entry.configure(border_color=T.PRIMARY_TEXT), add="+")
    entry.bind("<FocusOut>", lambda e: entry.configure(border_color=T.BORDER), add="+")
    return entry


def set_entry_text(entry: ctk.CTkEntry, text: str) -> None:
    entry.delete(0, "end")
    if text:
        entry.insert(0, text)


def checkbox(parent, text: str, value: bool, command=None) -> tuple[ctk.CTkCheckBox, ctk.BooleanVar]:
    var = ctk.BooleanVar(value=value)
    box = ctk.CTkCheckBox(parent, text=text, variable=var, command=command, font=T.font(13),
                          text_color=T.TEXT, fg_color=T.PRIMARY, hover_color=T.PRIMARY_HOVER,
                          border_color=T.TEXT_3, checkmark_color=T.ON_PRIMARY, border_width=2,
                          checkbox_width=18, checkbox_height=18, corner_radius=4)
    box.pack(fill="x", pady=(T.SPACE_1, T.SPACE_1))
    return box, var


# ======================================================================
# Scroll frame that hides its scrollbar when everything fits
# ======================================================================

class AutoScrollFrame(ctk.CTkScrollableFrame):
    def __init__(self, master, **kw):
        kw.setdefault("scrollbar_button_color", T.BORDER)
        kw.setdefault("scrollbar_button_hover_color", T.TEXT_3)
        super().__init__(master, **kw)
        self._sb_shown = True
        self._sb_job = None
        self.bind("<Configure>", self._queue_sb_check, add="+")
        self._parent_canvas.bind("<Configure>", self._queue_sb_check, add="+")

    def _queue_sb_check(self, _event=None):
        if self._sb_job is None:
            self._sb_job = self.after(50, self._sb_check)

    def _sb_check(self):
        self._sb_job = None
        need = self.winfo_reqheight() > self._parent_canvas.winfo_height() + 1
        if need and not self._sb_shown:
            self._scrollbar.grid()
        elif not need and self._sb_shown:
            self._scrollbar.grid_remove()
            self._parent_canvas.yview_moveto(0)
        self._sb_shown = need


# ======================================================================
# Drop zone (empty state)
# ======================================================================

class DropZone(ctk.CTkFrame):
    """Empty state: the one place the glossy orb appears."""

    def __init__(self, master, on_browse: Callable[[], None]):
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        self.panel = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=T.RADIUS_L,
                                  border_width=2, border_color=T.BORDER)
        self.panel.pack(expand=True, fill="both", padx=T.SPACE_4 * 2, pady=T.SPACE_4 * 2)
        inner = ctk.CTkFrame(self.panel, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(inner, text="", image=T.asset_image("drop_orb.png", 112)).pack(pady=(0, T.SPACE_3))
        self.title = ctk.CTkLabel(inner, text="", font=T.font(22, True), text_color=T.TEXT)
        self.title.pack()
        self.subtitle = ctk.CTkLabel(inner, text="", font=T.font(13), text_color=T.TEXT_2,
                                     wraplength=440, justify="center")
        self.subtitle.pack(pady=T.SPACE_2)
        self.button = primary_button(inner, "", on_browse, width=220)
        self.button.pack()
        hint = ctk.CTkFrame(inner, fg_color="transparent")
        hint.pack(pady=(T.SPACE_4, 0))
        ctk.CTkLabel(hint, text="", image=T.icon("shield", 14, T.TEXT_3)).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(hint, text="Files are compared on this computer. Nothing is uploaded.",
                     font=T.font(11), text_color=T.TEXT_3).pack(side="left")
        self.title.configure(text="Drop two files here")
        self.subtitle.configure(text="Text, log or config files. The older one goes on the left, the newer "
                                     "one on the right.")
        self.button.configure(text="Choose two files")

    def set_highlight(self, on: bool) -> None:
        self.panel.configure(border_color=T.PRIMARY_TEXT if on else T.BORDER,
                             fg_color=T.PRIMARY_SOFT if on else T.SURFACE)


# ======================================================================
# Result panel (sidebar)
# ======================================================================

class ResultPanel(ctk.CTkFrame):
    """Shows the outcome of the last search. Only the latest result is kept."""

    STYLES = {
        "success": (T.SUCCESS_SOFT, T.SUCCESS, "success"),
        "error": (T.DANGER_SOFT, T.DANGER, "error"),
        "info": (T.PRIMARY_SOFT, T.PRIMARY_TEXT, "info"),
    }

    def __init__(self, master):
        super().__init__(master, fg_color="transparent", height=1)

    def clear(self):
        for w in self.winfo_children():
            w.destroy()

    def show(self, kind: str, title: str, detail: str = "",
             actions: Optional[list[tuple[str, str, Callable]]] = None):
        self.clear()
        bg, fg, ico = self.STYLES[kind]
        box = ctk.CTkFrame(self, fg_color=bg, corner_radius=T.RADIUS_M)
        box.pack(fill="x")
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=T.SPACE_3, pady=(T.SPACE_3, 0))
        ctk.CTkLabel(head, text="", image=T.icon(ico, 18, fg)).pack(side="left", padx=(0, T.SPACE_2))
        ctk.CTkLabel(head, text=title, font=T.font(13, True), text_color=fg,
                     wraplength=T.CONTENT_W - 70, justify="left", anchor="w").pack(side="left", fill="x")
        if detail:
            ctk.CTkLabel(box, text=detail, font=T.font(12), text_color=T.TEXT_2, justify="left",
                         anchor="w", wraplength=T.CONTENT_W - 2 * T.SPACE_3 - 6).pack(fill="x", padx=T.SPACE_3, pady=(T.SPACE_1, 0))
        if actions:
            for n, (label, ic, cmd) in enumerate(actions):
                secondary_button(box, label, cmd, icon=ic, height=32, anchor="w").pack(
                    fill="x", padx=T.SPACE_3, pady=(T.SPACE_3 if n == 0 else T.SPACE_1, 0))
        ctk.CTkFrame(box, height=T.SPACE_3, fg_color="transparent").pack()
        canvas = getattr(self.master, "_parent_canvas", None)
        if canvas is not None:  # make sure the new result is visible on short screens
            self.after(120, lambda: canvas.yview_moveto(1.0))


# ======================================================================
# File slot: which file is on one side, and how to change it
# ======================================================================

class FileSlot(ctk.CTkFrame):
    """The header of one side: file name, its details, and Open / Paste / Remove."""

    def __init__(self, master, side: str, on_choose: Callable[[], None], on_paste: Callable[[], None],
                 on_clear: Callable[[], None]):
        super().__init__(master, fg_color="transparent", height=1)
        self.side = side
        # Buttons are packed before the labels so a long file name can never push them out.
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(side="right", padx=(T.SPACE_2, 0))
        # Icons only: the panes are half the window, and the file name needs the room.
        self.clear_btn = icon_button(buttons, "close", on_clear, size=16, width=30, height=30)
        self.clear_btn.pack(side="right")
        icon_button(buttons, "paste", on_paste, size=16, width=30, height=30).pack(side="right")
        icon_button(buttons, "folder", on_choose, size=16, width=30, height=30).pack(side="right")

        labels = ctk.CTkFrame(self, fg_color="transparent")
        labels.pack(side="left", fill="x", expand=True)
        top = ctk.CTkFrame(labels, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=side, font=T.font(11, True), text_color=T.PRIMARY_TEXT).pack(side="left")
        self.name = ctk.CTkLabel(top, text="", font=T.font(14, True), text_color=T.TEXT, anchor="w")
        self.name.pack(side="left", padx=(T.SPACE_2, 0))
        self.meta = ctk.CTkLabel(labels, text="", font=T.font(11), text_color=T.TEXT_2, anchor="w",
                                 justify="left")
        self.meta.pack(fill="x")
        # Wrap the details to the space there is, instead of cutting them off.
        labels.bind("<Configure>", lambda e: self.meta.configure(
            wraplength=max(120, e.width / ctk.ScalingTracker.get_widget_scaling(self) - 4)), add="+")
        self.set_source(None)

    def set_source(self, source: Optional[TextSource]) -> None:
        if source is None:
            self.name.configure(text="No file yet")
            self.meta.configure(text="Drop a file here, or use the open and paste buttons.")
            self.clear_btn.configure(state="disabled")
            return
        self.name.configure(text=_ellipsize(source.name, 46))
        self.meta.configure(text=describe_source(source))
        self.clear_btn.configure(state="normal")


def _ellipsize(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


def describe_source(source: TextSource) -> str:
    """'1,204 lines · UTF-8 · Windows (CRLF) · 48 KB · 2026-10-11 09:12'"""
    parts = [engine.plural(len(source.lines), "line")]
    if source.pasted:
        parts.append("pasted from the clipboard")
    else:
        parts += [p for p in (source.encoding, source.line_ending) if p]
        parts.append(engine.format_size(source.size))
        if source.modified:
            from datetime import datetime
            parts.append(datetime.fromtimestamp(source.modified).strftime("%Y-%m-%d %H:%M"))
    return "  ·  ".join(parts)


# ======================================================================
# One side of the comparison: line numbers and text
# ======================================================================

# What the gutter shows next to each kind of line, so a difference is never told by
# colour alone (colour-blind users, black-and-white printouts of a screenshot).
MARKERS = {REMOVED: "−", ADDED: "+", CHANGED: "~", MOVED: "»"}
LINE_TAGS = (REMOVED, ADDED, CHANGED, MOVED, FILLER, IGNORED)


class DiffPane(ctk.CTkFrame):
    """Line numbers and text for one file, coloured by what happened to each line.

    Plain tk.Text widgets rather than one widget per line: they stay fast with tens
    of thousands of lines. They are not drawn by CustomTkinter, so colours and fonts
    are applied here and again whenever the theme or scaling changes.
    """

    def __init__(self, master, side: str, char_tag: str, on_choose, on_paste, on_clear,
                 on_click: Callable[[str, int], None]):
        super().__init__(master, fg_color=T.SURFACE, bg_color=T.BG, corner_radius=T.RADIUS_M,
                         border_width=1, border_color=T.BORDER)
        self.side = side
        self.char_tag = char_tag            # "del_char" on the left, "add_char" on the right
        self._on_click = on_click
        self._lines: list[Line] = []
        self._rows: list[int] = []          # display line -> row in self._lines
        self._display: dict[int, int] = {}  # row -> display line
        self.y_listener: Optional[Callable[[float], None]] = None
        self._gutter_job = None

        self.slot = FileSlot(self, side, on_choose, on_paste, on_clear)
        self.slot.pack(fill="x", padx=T.SPACE_3, pady=(T.SPACE_3, T.SPACE_2))
        ctk.CTkFrame(self, height=2, fg_color=T.BORDER, corner_radius=0).pack(fill="x", padx=2)

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=(2, 2), pady=(0, 4))
        common = dict(wrap="none", bd=0, highlightthickness=0, relief="flat", insertwidth=0,
                      undo=False, takefocus=0)
        self.gutter = tk.Text(self.body, width=6, padx=6, pady=4, cursor="arrow", **common)
        self.text = tk.Text(self.body, padx=8, pady=4, **common)
        self.vscroll = ctk.CTkScrollbar(self.body, command=self._scroll_y, button_color=T.BORDER,
                                        button_hover_color=T.TEXT_3, fg_color="transparent")
        self.hscroll = ctk.CTkScrollbar(self.body, orientation="horizontal", command=self.text.xview,
                                        button_color=T.BORDER, button_hover_color=T.TEXT_3,
                                        fg_color="transparent", height=12)
        self.text.configure(yscrollcommand=self._on_text_y, xscrollcommand=self.hscroll.set)
        self.gutter.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        self.vscroll.grid(row=0, column=2, sticky="ns", pady=4)
        self.hscroll.grid(row=1, column=1, sticky="ew")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=1)

        self.empty = ctk.CTkLabel(self.body, text="", font=T.font(13), text_color=T.TEXT_2,
                                  justify="center", wraplength=320)

        # Read-only, but text can still be selected and copied.
        for widget in (self.text, self.gutter):
            widget.bind("<Key>", lambda e: None if (e.state & 0x4 and e.keysym.lower() in ("c", "a"))
                        else "break")
        self.text.bind("<ButtonRelease-1>", self._clicked, add="+")
        self.gutter.bind("<Button-1>", self._clicked)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.gutter.bind(seq, self._wheel)

        self.apply_style()
        ctk.ScalingTracker.add_widget(lambda *_: self.apply_style(), self)
        self.show_message("Drop a file on this side,\nor use the open and paste buttons above.")

    # -------------------------------------------------------------- look
    def apply_style(self) -> None:
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        mono = T.tk_font(13, scale, mono=True)
        surface, gutter = T.pick(T.SURFACE), T.pick(T.GUTTER)
        self.text.configure(bg=surface, fg=T.pick(T.TEXT), font=mono,
                            selectbackground=T.pick(T.PRIMARY_SOFT), selectforeground=T.pick(T.TEXT),
                            inactiveselectbackground=T.pick(T.PRIMARY_SOFT))
        self.gutter.configure(bg=gutter, fg=T.pick(T.TEXT_2), font=mono,
                              selectbackground=gutter, selectforeground=T.pick(T.TEXT_2),
                              inactiveselectbackground=gutter)
        colours = {REMOVED: T.REMOVED_LINE, ADDED: T.ADDED_LINE, CHANGED: T.CHANGED_LINE,
                   MOVED: T.MOVED_LINE, FILLER: T.FILLER}
        for tag, token in colours.items():
            self.text.tag_configure(tag, background=T.pick(token))
        self.text.tag_configure(IGNORED, foreground=T.pick(T.TEXT_3))
        self.text.tag_configure("del_char", background=T.pick(T.REMOVED_CHAR))
        self.text.tag_configure("add_char", background=T.pick(T.ADDED_CHAR))
        self.text.tag_raise("del_char")
        self.text.tag_raise("add_char")
        self.text.tag_raise("sel")
        self.gutter.tag_configure("current", background=T.pick(T.CURRENT_MARK),
                                  foreground=T.pick(T.ON_PRIMARY))

    # -------------------------------------------------------------- content
    def set_source(self, source: Optional[TextSource]) -> None:
        self.slot.set_source(source)

    def show_message(self, message: str) -> None:
        """No comparison to show: an empty pane with a hint in the middle."""
        self._fill([], [])
        self.empty.configure(text=message)
        self.empty.place(relx=0.5, rely=0.45, anchor="center")

    def show_plain(self, text_lines: tuple[str, ...]) -> None:
        """A loaded file that is not compared yet: its lines, uncoloured."""
        self.show_lines([Line("same", n + 1, t) for n, t in enumerate(text_lines)],
                        list(range(len(text_lines))))

    def show_lines(self, lines: list[Line], rows: list[int]) -> None:
        """Show ``lines[r]`` for every r in ``rows`` (all rows, or only the differences)."""
        self.empty.place_forget()
        self._fill(lines, rows)

    def _fill(self, lines: list[Line], rows: list[int]) -> None:
        self._lines, self._rows = lines, rows
        self._display = {row: d for d, row in enumerate(rows)}
        width = len(f"{max((ln.number or 0 for ln in lines), default=0):,}")
        numbers, texts = [], []
        for row in rows:
            ln = lines[row]
            num = f"{ln.number:,}" if ln.number is not None else ""
            numbers.append(f"{num:>{width}} {MARKERS.get(ln.kind, ' ')}")
            texts.append(ln.text)
        for widget, content in ((self.gutter, numbers), (self.text, texts)):
            widget.delete("1.0", "end")
            widget.insert("1.0", "\n".join(content))
        self.gutter.configure(width=width + 2)

        for d, row in enumerate(rows):
            ln = lines[row]
            if ln.kind in LINE_TAGS:
                # Tagging the newline too fills the line to the right edge of the pane.
                self.text.tag_add(ln.kind, f"{d + 1}.0", f"{d + 2}.0")
            for a, b in ln.spans:
                self.text.tag_add(self.char_tag, f"{d + 1}.{a}", f"{d + 1}.{b}")
        self.text.yview_moveto(0)
        self.text.xview_moveto(0)
        self._queue_gutter_sync()

    def displayed(self, row: int) -> Optional[int]:
        """Where a row is shown (0-based display line), or None if it is hidden."""
        return self._display.get(row)

    # -------------------------------------------------------------- current block
    def mark_current(self, rows: list[int]) -> None:
        self.gutter.tag_remove("current", "1.0", "end")
        for row in rows:
            d = self._display.get(row)
            if d is not None:
                self.gutter.tag_add("current", f"{d + 1}.0", f"{d + 2}.0")

    def see_row(self, row: int, top_margin: int = 3) -> None:
        """Scroll so ``row`` is near the top, with a few lines of context above it."""
        d = self._display.get(row)
        if d is None:
            return
        self.text.yview(max(0, d - top_margin))
        self._queue_gutter_sync()

    # -------------------------------------------------------------- scrolling
    def _on_text_y(self, first: str, last: str) -> None:
        self.vscroll.set(first, last)
        self.gutter.yview_moveto(first)
        self._queue_gutter_sync()
        if self.y_listener is not None:
            self.y_listener(float(first))

    def _queue_gutter_sync(self) -> None:
        """Line the numbers up with the text once Tk is idle.

        Needed on top of the scroll callback: Tk measures line heights lazily, and when
        new text ends up at the same scroll position as before, Tk sends no callback at
        all while the refilled number column has gone back to the top.
        """
        if self._gutter_job is None:
            self._gutter_job = self.after_idle(self._sync_gutter)

    def _sync_gutter(self) -> None:
        self._gutter_job = None
        self.gutter.yview_moveto(self.text.yview()[0])

    def follow_y(self, first: float) -> None:
        """Scroll to the same place as the other side (the aligned, line-order view)."""
        if abs(float(self.text.yview()[0]) - first) > 1e-9:
            self.text.yview_moveto(first)

    def _scroll_y(self, *args) -> None:
        self.text.yview(*args)

    def _wheel(self, event) -> str:
        if getattr(event, "num", None) == 4:
            step = -3
        elif getattr(event, "num", None) == 5:
            step = 3
        else:
            step = -3 if event.delta > 0 else 3
        self.text.yview_scroll(step, "units")
        return "break"

    def _clicked(self, event) -> None:
        widget = event.widget
        line = int(widget.index(f"@{event.x},{event.y}").split(".")[0]) - 1
        if 0 <= line < len(self._rows):
            self._on_click(self.side, self._rows[line])
