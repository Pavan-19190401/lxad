"""
History and Audit View for LXAD.

Allows querying, filtering, and auditing past anomaly detection events from SQLite,
with one-click export to CSV and professional PDF reports via ReportLab.
"""

from __future__ import annotations

import csv
import datetime
import os
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QDateEdit, QFrame
)

from lxad.core.storage import SQLiteStorage


class HistoryView(QWidget):
    """Historical audit view with multi-criteria filtering and export."""

    def __init__(self, storage: SQLiteStorage, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.storage = storage
        self._cached_alerts: List[Dict[str, Any]] = []
        self._init_ui()
        self.refresh_data()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Filter Card Container
        filter_card = QFrame()
        filter_card.setProperty("class", "card-panel")
        f_layout = QVBoxLayout(filter_card)
        f_layout.setContentsMargins(14, 14, 14, 14)

        lbl_f_title = QLabel("Historical Incident Filters")
        lbl_f_title.setStyleSheet("color: #7d8590; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;")
        f_layout.addWidget(lbl_f_title)

        filter_box = QHBoxLayout()
        filter_box.setSpacing(10)

        # Severity Filter
        lbl_sev = QLabel("Severity:")
        lbl_sev.setStyleSheet("color: #8b949e; font-weight: 500; font-size: 12px;")
        filter_box.addWidget(lbl_sev)
        self.combo_severity = QComboBox()
        self.combo_severity.addItems(["All", "Critical", "High", "Medium", "Low"])
        self.combo_severity.setFixedHeight(32)
        self.combo_severity.setCursor(Qt.PointingHandCursor)
        self.combo_severity.currentIndexChanged.connect(self.refresh_data)
        filter_box.addWidget(self.combo_severity)

        # Module Filter
        lbl_mod = QLabel("Module:")
        lbl_mod.setStyleSheet("color: #8b949e; font-weight: 500; font-size: 12px;")
        filter_box.addWidget(lbl_mod)
        self.combo_module = QComboBox()
        self.combo_module.addItems(["All", "CPU", "RAM", "Disk", "Network", "Process", "SystemLog", "Security", "FileSystem"])
        self.combo_module.setFixedHeight(32)
        self.combo_module.setCursor(Qt.PointingHandCursor)
        self.combo_module.currentIndexChanged.connect(self.refresh_data)
        filter_box.addWidget(self.combo_module)

        # Min Score Filter
        lbl_score = QLabel("Min Score:")
        lbl_score.setStyleSheet("color: #8b949e; font-weight: 500; font-size: 12px;")
        filter_box.addWidget(lbl_score)
        self.combo_min_score = QComboBox()
        self.combo_min_score.addItems(["0 (All)", "40 (Medium+)", "70 (High+)", "90 (Critical)"])
        self.combo_min_score.setFixedHeight(32)
        self.combo_min_score.setCursor(Qt.PointingHandCursor)
        self.combo_min_score.currentIndexChanged.connect(self.refresh_data)
        filter_box.addWidget(self.combo_min_score)

        # Search box
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍  Search incident justification or anomaly type...")
        self.txt_search.setFixedHeight(32)
        self.txt_search.textChanged.connect(self._apply_client_filter)
        filter_box.addWidget(self.txt_search, stretch=1)

        # Refresh button
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_data)
        filter_box.addWidget(self.btn_refresh)

        # Export CSV button
        self.btn_export_csv = QPushButton("📄 Export CSV")
        self.btn_export_csv.setFixedHeight(32)
        self.btn_export_csv.setCursor(Qt.PointingHandCursor)
        self.btn_export_csv.clicked.connect(self.export_csv)
        filter_box.addWidget(self.btn_export_csv)

        # Export PDF button
        self.btn_export_pdf = QPushButton("📑 Export PDF Report")
        self.btn_export_pdf.setFixedHeight(32)
        self.btn_export_pdf.setCursor(Qt.PointingHandCursor)
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        filter_box.addWidget(self.btn_export_pdf)

        f_layout.addLayout(filter_box)
        layout.addWidget(filter_card)

        # Results Table Card Container
        tbl_card = QFrame()
        tbl_card.setProperty("class", "card-panel")
        t_card_layout = QVBoxLayout(tbl_card)
        t_card_layout.setContentsMargins(14, 14, 14, 14)
        t_card_layout.setSpacing(10)

        lbl_t_title = QLabel("Audit Log Records")
        lbl_t_title.setStyleSheet("color: #7d8590; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;")
        t_card_layout.addWidget(lbl_t_title)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Timestamp", "Score", "Severity", "Module", "Anomaly Type", "Explanation Justification"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        t_card_layout.addWidget(self.table)

        self.lbl_status = QLabel("Total historical records: 0")
        self.lbl_status.setStyleSheet("color: #7d8590; font-size: 11px;")
        t_card_layout.addWidget(self.lbl_status)

        layout.addWidget(tbl_card, stretch=1)

    def refresh_data(self) -> None:
        """Fetch alerts from SQLite based on filter criteria."""
        sev = self.combo_severity.currentText()
        sev_filter = None if sev == "All" else sev

        mod = self.combo_module.currentText()
        mod_filter = None if mod == "All" else mod

        min_score_idx = self.combo_min_score.currentIndex()
        min_scores = [0.0, 40.0, 70.0, 90.0]
        min_score = min_scores[min_score_idx] if min_score_idx < len(min_scores) else 0.0

        try:
            alerts = self.storage.get_alerts(
                limit=50,
                min_score=min_score,
                severity=sev_filter,
                module=mod_filter
            )
            self._cached_alerts = alerts
            self._populate_table(alerts)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to retrieve history: {e}")

    def _apply_client_filter(self) -> None:
        """Search term filter over cached alerts."""
        query = self.txt_search.text().lower().strip()
        if not query:
            self._populate_table(self._cached_alerts)
            return

        filtered = [
            a for a in self._cached_alerts
            if query in a.get("justification", "").lower() or query in a.get("anomaly_type", "").lower()
        ]
        self._populate_table(filtered)

    def _populate_table(self, alerts: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(len(alerts))
        for row, a in enumerate(alerts):
            ts = a.get("timestamp", 0.0)
            dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

            item_id = QTableWidgetItem(str(a.get("id", row + 1)))
            item_id.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_id)

            item_ts = QTableWidgetItem(dt_str)
            item_ts.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, item_ts)

            item_score = QTableWidgetItem(f"{a.get('score', 0):.0f}")
            item_score.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, item_score)

            item_sev = QTableWidgetItem(a.get("severity", "Low"))
            item_sev.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, item_sev)

            self.table.setItem(row, 4, QTableWidgetItem(a.get("module", "")))
            self.table.setItem(row, 5, QTableWidgetItem(a.get("anomaly_type", "")))
            self.table.setItem(row, 6, QTableWidgetItem(a.get("justification", "")))

        self.lbl_status.setText(f"Showing {len(alerts)} records (out of {len(self._cached_alerts)} fetched).")

    def export_csv(self) -> None:
        """Export current filtered alerts to a CSV file."""
        if not self._cached_alerts:
            QMessageBox.information(self, "Info", "No alerts available to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Alerts CSV", f"lxad_alerts_{int(time.time())}.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "ID", "Timestamp", "DateTime", "Score", "Severity", "Module",
                    "Anomaly Type", "Detectors Fired", "Matched Rules", "Justification", "Remedial Actions"
                ])
                for a in self._cached_alerts:
                    dt_str = datetime.datetime.fromtimestamp(a.get("timestamp", 0)).strftime("%Y-%m-%d %H:%M:%S")
                    writer.writerow([
                        a.get("id", ""),
                        a.get("timestamp", 0),
                        dt_str,
                        a.get("score", 0),
                        a.get("severity", ""),
                        a.get("module", ""),
                        a.get("anomaly_type", ""),
                        ", ".join(a.get("detectors_fired", [])),
                        ", ".join(a.get("matched_rules", [])),
                        a.get("justification", ""),
                        " | ".join(a.get("remedial_actions", []))
                    ])
            QMessageBox.information(self, "Success", f"Alerts successfully exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to save CSV file:\n{e}")

    def export_pdf(self) -> None:
        """Export executive summary PDF report using ReportLab."""
        if not self._cached_alerts:
            QMessageBox.information(self, "Info", "No alerts available to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF Report", f"lxad_audit_report_{int(time.time())}.pdf", "PDF Files (*.pdf)"
        )
        if not file_path:
            return

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

            doc = SimpleDocTemplate(file_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            story = []
            styles = getSampleStyleSheet()

            # Title
            title_style = ParagraphStyle(
                "TitleStyle",
                parent=styles["Heading1"],
                fontSize=18,
                textColor=colors.HexColor("#1f6feb"),
                spaceAfter=12
            )
            story.append(Paragraph("LXAD: Anomaly Detection & Justification Audit Report", title_style))

            subtitle_style = ParagraphStyle("SubStyle", parent=styles["Normal"], fontSize=10, textColor=colors.gray, spaceAfter=18)
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            story.append(Paragraph(f"Generated: {now_str} | Total Incidents Recorded: {len(self._cached_alerts)}", subtitle_style))

            # Table Header
            table_data = [["Time", "Score", "Severity", "Module", "Anomaly Type", "Explanation"]]

            for a in self._cached_alerts[:50]:  # Cap at top 50 for clean PDF
                dt_str = datetime.datetime.fromtimestamp(a.get("timestamp", 0)).strftime("%H:%M:%S")
                table_data.append([
                    dt_str,
                    f"{a.get('score', 0):.0f}",
                    a.get("severity", ""),
                    a.get("module", ""),
                    a.get("anomaly_type", ""),
                    Paragraph(a.get("justification", "")[:200], styles["Normal"])
                ])

            t = Table(table_data, colWidths=[60, 45, 55, 65, 110, 205])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#21262d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
            ]))
            story.append(t)

            doc.build(story)
            QMessageBox.information(self, "Success", f"PDF Report generated successfully:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to generate PDF report:\n{e}")
