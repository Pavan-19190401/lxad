"""
Configuration and Rule Editor Settings View for LXAD.

Allows dynamic toggling of telemetry collectors and anomaly detection algorithms,
weight calibration between statistical and rule scores, and live YAML rule editing with syntax validation.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Optional

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QCheckBox, QDoubleSpinBox, QSpinBox, QGroupBox, QPushButton,
    QPlainTextEdit, QMessageBox, QTabWidget
)

from lxad.rules.engine import RuleEngine

logger = logging.getLogger(__name__)


class SettingsView(QWidget):
    """Configuration management and live rule definition editor."""

    def __init__(
        self,
        rule_engine: RuleEngine,
        on_settings_changed: Optional[Callable[[Dict[str, Any]], None]] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.rule_engine = rule_engine
        self.on_settings_changed = on_settings_changed
        self._init_ui()
        self.load_rule_file_to_editor()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        tabs = QTabWidget()

        # TAB 1: Collectors & Detectors
        tab_engine = QWidget()
        engine_layout = QVBoxLayout(tab_engine)

        # Collectors Group
        grp_collectors = QGroupBox("Active Telemetry Collectors (Read-Only PC Observation)")
        coll_layout = QGridLayout(grp_collectors)

        self.chk_metrics = QCheckBox("Hardware Metrics (CPU, RAM, Disk I/O, Net I/O, Battery, Temp)")
        self.chk_metrics.setChecked(True)
        self.chk_procs = QCheckBox("Process Activity (Lifecycles, Top Resource Consumers, Trees)")
        self.chk_procs.setChecked(True)
        self.chk_logs = QCheckBox("System Logs (Windows Event Logs: System, App, Security)")
        self.chk_logs.setChecked(True)
        self.chk_files = QCheckBox("Filesystem Activity (Watchdog on Temp and User Log Folders)")
        self.chk_files.setChecked(True)
        self.chk_net = QCheckBox("Network Connections (Active TCP/UDP sockets, Open Ports)")
        self.chk_net.setChecked(True)

        coll_layout.addWidget(self.chk_metrics, 0, 0)
        coll_layout.addWidget(self.chk_procs, 0, 1)
        coll_layout.addWidget(self.chk_logs, 1, 0)
        coll_layout.addWidget(self.chk_files, 1, 1)
        coll_layout.addWidget(self.chk_net, 2, 0)
        engine_layout.addWidget(grp_collectors)

        # Detectors Group
        grp_detectors = QGroupBox("Active Anomaly Detection Algorithms")
        det_layout = QGridLayout(grp_detectors)

        self.chk_zscore = QCheckBox("Z-Score Detector (Rolling Window, Threshold=3.0)")
        self.chk_zscore.setChecked(True)
        self.chk_ewma = QCheckBox("EWMA Control Chart (Alpha=0.3, L=3.0)")
        self.chk_ewma.setChecked(True)
        self.chk_iqr = QCheckBox("IQR Fence Detector (1.5x Multiplier)")
        self.chk_iqr.setChecked(True)
        self.chk_iforest = QCheckBox("Isolation Forest (Unsupervised Tree Ensemble, Periodic Retrain)")
        self.chk_iforest.setChecked(True)
        self.chk_lof = QCheckBox("Local Outlier Factor (LOF Novelty Detection Mode)")
        self.chk_lof.setChecked(True)

        det_layout.addWidget(self.chk_zscore, 0, 0)
        det_layout.addWidget(self.chk_ewma, 0, 1)
        det_layout.addWidget(self.chk_iqr, 1, 0)
        det_layout.addWidget(self.chk_iforest, 1, 1)
        det_layout.addWidget(self.chk_lof, 2, 0)
        engine_layout.addWidget(grp_detectors)

        # Scoring Weights & Sensitivity
        grp_scoring = QGroupBox("Scoring Formula & Alert Calibration")
        score_layout = QGridLayout(grp_scoring)

        score_layout.addWidget(QLabel("Statistical Weight (w_stat):"), 0, 0)
        self.spin_w_stat = QDoubleSpinBox()
        self.spin_w_stat.setRange(0.0, 1.0)
        self.spin_w_stat.setSingleStep(0.05)
        self.spin_w_stat.setValue(0.50)
        self.spin_w_stat.setFixedHeight(32)
        score_layout.addWidget(self.spin_w_stat, 0, 1)

        score_layout.addWidget(QLabel("Rule Weight (w_rule):"), 0, 2)
        self.spin_w_rule = QDoubleSpinBox()
        self.spin_w_rule.setRange(0.0, 1.0)
        self.spin_w_rule.setSingleStep(0.05)
        self.spin_w_rule.setValue(0.50)
        self.spin_w_rule.setFixedHeight(32)
        score_layout.addWidget(self.spin_w_rule, 0, 3)

        score_layout.addWidget(QLabel("Alert Threshold (0-100):"), 1, 0)
        self.spin_threshold = QSpinBox()
        self.spin_threshold.setRange(10, 95)
        self.spin_threshold.setValue(40)
        self.spin_threshold.setFixedHeight(32)
        score_layout.addWidget(self.spin_threshold, 1, 1)

        score_layout.addWidget(QLabel("Window Size (seconds):"), 1, 2)
        self.spin_window = QSpinBox()
        self.spin_window.setRange(2, 60)
        self.spin_window.setValue(10)
        self.spin_window.setFixedHeight(32)
        score_layout.addWidget(self.spin_window, 1, 3)

        score_layout.addWidget(QLabel("Alert Cooldown (seconds):"), 2, 0)
        self.spin_cooldown = QSpinBox()
        self.spin_cooldown.setRange(5, 300)
        self.spin_cooldown.setValue(30)
        self.spin_cooldown.setFixedHeight(32)
        score_layout.addWidget(self.spin_cooldown, 2, 1)

        score_layout.addWidget(QLabel("Data Retention (days):"), 2, 2)
        self.spin_retention = QSpinBox()
        self.spin_retention.setRange(1, 90)
        self.spin_retention.setValue(7)
        self.spin_retention.setFixedHeight(32)
        score_layout.addWidget(self.spin_retention, 2, 3)

        engine_layout.addWidget(grp_scoring)

        # Apply settings button
        btn_apply = QPushButton("💾 Save & Apply System Settings")
        btn_apply.clicked.connect(self._apply_settings)
        engine_layout.addWidget(btn_apply)
        engine_layout.addStretch()

        tabs.addTab(tab_engine, "⚙️ Detection & Engine Settings")

        # TAB 2: Live Rule Editor
        tab_rules = QWidget()
        rule_layout = QVBoxLayout(tab_rules)

        lbl_rule_info = QLabel("Declarative Rule Definition Editor (rules.yaml). Changes take effect immediately after saving.")
        lbl_rule_info.setStyleSheet("color: #8b949e; font-size: 12px;")
        rule_layout.addWidget(lbl_rule_info)

        self.txt_rules = QPlainTextEdit()
        self.txt_rules.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        rule_layout.addWidget(self.txt_rules)

        btn_row = QHBoxLayout()
        self.btn_save_rules = QPushButton("💾 Save & Reload Rules")
        self.btn_save_rules.clicked.connect(self._save_rules)
        btn_row.addWidget(self.btn_save_rules)

        self.btn_reload_rules = QPushButton("🔄 Revert to Disk")
        self.btn_reload_rules.setProperty("class", "secondary")
        self.btn_reload_rules.clicked.connect(self.load_rule_file_to_editor)
        btn_row.addWidget(self.btn_reload_rules)

        rule_layout.addLayout(btn_row)
        tabs.addTab(tab_rules, "📝 Rule Definition Editor (YAML)")

        main_layout.addWidget(tabs)

    def load_rule_file_to_editor(self) -> None:
        """Load YAML file content into the text editor."""
        if os.path.exists(self.rule_engine.rules_file):
            try:
                with open(self.rule_engine.rules_file, "r", encoding="utf-8") as f:
                    content = f.read()
                self.txt_rules.setPlainText(content)
            except Exception as e:
                self.txt_rules.setPlainText(f"# Error reading rules: {e}")

    def _save_rules(self) -> None:
        """Validate and write YAML rules."""
        content = self.txt_rules.toPlainText()
        try:
            parsed = yaml.safe_load(content)
            if not isinstance(parsed, dict) or "rules" not in parsed:
                raise ValueError("Root element must be a dictionary with a 'rules' list.")
            success = self.rule_engine.save_rules(content)
            if success:
                QMessageBox.information(self, "Success", f"Rules saved and reloaded! ({len(parsed['rules'])} rules active)")
            else:
                QMessageBox.critical(self, "Error", "Failed to write rules to file.")
        except Exception as e:
            QMessageBox.critical(self, "YAML Syntax Error", f"Failed to parse YAML:\n{e}")

    def _apply_settings(self) -> None:
        """Collect current settings and notify parent listener."""
        settings = {
            "collectors": {
                "metrics": self.chk_metrics.isChecked(),
                "processes": self.chk_procs.isChecked(),
                "eventlogs": self.chk_logs.isChecked(),
                "filewatch": self.chk_files.isChecked(),
                "network": self.chk_net.isChecked(),
            },
            "detectors": {
                "zscore": self.chk_zscore.isChecked(),
                "ewma": self.chk_ewma.isChecked(),
                "iqr": self.chk_iqr.isChecked(),
                "iforest": self.chk_iforest.isChecked(),
                "lof": self.chk_lof.isChecked(),
            },
            "w_stat": self.spin_w_stat.value(),
            "w_rule": self.spin_w_rule.value(),
            "alert_threshold": self.spin_threshold.value(),
            "window_size": self.spin_window.value(),
            "cooldown": self.spin_cooldown.value(),
            "retention": self.spin_retention.value()
        }
        if self.on_settings_changed:
            self.on_settings_changed(settings)
        QMessageBox.information(self, "Settings Applied", "Engine configuration successfully updated.")
