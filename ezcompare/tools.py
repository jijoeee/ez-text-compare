"""The compare screen: the two files side by side on the left, the options on the right."""

from __future__ import annotations

import logging
import os
import re
import threading
import tkinter as tk
import tkinter.filedialog as fd
from typing import Optional

import customtkinter as ctk

from . import engine
from . import theme as T
from .engine import (ADDED, CHANGED, DIFF_KINDS, MOVED, REMOVED, CompareOptions, CompareResult)
from .export import export_excel
from .system import open_path, reveal_in_folder
from .textfile import CompareError, TextSource, read_text_file, text_from_string
from .widgets import (AutoScrollFrame, DiffPane, DropZone, ResultPanel, checkbox, divider,
                      icon_button, primary_button, secondary_button, section_label, set_entry_text,
                      text_entry)

log = logging.getLogger("ezcompare.tools")

LEFT, RIGHT = "Left", "Right"
TEXT_FILES = [("Text, log and config files", "*.txt *.log *.cfg *.conf *.config *.ini *.csv *.json "
                                              "*.xml *.yaml *.yml *.rsc *.out"),
              ("All files", "*.*")]


class CompareTool(ctk.CTkFrame):
    title = "Compare text"
    icon = "compare"
    description = ("Drop two text, log or config files to see which lines were added, removed or "
                   "changed.")

    def __init__(self, master, app):
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        self.app = app
        self.busy = False
        self.sources: dict[str, Optional[TextSource]] = {LEFT: None, RIGHT: None}
        self.result: Optional[CompareResult] = None
        self._result_options: Optional[CompareOptions] = None
        self._gen = 0
        self._cancel: Optional[threading.Event] = None
        self._block = -1

        # The sidebar is packed first so it always keeps its width; the work area gets the rest.
        self._build_sidebar()
        self._build_work_area()
        self._load_settings()
        self.show_empty()

    # ================================================================ layout
    def _build_work_area(self):
        self.work = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        self.work.pack(side="left", fill="both", expand=True)
        self.drop_zone = DropZone(self.work, self.choose_files)

        self.toolbar = ctk.CTkFrame(self.work, fg_color=T.BG, corner_radius=0, height=56)
        self.toolbar.pack_propagate(False)
        # Buttons are packed before the labels so a long heading can never squeeze them.
        right = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        right.pack(side="right", fill="y", padx=(0, T.SPACE_4))
        self.export_btn = secondary_button(right, "Export to Excel", self.export, icon="export")
        self.export_btn.pack(side="right", pady=11)
        self.reset_btn = secondary_button(right, "Reset", self.reset, icon="reset")
        self.reset_btn.pack(side="right", pady=11, padx=(0, T.SPACE_2))
        # Swap is an icon: on a laptop screen the toolbar needs the room for its heading.
        self.swap_btn = secondary_button(right, "", self.swap, icon="swap", width=34)
        self.swap_btn.pack(side="right", pady=11, padx=(0, T.SPACE_2))
        nav = ctk.CTkFrame(right, fg_color="transparent")
        nav.pack(side="right", padx=(0, T.SPACE_3))
        self.last_btn = icon_button(nav, "last", self.last_diff, size=16, width=30, height=30)
        self.last_btn.pack(side="right")
        self.next_btn = icon_button(nav, "down", self.next_diff, size=16, width=30, height=30)
        self.next_btn.pack(side="right")
        self.prev_btn = icon_button(nav, "up", self.prev_diff, size=16, width=30, height=30)
        self.prev_btn.pack(side="right")
        self.first_btn = icon_button(nav, "first", self.first_diff, size=16, width=30, height=30)
        self.first_btn.pack(side="right")
        self.counter = ctk.CTkLabel(nav, text="", font=T.font(12), text_color=T.TEXT_2)
        self.counter.pack(side="right", padx=(0, T.SPACE_2))
        left = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        left.pack(side="left", fill="y", padx=(T.SPACE_4, T.SPACE_3))
        self.heading = ctk.CTkLabel(left, text="", font=T.font(14, True), text_color=T.TEXT)
        self.heading.pack(side="left", pady=T.SPACE_3)
        self.heading_meta = ctk.CTkLabel(left, text="", font=T.font(12), text_color=T.TEXT_2)
        self.heading_meta.pack(side="left", padx=(T.SPACE_2, 0))

        self.panes = ctk.CTkFrame(self.work, fg_color="transparent")
        self.panes.grid_columnconfigure((0, 1), weight=1, uniform="side")
        self.panes.grid_rowconfigure(0, weight=1)
        self.pane = {}
        for col, side in enumerate((LEFT, RIGHT)):
            pane = DiffPane(self.panes, side, "del_char" if side == LEFT else "add_char",
                            on_choose=lambda s=side: self.choose_file(s),
                            on_paste=lambda s=side: self.paste(s),
                            on_clear=lambda s=side: self.clear_side(s),
                            on_click=self._line_clicked)
            pane.grid(row=0, column=col, sticky="nsew", padx=(0, T.SPACE_2) if col == 0 else (T.SPACE_2, 0))
            self.pane[side] = pane

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=T.SIDEBAR_W, fg_color=T.SURFACE, corner_radius=0)
        self.sidebar.pack(side="right", fill="y")
        self.sidebar.pack_propagate(False)
        ctk.CTkFrame(self, width=2, fg_color=T.BORDER, corner_radius=0).pack(side="right", fill="y")

        # Footer stays pinned to the bottom: summary, progress, main action
        self.footer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.footer.pack(side="bottom", fill="x", padx=T.SPACE_4, pady=T.SPACE_4)
        self.summary = ctk.CTkLabel(self.footer, text="", font=T.font(12), text_color=T.TEXT_2,
                                    justify="left", anchor="w", wraplength=T.SIDEBAR_W - 2 * T.SPACE_4)
        self.summary.pack(fill="x", pady=(0, T.SPACE_2))
        self.progress = ctk.CTkProgressBar(self.footer, height=6, corner_radius=3,
                                           fg_color=T.BORDER, progress_color=T.PRIMARY_TEXT)
        self.action_btn = primary_button(self.footer, "Compare", self.run, icon="compare")
        self.action_btn.pack(fill="x")

        # Everything else scrolls, so small laptop screens never clip the result panel
        self.side_scroll = AutoScrollFrame(self.sidebar, fg_color=T.SURFACE, corner_radius=0)
        self.side_scroll.pack(side="top", fill="both", expand=True, padx=(T.SPACE_4, T.SPACE_2),
                              pady=(T.SPACE_4, 0))
        head = ctk.CTkFrame(self.side_scroll, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="", image=T.icon(self.icon, 22, T.PRIMARY_TEXT)).pack(side="left", padx=(0, T.SPACE_2))
        ctk.CTkLabel(head, text=self.title, font=T.font(16, True), text_color=T.TEXT).pack(side="left")
        ctk.CTkLabel(self.side_scroll, text=self.description, font=T.font(12), text_color=T.TEXT_2,
                     justify="left", anchor="w", wraplength=T.CONTENT_W).pack(
            fill="x", pady=(T.SPACE_2, T.SPACE_3))
        divider(self.side_scroll, padx=(0, T.SPACE_3))
        self.options = ctk.CTkFrame(self.side_scroll, fg_color="transparent", width=T.CONTENT_W, height=1)
        self.options.pack(fill="x", pady=(T.SPACE_1, 0), padx=(0, T.SPACE_3))
        self.result_panel = ResultPanel(self.side_scroll)
        self.result_panel.pack(fill="x", pady=(T.SPACE_3, 0), padx=(0, T.SPACE_3))
        self._build_options()

    def _caption(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text, font=T.font(11), text_color=T.TEXT_2, anchor="w",
                     justify="left", wraplength=T.CONTENT_W - 30).pack(fill="x", padx=(28, 0))

    def _build_options(self):
        o = self.options
        changed = self._option_changed
        section_label(o, "Compare")
        self.order_box, self.ignore_order = checkbox(o, "Ignore line order", True, command=changed)
        self._caption(o, "A line counts as the same wherever it is in the other file. Untick for a "
                         "side-by-side diff that keeps the order.")
        self.moves_box, self.detect_moves = checkbox(o, "Detect moved lines", True, command=changed)
        self.chars_box, self.char_diffs = checkbox(o, "Highlight changed characters", True, command=changed)
        ctk.CTkLabel(o, text="Only compare lines containing", font=T.font(12), text_color=T.TEXT,
                     anchor="w").pack(fill="x", pady=(T.SPACE_2, T.SPACE_1))
        self.only_entry = text_entry(o, "e.g. interface   (any case)")
        self.only_entry.pack(fill="x")
        ctk.CTkLabel(o, text="Leave empty to compare every line. Not case sensitive.", font=T.font(11),
                     text_color=T.TEXT_2, anchor="w", justify="left",
                     wraplength=T.CONTENT_W).pack(fill="x", pady=(T.SPACE_1, 0))

        section_label(o, "Ignore")
        self.empty_box, self.ignore_empty = checkbox(o, "Empty lines", False, command=changed)
        self.spaces_box, self.ignore_spaces = checkbox(o, "Changes in spaces", False, command=changed)
        self.all_spaces_box, self.ignore_all_spaces = checkbox(o, "All spaces", False, command=changed)
        self.case_box, self.ignore_case = checkbox(o, "Upper and lower case", False, command=changed)
        self.time_box, self.ignore_timestamps = checkbox(o, "Dates and times", False, command=changed)
        self._caption(o, "2026-10-11 09:12:33, Oct 11 09:12:33 and similar, wherever they are in a line.")
        ctk.CTkLabel(o, text="Text matching (regular expression)", font=T.font(12), text_color=T.TEXT,
                     anchor="w").pack(fill="x", pady=(T.SPACE_2, T.SPACE_1))
        self.pattern_entry = text_entry(o, r"e.g. ^\S+ or seq \d+")
        self.pattern_entry.pack(fill="x")
        for entry in (self.only_entry, self.pattern_entry):
            entry.bind("<Return>", lambda e: self.run(), add="+")
            entry.bind("<KeyRelease>", lambda e: self._option_changed(), add="+")

        section_label(o, "View")
        self.only_box, self.only_diffs = checkbox(o, "Show only differences", False, command=self._redraw)

    # ================================================================ look
    def apply_style(self) -> None:
        """Colours for the plain Tk parts. Called again whenever the theme changes."""
        for pane in self.pane.values():
            pane.apply_style()

    # ================================================================ settings
    _OPTION_KEYS = ("ignore_order", "detect_moves", "char_diffs", "ignore_empty", "ignore_spaces",
                    "ignore_all_spaces", "ignore_case", "ignore_timestamps", "only_diffs")

    def _load_settings(self):
        s = self.app.settings
        for key in self._OPTION_KEYS:
            var: ctk.BooleanVar = getattr(self, key)
            value = s.get(key)
            if isinstance(value, bool):
                var.set(value)
        set_entry_text(self.pattern_entry, s.get("ignore_pattern", ""))
        set_entry_text(self.only_entry, s.get("only_containing", ""))
        self._update_option_states()

    def _save_settings(self):
        s = self.app.settings
        for key in self._OPTION_KEYS:
            s.set(key, getattr(self, key).get())
        s.set("ignore_pattern", self.pattern_entry.get())
        s.set("only_containing", self.only_entry.get())

    def compare_options(self) -> CompareOptions:
        return CompareOptions(
            ignore_order=self.ignore_order.get(),
            detect_moves=self.detect_moves.get(),
            char_diffs=self.char_diffs.get(),
            ignore_empty=self.ignore_empty.get(),
            ignore_changed_spaces=self.ignore_spaces.get(),
            ignore_all_spaces=self.ignore_all_spaces.get(),
            ignore_case=self.ignore_case.get(),
            ignore_timestamps=self.ignore_timestamps.get(),
            ignore_pattern=self.pattern_entry.get(),
            only_containing=self.only_entry.get(),
        )

    def _update_option_states(self):
        # Moves only exist when order matters; "all spaces" already covers "changes in spaces".
        self.moves_box.configure(state="disabled" if self.ignore_order.get() else "normal")
        self.spaces_box.configure(state="disabled" if self.ignore_all_spaces.get() else "normal")

    def _option_changed(self):
        """Options never start a comparison: the user clicks Compare when ready."""
        self._update_option_states()
        self._save_settings()
        self.refresh()

    def options_out_of_date(self) -> bool:
        return self.result is not None and self.compare_options() != self._result_options

    # ================================================================ states
    def show_empty(self):
        self.toolbar.pack_forget()
        self.panes.pack_forget()
        self.drop_zone.pack(fill="both", expand=True)
        self.refresh()

    def show_content(self):
        if self.toolbar.winfo_manager():
            return  # already showing; re-packing would reorder the widgets
        self.drop_zone.pack_forget()
        self.toolbar.pack(fill="x")
        self.panes.pack(fill="both", expand=True, padx=T.SPACE_4, pady=(0, T.SPACE_4))

    def both_loaded(self) -> bool:
        return self.sources[LEFT] is not None and self.sources[RIGHT] is not None

    def refresh(self):
        if self.busy:
            stopping = self._cancel is not None and self._cancel.is_set()
            self.action_btn.configure(text="Stopping..." if stopping else "Stop",
                                      image=T.icon("stop", 18, T.ON_PRIMARY),
                                      state="disabled" if stopping else "normal",
                                      fg_color=T.DANGER_FILL, hover_color=T.DANGER_FILL_HOVER)
        else:
            ready = self.both_loaded()
            self.action_btn.configure(text="Compare", image=T.icon("compare", 18, T.ON_PRIMARY),
                                      state="normal" if ready else "disabled",
                                      fg_color=T.PRIMARY if ready else T.PRIMARY_DISABLED,
                                      hover_color=T.PRIMARY_HOVER)
            if not any(self.sources.values()):
                self.summary.configure(text="Drop two files, or open them one at a time.")
            elif not ready:
                missing = "left" if self.sources[LEFT] is None else "right"
                self.summary.configure(text=f"Add the {missing} file to compare.")
            elif self.result is None:
                self.summary.configure(text="Both files are ready. Click Compare.")
            elif self.options_out_of_date():
                self.summary.configure(text="Options changed. Click Compare to apply them.")
            else:
                self.summary.configure(text="Compare reads both files from disk again.")
        has_result = self.result is not None and not self.busy
        self.export_btn.configure(state="normal" if has_result else "disabled")
        self.swap_btn.configure(state="normal" if self.both_loaded() and not self.busy else "disabled")
        self.reset_btn.configure(state="normal" if any(self.sources.values()) else "disabled")
        self._update_nav()

    def set_drop_highlight(self, on: bool):
        if self.drop_zone.winfo_ismapped():
            self.drop_zone.set_highlight(on)

    # ================================================================ input
    def choose_files(self):
        """The empty state's button: pick both files at once (or one, then the other)."""
        paths = fd.askopenfilenames(title="Choose two files to compare", initialdir=self._start_dir(),
                                    filetypes=TEXT_FILES)
        if paths:
            self.load(list(paths))

    def choose_file(self, side: str):
        path = fd.askopenfilename(title=f"Choose the {side.lower()} file", initialdir=self._start_dir(),
                                  filetypes=TEXT_FILES)
        if path:
            self.load([path], side)

    def _start_dir(self) -> str:
        for source in (self.sources[RIGHT], self.sources[LEFT]):
            if source and source.path:
                return os.path.dirname(source.path)
        last = self.app.settings.get("last_dir", "")
        return last if last and os.path.isdir(last) else os.path.expanduser("~")

    def load(self, paths: list[str], side: Optional[str] = None):
        """Files were chosen or dropped. Two files: older on the left, newer on the right.

        One file goes to ``side``; with no side given, it fills whichever side is empty
        (the right one when both are already filled, as that is usually the newer file).
        """
        files = [p for p in paths if os.path.isfile(p)]
        if not files:
            self.app.set_status("error", "Drop text files, not folders.")
            return
        if len(files) >= 2 and side is None:
            pair = sorted(files[:2], key=_modified_time)
            targets = list(zip((LEFT, RIGHT), pair))
            if len(files) > 2:
                self.app.set_status("info", "Only the first two files were used.")
        else:
            if side is None:
                side = LEFT if self.sources[LEFT] is None else RIGHT
            targets = [(side, files[0])]
        self._read_files(targets)

    def _read_files(self, targets: list[tuple[str, str]]):
        """Read files in a worker thread: a 50 MB log must not freeze the window."""
        self._gen += 1
        gen = self._gen
        self.app.set_status("busy", "Reading " + ", ".join(os.path.basename(p) for _s, p in targets) + "...")

        def work():
            loaded, errors = [], []
            for side, path in targets:
                try:
                    loaded.append((side, read_text_file(path)))
                except CompareError as exc:
                    errors.append(str(exc))
                except Exception:
                    log.exception("Could not read %s", path)
                    errors.append(f"{os.path.basename(path)} could not be read. The details were saved "
                                  "to the log file.")
            self.app.call_soon(lambda: self._files_read(gen, loaded, errors))

        threading.Thread(target=work, daemon=True).start()

    def _files_read(self, gen: int, loaded: list[tuple[str, TextSource]], errors: list[str]):
        if gen != self._gen:
            return
        for side, source in loaded:
            self._set_source(side, source)
            if source.path:
                self.app.settings.set("last_dir", os.path.dirname(source.path))
        if errors:
            self._show_error("Can't open the file", " ".join(errors))
        elif loaded:
            self.app.set_status("info", "Loaded " + " and ".join(s.name for _side, s in loaded) + ".")
        self.refresh()

    def _set_source(self, side: str, source: Optional[TextSource]):
        self.sources[side] = source
        self.pane[side].set_source(source)
        self._forget_result()
        if not any(self.sources.values()):
            self.show_empty()
            return
        self.show_content()
        for s in (LEFT, RIGHT):
            if self.sources[s] is None:
                self.pane[s].show_message("Drop a file on this side,\nor use the open and paste buttons above.")
            else:
                self.pane[s].show_plain(self.sources[s].lines)
        self._set_scroll_link(False)
        self.heading.configure(text="Not compared yet")
        self.heading_meta.configure(text="")

    def paste(self, side: str):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        if not text.strip():
            self.app.set_status("error", "The clipboard has no text to paste.")
            return
        self._gen += 1  # a file still being read for this side must not overwrite the paste
        self._set_source(side, text_from_string(text))
        self.app.set_status("info", f"Pasted {engine.plural(len(self.sources[side].lines), 'line')} "
                                    f"on the {side.lower()}.")
        self.refresh()

    def clear_side(self, side: str):
        if self.busy:
            self.stop()
        self._set_source(side, None)
        self.refresh()

    def reset(self):
        """Start over: both files and the comparison are cleared. The options are kept."""
        if self.busy:
            self.stop()
        self._gen += 1  # a file still being read must not reappear after the reset
        self._set_source(LEFT, None)
        self._set_source(RIGHT, None)
        self.app.set_status("info", "Cleared. Drop two files to start again.")
        self.refresh()

    def swap(self):
        if not self.both_loaded() or self.busy:
            return
        left, right = self.sources[LEFT], self.sources[RIGHT]
        self._set_source(LEFT, right)
        self._set_source(RIGHT, left)
        self.refresh()

    # ================================================================ comparing
    def run(self):
        """The main action: Compare (reloading both files), or Stop while one is running."""
        if self.busy:
            self.stop()
        elif self.both_loaded():
            self.start_compare(reload=True)

    def stop(self):
        if self.busy and self._cancel is not None:
            self._cancel.set()
            self.app.set_status("info", "Stopping...")
            self.refresh()

    def start_compare(self, reload: bool):
        if not self.both_loaded():
            return
        options = self.compare_options()
        try:
            engine.build_ignore_pattern(options.ignore_pattern, options.ignore_timestamps)
        except CompareError as exc:
            self._show_error("Can't compare yet", str(exc))
            return
        self._save_settings()

        self._gen += 1
        gen = self._gen
        cancel = self._cancel = threading.Event()
        sources = dict(self.sources)
        self.busy = True
        self.result_panel.clear()
        self.heading.configure(text="Comparing...")
        self.progress.configure(mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, T.SPACE_2), before=self.action_btn)
        self.progress.start()
        self.app.set_status("busy", "Comparing...")
        self.refresh()

        def work():
            try:
                fresh = dict(sources)
                if reload:  # files may have changed on disk since they were opened
                    for side, source in sources.items():
                        if source is not None and source.path:
                            fresh[side] = read_text_file(source.path)
                result = engine.compare(fresh[LEFT], fresh[RIGHT], options, cancel)
            except CompareError as exc:
                message = str(exc)  # copied: Python deletes ``exc`` when this block ends
                self.app.call_soon(lambda: self._compare_failed(gen, message, cancel.is_set()))
            except Exception:
                log.exception("Compare failed")
                self.app.call_soon(lambda: self._compare_failed(
                    gen, "Something unexpected went wrong. The details were saved to the log file.", False))
            else:
                self.app.call_soon(lambda: self._compare_done(gen, fresh, result, options))

        threading.Thread(target=work, daemon=True).start()

    def _finish(self):
        self.busy = False
        self.progress.stop()
        self.progress.pack_forget()

    def _compare_failed(self, gen: int, message: str, stopped: bool):
        if gen != self._gen:
            return
        self._finish()
        if stopped:
            self.heading.configure(text="Stopped")
            self.result_panel.show("info", "Comparison stopped", "Click Compare to run it again.")
            self.app.set_status("info", "Comparison stopped.")
        else:
            self.heading.configure(text="Can't compare")
            self._show_error("Can't compare", message)
        self.refresh()

    def _compare_done(self, gen: int, sources: dict[str, TextSource], result: CompareResult,
                      options: CompareOptions):
        if gen != self._gen:
            return
        self._finish()
        for side in (LEFT, RIGHT):
            if sources[side] is not self.sources[side]:  # reloaded from disk
                self.sources[side] = sources[side]
                self.pane[side].set_source(sources[side])
        self.result = result
        self._result_options = options
        self._block = -1
        self._redraw()
        self._show_summary()
        if result.blocks:
            self.goto_block(0)
        self.refresh()

    def _forget_result(self):
        self.result = None
        self._result_options = None
        self._block = -1
        self.result_panel.clear()
        for pane in self.pane.values():
            pane.mark_current([])

    # ================================================================ showing the result
    def _rows(self, side: str) -> list[int]:
        """Which rows to show on one side: all, or only the differences."""
        result = self.result
        lines = result.left if side == LEFT else result.right
        if not self.only_diffs.get():
            return list(range(len(lines)))
        if result.aligned:
            return [i for i in range(len(result.left))
                    if result.left[i].kind in DIFF_KINDS or result.right[i].kind in DIFF_KINDS]
        return [i for i, ln in enumerate(lines) if ln.kind in DIFF_KINDS]

    def _redraw(self):
        self._save_settings()
        if self.result is None:
            return
        for side in (LEFT, RIGHT):
            lines = self.result.left if side == LEFT else self.result.right
            self.pane[side].show_lines(lines, self._rows(side))
        # In the line-order view both sides have the same rows, so they scroll together.
        self._set_scroll_link(self.result.aligned)
        if 0 <= self._block < len(self.result.blocks):
            self.goto_block(self._block)

    def _set_scroll_link(self, linked: bool):
        left, right = self.pane[LEFT], self.pane[RIGHT]
        left.y_listener = right.follow_y if linked else None
        right.y_listener = left.follow_y if linked else None

    def _show_summary(self):
        r = self.result
        took = f"{r.seconds:.1f} s" if r.seconds >= 0.1 else "under 0.1 s"
        notes = self._notes()
        actions = [("Export to Excel", "export", self.export)] if not r.identical else []
        if r.identical:
            heading = "The files are the same"
            detail = " ".join([f"{engine.plural(r.same, 'line')} match.", *notes])
            self.result_panel.show("success", heading, detail)
            self.app.set_status("success", f"{heading}.")
        else:
            heading = engine.plural(r.differences, "difference")
            detail = "\n".join(f"• {line}" for line in engine.summary_lines(r))
            if notes:
                detail += "\n\n" + " ".join(notes)
            self.result_panel.show("info", heading, detail, actions)
            self.app.set_status("success", f"{heading} found in {took}.")
        self.heading.configure(text=heading)
        # The time taken is in the status bar; the toolbar is short of room on a laptop screen.

    def _notes(self) -> list[str]:
        """Things that explain a surprising result."""
        left, right = self.sources[LEFT], self.sources[RIGHT]
        notes = []
        if left.line_ending and right.line_ending and left.line_ending != right.line_ending:
            notes.append(f"Line endings differ ({left.line_ending} and {right.line_ending}); "
                         "that is not counted as a difference.")
        if left.encoding and right.encoding and left.encoding != right.encoding:
            notes.append(f"The files are saved in different encodings ({left.encoding} and "
                         f"{right.encoding}); the text itself was compared.")
        if self.result.pairing_limited:
            notes.append("There were too many differences to check every pair of lines for being "
                         "similar, so lines were only compared with lines in a similar place.")
        return notes

    # ================================================================ navigation
    def _block_rows(self, index: int) -> tuple[list[int], list[int]]:
        """The rows of one difference block, on each side."""
        r = self.result
        block = r.blocks[index]

        def run(lines, start, kinds) -> list[int]:
            rows = []
            row = start
            while row < len(lines) and lines[row].kind in kinds:
                rows.append(row)
                row += 1
            return rows

        if r.aligned:
            rows = []
            row = block.left
            while row < len(r.left) and (r.left[row].kind in DIFF_KINDS or r.right[row].kind in DIFF_KINDS):
                rows.append(row)
                row += 1
            return rows, rows
        left_rows = run(r.left, block.left, {REMOVED, CHANGED}) if block.left is not None else []
        right_rows = run(r.right, block.right, {ADDED}) if block.kind == ADDED else []
        # A changed line's partner may be anywhere on the right: show each partner.
        right_rows += [r.left[row].partner for row in left_rows
                       if r.left[row].kind == CHANGED and r.left[row].partner is not None]
        return left_rows, right_rows

    def goto_block(self, index: int):
        if not self.result or not self.result.blocks:
            return
        self._block = index % len(self.result.blocks)
        left_rows, right_rows = self._block_rows(self._block)
        self.pane[LEFT].mark_current(left_rows)
        self.pane[RIGHT].mark_current(right_rows)
        if self.result.aligned:
            self.pane[LEFT].see_row(left_rows[0])
        else:
            if left_rows:
                self.pane[LEFT].see_row(left_rows[0])
            if right_rows:
                self.pane[RIGHT].see_row(right_rows[0])
        self._update_nav()

    def next_diff(self):
        self.goto_block(self._block + 1)

    def prev_diff(self):
        self.goto_block(self._block - 1 if self._block > 0 else -1)

    def first_diff(self):
        self.goto_block(0)

    def last_diff(self):
        self.goto_block(-1)

    def _update_nav(self):
        n = len(self.result.blocks) if self.result and not self.busy else 0
        self.counter.configure(text=f"{self._block + 1} of {n}" if n and self._block >= 0 else "")
        state = "normal" if n else "disabled"
        for btn in (self.first_btn, self.prev_btn, self.next_btn, self.last_btn):
            btn.configure(state=state)

    def _line_clicked(self, side: str, row: int):
        """Click a changed or moved line: show the line it pairs with on the other side."""
        if not self.result:
            return
        lines = self.result.left if side == LEFT else self.result.right
        if row >= len(lines):
            return
        ln = lines[row]
        if ln.kind not in (CHANGED, MOVED) or ln.partner is None:
            return
        other = RIGHT if side == LEFT else LEFT
        self.pane[side].mark_current([row])
        self.pane[other].mark_current([ln.partner])
        if not self.result.aligned or ln.kind == MOVED:
            self.pane[other].see_row(ln.partner)
        where = "right" if other == RIGHT else "left"
        number = (self.result.right if other == RIGHT else self.result.left)[ln.partner].number
        self.app.set_status("info", f"Line {ln.number:,} pairs with line {number:,} on the {where}.")

    # ================================================================ export
    def export(self):
        if not self.result or self.busy:
            return
        left, right = self.sources[LEFT], self.sources[RIGHT]
        stem = lambda s: re.sub(r'[\\/:*?"<>|]+', " ", os.path.splitext(s.name)[0]).strip()[:40] or "text"
        start = self.app.settings.get("export_dir") or (os.path.dirname(right.path) if right.path else "") \
            or os.path.expanduser("~")
        path = fd.asksaveasfilename(title="Export the differences to Excel", initialdir=start,
                                    initialfile=f"Compare - {stem(left)} vs {stem(right)}.xlsx",
                                    defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if not path:
            return
        try:
            rows = export_excel(self.result, left, right, self._result_options, path)
        except CompareError as exc:
            self._show_error("Not exported", str(exc))
            return
        except Exception:
            log.exception("Export failed")
            self._show_error("Not exported", "Something unexpected went wrong. The details were saved "
                                             "to the log file.")
            return
        self.app.settings.set("export_dir", os.path.dirname(path))
        self.result_panel.show("success", "Exported to Excel",
                               f"{engine.plural(rows, 'difference')} saved to {os.path.basename(path)}.",
                               [("Open", "file", lambda: open_path(path)),
                                ("Show in folder", "folder", lambda: reveal_in_folder(path))])
        self.app.set_status("success", f"Saved {os.path.basename(path)}.")

    # ================================================================ errors
    def _show_error(self, title: str, message: str) -> None:
        self.result_panel.show("error", title, message)
        self.app.set_status("error", message)


def _modified_time(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
