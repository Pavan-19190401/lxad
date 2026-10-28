"""
Alerts View for LXAD with Jet-Black Card Aesthetic.

Interactive alert table and explainability inspection card styled with
subtle borders, rounded corners, and clear severity indicators.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QLabel, QPushButton, QHeaderView, QFrame, QTextEdit
)

from lxad.ui.styles import get_severity_badge_style


class AlertsView(QWidget):
    """Real-time alerts table and explainability inspector."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._alerts_data: List[Dict[str, Any]] = []
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Splitter: Table on top, Detail drawer on bottom
        splitter = QSplitter(Qt.Vertical)

        # TOP CARD: Alert Events Stream
        tbl_frame = QFrame()
        tbl_frame.setProperty("class", "card-panel")
        tbl_layout = QVBoxLayout(tbl_frame)
        tbl_layout.setContentsMargins(14, 14, 14, 14)
        tbl_layout.setSpacing(10)

        top_bar = QHBoxLayout()
        lbl_tbl_title = QLabel("Live Detection Feed")
        lbl_tbl_title.setStyleSheet("color: #7d8590; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;")
        top_bar.addWidget(lbl_tbl_title)
        top_bar.addStretch()

        self.btn_clear = QPushButton("Clear View")
        self.btn_clear.clicked.connect(self.clear_alerts)
        top_bar.addWidget(self.btn_clear)
        tbl_layout.addLayout(top_bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Severity", "Score", "Module", "Anomaly Type"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        tbl_layout.addWidget(self.table)
        splitter.addWidget(tbl_frame)

        # BOTTOM CARD: Explainability & Remedial Actions Drawer
        detail_frame = QFrame()
        detail_frame.setProperty("class", "card-panel")
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(10)

        lbl_drawer_header = QLabel("Explainable Root-Cause Justification & Actions")
        lbl_drawer_header.setStyleSheet("color: #7d8590; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;")
        detail_layout.addWidget(lbl_drawer_header)

        self.lbl_headline = QLabel("Select an alert above to inspect root-cause analysis.")
        self.lbl_headline.setStyleSheet("font-weight: 600; font-size: 14px; color: #f0f2f5;")
        self.lbl_headline.setWordWrap(True)
        detail_layout.addWidget(self.lbl_headline)

        self.txt_justification = QTextEdit()
        self.txt_justification.setReadOnly(True)
        self.txt_justification.setStyleSheet("""
            QTextEdit {
                font-size: 13px;
                line-height: 1.5;
                background-color: #0c0e12;
                border: 1px solid #21252d;
                border-radius: 6px;
                padding: 10px 12px;
                color: #e6edf3;
            }
            QTextEdit:hover {
                border-color: #333945;
            }
        """)
        detail_layout.addWidget(self.txt_justification)

        lbl_actions_title = QLabel("💡 Suggested Remedial Actions:")
        lbl_actions_title.setStyleSheet("font-weight: 600; color: #58a6ff; font-size: 12px;")
        detail_layout.addWidget(lbl_actions_title)

        self.txt_actions = QTextEdit()
        self.txt_actions.setReadOnly(True)
        self.txt_actions.setMaximumHeight(85)
        self.txt_actions.setStyleSheet("""
            QTextEdit {
                font-size: 12px;
                line-height: 1.4;
                background-color: #0c0e12;
                border: 1px solid #21252d;
                border-radius: 6px;
                padding: 8px 12px;
                color: #e6edf3;
            }
            QTextEdit:hover {
                border-color: #333945;
            }
        """)
        detail_layout.addWidget(self.txt_actions)

        splitter.addWidget(detail_frame)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    def add_alert(self, alert_dict: Dict[str, Any]) -> None:
        """Insert alert into top of table."""
        self._alerts_data.insert(0, alert_dict)
        self.table.insertRow(0)

        ts = alert_dict.get("timestamp", 0.0)
        dt_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        severity = alert_dict.get("severity", "Medium")
        score = alert_dict.get("score", 0.0)
        module = alert_dict.get("module", "System")
        anomaly_type = alert_dict.get("anomaly_type", "Anomaly")

        item_ts = QTableWidgetItem(dt_str)
        item_ts.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(0, 0, item_ts)

        item_sev = QTableWidgetItem(severity.upper())
        item_sev.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(0, 1, item_sev)

        item_score = QTableWidgetItem(f"{score:.0f}")
        item_score.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(0, 2, item_score)

        self.table.setItem(0, 3, QTableWidgetItem(module))
        self.table.setItem(0, 4, QTableWidgetItem(anomaly_type))

        self.table.selectRow(0)

    def _on_selection_changed(self) -> None:
        """Update detail panel on selection."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row_idx = selected_rows[0].row()
        if row_idx >= len(self._alerts_data):
            return

        data = self._alerts_data[row_idx]
        score = data.get("score", 0.0)
        severity = data.get("severity", "Medium")
        module = data.get("module", "System")
        anomaly_type = data.get("anomaly_type", "Anomaly")
        justification = data.get("justification", "")
        detectors = data.get("detectors_fired", [])
        rules = data.get("matched_rules", [])
        actions = data.get("remedial_actions", [])

        self.lbl_headline.setText(
            f"Alert #{len(self._alerts_data) - row_idx}: Score {score:.0f} [{severity.upper()}] - {anomaly_type} ({module})"
        )

        fired_str = ", ".join(detectors) if detectors else "Statistical Ensemble"
        rules_str = ", ".join(rules) if rules else "Statistical Heuristics"

        full_html = f"""
        <div style='font-family: -apple-system, Segoe UI, sans-serif; font-size: 13px; line-height: 1.5; color: #e6edf3;'>
            <p style='margin-bottom: 8px;'>{justification}</p>
            <p style='color: #7d8590; margin-top: 6px; font-size: 12px;'>
                <b>Detectors Fired:</b> <span style='color: #58a6ff;'>{fired_str}</span> &nbsp;|&nbsp; 
                <b>Rules Matched:</b> <span style='color: #d29922;'>{rules_str}</span>
            </p>
        </div>
        """
        self.txt_justification.setHtml(full_html)

        if actions:
            action_html = "<ol style='margin-top: 2px; padding-left: 20px; color: #c9d1d9; font-size: 12px;'>"
            for act in actions:
                action_html += f"<li style='margin-bottom: 3px;'>{act}</li>"
            action_html += "</ol>"
            self.txt_actions.setHtml(action_html)
        else:
            self.txt_actions.setPlainText("No specific remediation required. Continuous monitoring active.")

    def clear_alerts(self) -> None:
        self._alerts_data.clear()
        self.table.setRowCount(0)
        self.lbl_headline.setText("No active alerts.")
        self.txt_justification.clear()
        self.txt_actions.clear()
