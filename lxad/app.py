"""
Application Entry Point for LXAD.

Runs the complete desktop application:
    python -m lxad.app
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys

from PySide6.QtWidgets import QApplication

from lxad.ui.main_window import MainWindow
from lxad.ui.permissions_dialog import PermissionsDialog, is_admin


def setup_logging() -> None:
    """Configure rotating file and console logging."""
    os.makedirs("data", exist_ok=True)
    log_path = os.path.join("data", "lxad.log")

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] (%(threadName)s) %(name)s: %(message)s"
    )

    # Rotating file handler (5 MB per file, max 3 backups)
    file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def main() -> int:
    """Launch the LXAD Desktop GUI Application."""
    setup_logging()
    logging.info("Starting LXAD Desktop Application...")

    app = QApplication(sys.argv)
    app.setApplicationName("LXAD")
    app.setOrganizationName("CMRIT-CSE-AIML")

    # Show permissions notice on launch if not elevated
    if not is_admin() and "--no-permissions-dialog" not in sys.argv:
        perm_dialog = PermissionsDialog()
        perm_dialog.exec()

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
