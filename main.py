"""EZ Text Compare by EZKerja: entry point.

Run from source:   python main.py [left-file] [right-file]
Files given on the command line (or dropped on the .exe) are loaded at start-up.
"""

from __future__ import annotations

import logging
import sys
import threading
import traceback


def _file_arguments() -> list[str]:
    """Up to two file paths from the command line, e.g. two files dropped on the .exe."""
    return [arg.strip().strip('"') for arg in sys.argv[1:] if not arg.startswith("-")][:2]


def main() -> None:
    from ezcompare import APP_ID, APP_NAME, __version__
    from ezcompare.system import Settings, log_dir, set_windows_app_id, setup_logging

    setup_logging()
    log = logging.getLogger("ezcompare")
    log.info("Starting %s %s", APP_NAME, __version__)

    def crash(exc_type, exc, tb):
        log.critical("Unhandled error:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        try:
            import tkinter.messagebox as mb
            mb.showerror(APP_NAME, f"{APP_NAME} hit a problem and needs to close.\n\n"
                                   f"Details were saved to:\n{log_dir()}")
        except Exception:
            pass

    sys.excepthook = crash
    threading.excepthook = lambda a: log.error(
        "Error in background thread:\n%s",
        "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))

    set_windows_app_id(APP_ID)

    from ezcompare.app import App
    app = App(Settings(), startup_files=_file_arguments())
    app.mainloop()


if __name__ == "__main__":
    main()
