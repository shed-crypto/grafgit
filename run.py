#!/usr/bin/env python3
"""GrafGit — Desktop Entrypoint.

Usage:
    python run.py [path_to_git_repository]
"""

import os
import sys

# Enable crisp DPI scaling on Windows (prevents 125%/150% blurriness)
if sys.platform == "win32":
    try:
        import ctypes
        # SetProcessDpiAwareness(2) -> Per-Monitor V2 awareness
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Ensure grafgit package directory is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from grafgit.ui.main_window import MainWindow


def main():
    target_dir = sys.argv[1] if len(sys.argv) > 1 else SCRIPT_DIR
    app = MainWindow(target_dir=target_dir)
    app.mainloop()


if __name__ == "__main__":
    main()
