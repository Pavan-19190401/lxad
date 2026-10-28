"""
First-Launch Permissions and System Access Notice for LXAD.

Explains the read-only, local-only architecture, checks Administrator privilege level,
offers seamless elevation relaunch, and handles standard user degradation gracefully.
"""

from __future__ import annotations

import ctypes
import os
import platform
import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextBrowser, QMessageBox
)


def is_admin() -> bool:
    """Check if the current process has elevated administrative rights."""
    if platform.system().lower() != "windows":
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin() -> None:
    """Trigger Windows UAC prompt to restart process elevated."""
    if platform.system().lower() == "windows":
        try:
            params = " ".join([f'"{arg}"' for arg in sys.argv])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, None, 1
            )
            sys.exit(0)
        except Exception as e:
            QMessageBox.critical(None, "Elevation Error", f"Failed to elevate process: {e}")


class PermissionsDialog(QDialog):
    """Explains system visibility, privacy boundaries, and privilege elevation."""

    def __init__(self, parent: Optional[QDialog] = None):
        super().__init__(parent)
        self.setWindowTitle("LXAD System Transparency & Permissions")
        self.resize(540, 420)
        self.setModal(True)
        self.elevated = is_admin()
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        lbl_title = QLabel("🛡️ LXAD System Access & Safety Guarantee")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #58a6ff;")
        layout.addWidget(lbl_title)

        # Privilege status banner
        banner = QFrame()
        b_layout = QHBoxLayout(banner)
        b_layout.setContentsMargins(10, 8, 10, 8)

        if self.elevated:
            banner.setStyleSheet("background-color: rgba(46, 160, 67, 0.15); border: 1px solid #2ea043; border-radius: 6px;")
            lbl_status = QLabel("✅ Running with Administrator Privileges (Full-PC visibility enabled)")
            lbl_status.setStyleSheet("color: #3fb950; font-weight: bold;")
        else:
            banner.setStyleSheet("background-color: rgba(210, 153, 34, 0.15); border: 1px solid #d29922; border-radius: 6px;")
            lbl_status = QLabel("⚠️ Running in Standard User Mode (Gracefully Degraded)")
            lbl_status.setStyleSheet("color: #d29922; font-weight: bold;")

        b_layout.addWidget(lbl_status)
        layout.addWidget(banner)

        # Description text
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml("""
        <p><b>Read-Only PC Observation Framework</b></p>
        <p>This software monitors system behavior to detect anomalies and explain root causes. It observes:</p>
        <ul>
            <li><b>Hardware Metrics:</b> Per-core CPU, RAM, Swap, Disk I/O, Network I/O.</li>
            <li><b>Process Activity:</b> Process names, CPU/RAM percentages, parent-child spawns.</li>
            <li><b>System Event Logs:</b> Application and System errors (Security audit log requires Admin).</li>
            <li><b>Filesystem Signals:</b> High-frequency write bursts in Temp folders.</li>
        </ul>
        <p><b>100% Local & Non-Invasive:</b></p>
        <ul>
            <li>🔒 <b>No modifications:</b> The app NEVER modifies, kills, or deletes files or processes.</li>
            <li>🌐 <b>No telemetry:</b> All analysis occurs entirely locally; zero outbound network calls.</li>
        </ul>
        <p style='color: #8b949e; font-size: 11px;'>
            If running without Administrator privileges, the Security log is silenced gracefully. All other collectors continue normal operation.
        </p>
        """)
        layout.addWidget(browser)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        if not self.elevated and platform.system().lower() == "windows":
            btn_elevate = QPushButton("🛡️ Run as Administrator (Full Access)")
            btn_elevate.setProperty("class", "inject")
            btn_elevate.clicked.connect(relaunch_as_admin)
            btn_layout.addWidget(btn_elevate)

        btn_continue = QPushButton("Proceed with Monitoring" if self.elevated else "Continue in Standard Mode")
        btn_continue.clicked.connect(self.accept)
        btn_layout.addWidget(btn_continue)

        layout.addLayout(btn_layout)
