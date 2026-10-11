"""Main window for EZ Text Compare."""

from __future__ import annotations

import logging
import os
import queue
import sys
import tkinter as tk
import tkinter.messagebox as messagebox
import traceback
import webbrowser

import customtkinter as ctk

from . import APP_NAME, BRAND, COPYRIGHT, WEBSITE, __version__
from . import theme as T
from .system import Settings, log_dir, open_path, resource_path, set_window_icon
from .tools import LEFT, RIGHT, CompareTool
from .widgets import icon_button

log = logging.getLogger("ezcompare.app")

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # the app must still run if drag-and-drop can't load
    TkinterDnD = None
    DND_FILES = None


class _Root(ctk.CTk, *( [TkinterDnD.DnDWrapper] if TkinterDnD else [] )):
    def __init__(self):
        super().__init__()
        self.dnd_ok = False
        if TkinterDnD:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_ok = True
            except Exception:
                log.exception("Drag and drop is unavailable")


class App(_Root):
    def __init__(self, settings: Settings, startup_files: list[str] | None = None):
        self.settings = settings
        ctk.set_appearance_mode(settings.get("theme", "system"))
        super().__init__()
        self._calls: queue.SimpleQueue = queue.SimpleQueue()
        self._status_job = None

        self.title(APP_NAME)
        self._set_window_icon(self)
        # CustomTkinter re-applies its own title-bar handling shortly after start-up,
        # which can drop the icon, so set it once more when the window has settled.
        self.after(400, lambda: self._set_window_icon(self))
        self.configure(fg_color=T.BG)
        self._place_window()
        self.minsize(980, 640)

        self._build_header()
        self._build_status_bar()
        self.tool = CompareTool(self, self)
        self.tool.pack(fill="both", expand=True)

        # The two text panes are plain Tk widgets: repaint them on theme changes,
        # including when Windows itself switches between light and dark.
        ctk.AppearanceModeTracker.add(self._on_appearance_change, self)

        self._bind_keys()
        self._setup_dnd()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._drain_job = self.after(30, self._drain_calls)
        if startup_files:
            self.after(200, lambda: self.tool.load(startup_files))

    # ================================================================ threading
    def call_soon(self, fn) -> None:
        """Thread-safe: schedule ``fn`` on the Tk main thread. Workers must use this."""
        self._calls.put(fn)

    def _drain_calls(self):
        try:
            while True:
                fn = self._calls.get_nowait()
                try:
                    fn()
                except Exception:
                    self.report_callback_exception(*sys.exc_info())
        except queue.Empty:
            pass
        self._drain_job = self.after(30, self._drain_calls)

    # ================================================================ window
    def _set_window_icon(self, window):
        ico = resource_path("assets", "app.ico")
        # Preferred path on Windows: let the OS pick the right size from the .ico.
        if set_window_icon(window, ico):
            return
        try:
            if sys.platform == "win32":
                window.iconbitmap(ico)
            else:
                self._icon_photo = tk.PhotoImage(file=resource_path("assets", "logo.png"))
                window.iconphoto(True, self._icon_photo)
        except tk.TclError:
            log.warning("Could not set window icon")

    def _place_window(self):
        scale = ctk.ScalingTracker.get_window_scaling(self)
        sw, sh = self.winfo_screenwidth() / scale, self.winfo_screenheight() / scale
        w, h = int(min(1280, sw - 80)), int(min(820, sh - 120))
        self.geometry(f"{w}x{h}+{int((sw - w) / 2)}+{int(max(0, (sh - h) / 2 - 20))}")

    # ================================================================ header
    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=0, height=60)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.pack(side="left", padx=T.SPACE_4)
        ctk.CTkLabel(brand, text="", image=T.asset_image("logo.png", 32)).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(brand, text=APP_NAME, font=T.font(16, True), text_color=T.TEXT).pack(side="left")
        ctk.CTkLabel(brand, text=f"by {BRAND}", font=T.font(12), text_color=T.TEXT_3).pack(side="left", padx=(8, 0), pady=(3, 0))

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right", padx=T.SPACE_3)
        icon_button(right, "info", self.show_about).pack(side="right")
        self.theme_btn = icon_button(right, "moon", self.toggle_theme)
        self.theme_btn.pack(side="right", padx=(0, 2))
        self._paint_theme_button()
        ctk.CTkButton(right, text=f"More {BRAND} tools", command=lambda: webbrowser.open(WEBSITE),
                      fg_color="transparent", hover_color=T.HOVER, text_color=T.PRIMARY_TEXT,
                      font=T.font(12, True), height=34, corner_radius=T.RADIUS_S,
                      image=T.icon("external", 15, T.PRIMARY_TEXT), compound="right").pack(side="right", padx=(0, T.SPACE_2))
        # One tool, so there is no tool navigation bar (and no orange underline beneath it).
        ctk.CTkFrame(self, height=2, fg_color=T.BORDER, corner_radius=0).pack(fill="x")

    # ================================================================ status bar
    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=0, height=30)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        ctk.CTkFrame(self, height=2, fg_color=T.BORDER, corner_radius=0).pack(side="bottom", fill="x")
        # Right-hand labels are packed first, so a long message on the left can't cover them.
        ctk.CTkLabel(bar, text=f"v{__version__}", font=T.font(11), text_color=T.TEXT_3).pack(side="right", padx=(8, T.SPACE_3))
        ctk.CTkLabel(bar, text="Works offline. Your files never leave this PC.", font=T.font(11),
                     text_color=T.TEXT_3).pack(side="right")
        ctk.CTkLabel(bar, text="", image=T.icon("shield", 13, T.TEXT_3)).pack(side="right", padx=(0, 6))
        self.status_icon = ctk.CTkLabel(bar, text="", width=16)
        self.status_icon.pack(side="left", padx=(T.SPACE_3, 6))
        self.status_text = ctk.CTkLabel(bar, text="Ready.", font=T.font(11), text_color=T.TEXT_2, anchor="w")
        self.status_text.pack(side="left", fill="x", expand=True)

    def set_status(self, kind: str, message: str):
        icons = {"success": ("success", T.SUCCESS), "error": ("error", T.DANGER),
                 "info": ("info", T.PRIMARY_TEXT)}
        if kind in icons:
            name, color = icons[kind]
            self.status_icon.configure(image=T.icon(name, 14, color))
        else:
            self.status_icon.configure(image=T.blank(14))
        self.status_text.configure(text=message, text_color=T.DANGER if kind == "error" else T.TEXT_2)
        if self._status_job:
            self.after_cancel(self._status_job)
            self._status_job = None
        if kind in ("success", "info"):
            self._status_job = self.after(10000, lambda: self.set_status("ready", "Ready."))

    # ================================================================ drag and drop
    def _setup_dnd(self):
        if not self.dnd_ok:
            return
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<DropEnter>>", lambda e: (self.tool.set_drop_highlight(True), e.action)[1])
        self.dnd_bind("<<DropLeave>>", lambda e: (self.tool.set_drop_highlight(False), e.action)[1])
        self.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event):
        self.tool.set_drop_highlight(False)
        paths = list(self.splitlist(event.data))
        if not paths:
            return event.action
        if self.tool.busy:
            self.tool.stop()
        side = None
        if len(paths) == 1 and self.tool.panes.winfo_ismapped():
            # One file dropped on the two panes: it goes on the side it was dropped on.
            middle = self.tool.panes.winfo_rootx() + self.tool.panes.winfo_width() / 2
            side = LEFT if event.x_root < middle else RIGHT
        self.tool.load(paths, side)
        return event.action

    # ================================================================ keyboard
    def _bind_keys(self):
        self.bind("<Control-o>", lambda e: self.tool.choose_files())
        self.bind("<F5>", lambda e: self.tool.run())
        self.bind("<Control-Return>", lambda e: self.tool.run())
        self.bind("<Control-e>", lambda e: self.tool.export())
        self.bind("<Escape>", lambda e: self.tool.stop())
        # Next / previous difference: F3 like a search, Alt+arrows like most diff tools.
        self.bind("<F3>", lambda e: self.tool.next_diff())
        self.bind("<Shift-F3>", lambda e: self.tool.prev_diff())
        self.bind("<Alt-Down>", lambda e: self.tool.next_diff())
        self.bind("<Alt-Up>", lambda e: self.tool.prev_diff())
        self.bind("<Alt-Home>", lambda e: self.tool.first_diff())
        self.bind("<Alt-End>", lambda e: self.tool.last_diff())

    # ================================================================ theme
    def _paint_theme_button(self):
        dark = ctk.get_appearance_mode() == "Dark"
        self.theme_btn.configure(image=T.icon("sun" if dark else "moon", 18, T.TEXT_2))

    def toggle_theme(self):
        new = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
        ctk.set_appearance_mode(new)
        self.settings.set("theme", new)

    def _on_appearance_change(self, *_):
        # CustomTkinter silently ignores errors in these callbacks, so log them ourselves.
        try:
            self._paint_theme_button()
            self.tool.apply_style()
        except Exception:
            log.exception("Could not repaint after a theme change")

    # ================================================================ dialogs
    def _center(self, win):
        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{x}+{y}")

    def show_about(self):
        win = ctk.CTkToplevel(self)
        win.title(f"About {APP_NAME}")
        win.resizable(False, False)
        win.configure(fg_color=T.SURFACE)
        win.transient(self)
        win.after(250, lambda: self._set_window_icon(win))  # CTkToplevel resets its icon at 200 ms
        box = ctk.CTkFrame(win, fg_color="transparent")
        box.pack(padx=40, pady=32)
        ctk.CTkLabel(box, text="", image=T.asset_image("logo.png", 76)).pack()
        ctk.CTkLabel(box, text=APP_NAME, font=T.font(18, True), text_color=T.TEXT).pack(pady=(T.SPACE_3, 0))
        ctk.CTkLabel(box, text=f"Version {__version__}", font=T.font(12), text_color=T.TEXT_2).pack()
        ctk.CTkLabel(box, text="Compare two text, log or config files and see which lines\n"
                               "were added, removed or changed.\n"
                               "Works 100% offline. Your files never leave this PC.\n"
                               "Free to use and free to share.",
                     font=T.font(12), text_color=T.TEXT_2, justify="center").pack(pady=T.SPACE_3)
        links = ctk.CTkFrame(box, fg_color="transparent")
        links.pack()
        for text, cmd in ((WEBSITE.replace("https://", ""), lambda: webbrowser.open(WEBSITE)),
                          ("Open-source licences", self._open_licences),
                          ("Log files", lambda: open_path(log_dir()))):
            ctk.CTkButton(links, text=text, command=cmd, fg_color="transparent", hover_color=T.HOVER,
                          text_color=T.PRIMARY_TEXT, font=T.font(12), height=28, width=10).pack(side="left", padx=2)
        ctk.CTkLabel(box, text=COPYRIGHT, font=T.font(11), text_color=T.TEXT_3).pack(pady=(T.SPACE_3, 0))
        self._center(win)
        win.after(50, win.grab_set)
        win.bind("<Escape>", lambda e: win.destroy())
        win.focus_set()

    def _open_licences(self):
        path = resource_path("THIRD_PARTY_NOTICES.md")
        if os.path.exists(path):
            open_path(path)

    # ================================================================ lifecycle
    def _on_close(self):
        # Comparing only reads files, so closing mid-compare is always safe: just stop it.
        self.tool.stop()
        self.destroy()

    def destroy(self):
        try:
            self.after_cancel(self._drain_job)
        except (AttributeError, tk.TclError):
            pass
        try:
            ctk.AppearanceModeTracker.remove(self._on_appearance_change)
        except Exception:
            pass
        super().destroy()

    def report_callback_exception(self, exc, val, tb):
        """Any unhandled error in the UI: log it and tell the user where to find it."""
        log.error("Unhandled UI error:\n%s", "".join(traceback.format_exception(exc, val, tb)))
        try:
            messagebox.showerror(APP_NAME, "Something went wrong, but your files are safe.\n\n"
                                           f"Details were saved to:\n{log_dir()}")
        except tk.TclError:
            pass
