"""
Main Application Window for LXAD.

Clean, uncluttered, minimalist interface inspired by Linear / Datadog:
- Minimalist header with title, breadcrumb, and full-PC access badge
- Clean underline tabs with live alert counter
- Zero visual noise: no dummy icons, no cluttered avatar circles
- Responsive stacked views with real-time host PC telemetry
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QSystemTrayIcon, QMenu,
    QFrame
)

from lxad.core.ingestion import EventQueue, TelemetryEvent
from lxad.core.storage import RingBuffer, SQLiteStorage
from lxad.core.preprocessing import PreprocessingPipeline, WindowFeatures
from lxad.collectors.metrics import MetricsCollector
from lxad.collectors.processes import ProcessCollector
from lxad.collectors.eventlogs import EventLogCollector
from lxad.collectors.filewatch import FileWatchCollector
from lxad.collectors.network import NetworkCollector
from lxad.detectors.ensemble import EnsembleDetector
from lxad.rules.engine import RuleEngine
from lxad.scoring.scorer import AlertScorer, AlertScoreResult
from lxad.explain.justification import JustificationGenerator

from lxad.ui.styles import JET_BLACK_THEME_QSS
from lxad.ui.dashboard import DashboardView
from lxad.ui.alerts_view import AlertsView
from lxad.ui.history_view import HistoryView
from lxad.ui.settings_view import SettingsView
from lxad.ui.permissions_dialog import PermissionsDialog, is_admin, relaunch_as_admin

logger = logging.getLogger(__name__)


class PipelineWorker(QThread):
    """Real-time pipeline orchestrator running in a background thread."""
    sig_metrics_updated = Signal(dict)
    sig_score_updated = Signal(float, str)
    sig_alert_generated = Signal(dict)

    def __init__(
        self,
        event_queue: EventQueue,
        ring_buffer: RingBuffer,
        storage: SQLiteStorage,
        rule_engine: RuleEngine
    ):
        super().__init__()
        self.queue = event_queue
        self.buffer = ring_buffer
        self.storage = storage
        self.rule_engine = rule_engine

        self.preprocessing = PreprocessingPipeline(window_size_seconds=10.0)
        self.ensemble = EnsembleDetector()
        self.scorer = AlertScorer(w_stat=0.5, w_rule=0.5, alert_threshold=40.0, cooldown_seconds=30.0)
        self.justification_gen = JustificationGenerator()

        # Collectors
        self.metrics_collector = MetricsCollector(self.queue, interval=1.0)
        self.process_collector = ProcessCollector(self.queue, interval=2.0)
        self.eventlog_collector = EventLogCollector(self.queue, interval=3.0)
        self.filewatch_collector = FileWatchCollector(self.queue)
        self.network_collector = NetworkCollector(self.queue, interval=3.0)

        self._running = False
        self._last_eval_time = 0.0
        self._eval_interval = 2.0

        self._cpu_baseline = 25.0
        self._ram_baseline = 50.0

    def start_collectors(self) -> None:
        self.metrics_collector.start()
        self.process_collector.start()
        self.eventlog_collector.start()
        self.filewatch_collector.start()
        self.network_collector.start()

    def stop_collectors(self) -> None:
        self.metrics_collector.stop()
        self.process_collector.stop()
        self.eventlog_collector.stop()
        self.filewatch_collector.stop()
        self.network_collector.stop()

    def run(self) -> None:
        self._running = True
        self.start_collectors()

        while self._running:
            batch = self.queue.drain_batch(max_items=100)
            if batch:
                self.buffer.extend(batch)

            now = time.time()
            if now - self._last_eval_time >= self._eval_interval:
                self._last_eval_time = now
                self._evaluate_cycle(now)

            time.sleep(0.2)

        self.stop_collectors()

    def _evaluate_cycle(self, now: float) -> None:
        recent_events = self.buffer.get_recent(seconds=10.0)
        wf = self.preprocessing.process_window(recent_events, start_ts=now - 10.0, end_ts=now)

        cpu_val = wf.get_metric("cpu_percent", "mean", 0.0)
        ram_val = wf.get_metric("memory_percent", "mean", 0.0)
        swap_val = wf.get_metric("swap_percent", "mean", 0.0)
        disk_w_mb = wf.get_metric("disk_write_bytes_sec", "mean", 0.0) / (1024 * 1024)
        net_s_mb = wf.get_metric("net_sent_bytes_sec", "mean", 0.0) / (1024 * 1024)

        self._cpu_baseline = 0.95 * self._cpu_baseline + 0.05 * max(5.0, cpu_val)
        self._ram_baseline = 0.95 * self._ram_baseline + 0.05 * max(10.0, ram_val)

        vector = wf.to_vector()

        ens_res = self.ensemble.evaluate(
            primary_metric_val=cpu_val,
            feature_vector=vector,
            add_to_history=True
        )

        baselines = {"cpu_percent": self._cpu_baseline, "memory_percent": self._ram_baseline}
        rule_matches = self.rule_engine.evaluate(wf, baseline_metrics=baselines)

        alert_res = self.scorer.score(ens_res, rule_matches, default_module="CPU")

        if alert_res.is_alert:
            exp_detail = self.justification_gen.generate(
                alert_res=alert_res,
                ensemble_res=ens_res,
                primary_metric_name="cpu_percent" if alert_res.module == "CPU" else alert_res.module.lower(),
                current_metric_val=cpu_val if alert_res.module == "CPU" else 1.0,
                baseline_metric_val=self._cpu_baseline
            )

            alert_id = self.storage.save_alert(
                score=alert_res.score,
                severity=alert_res.severity,
                module=alert_res.module,
                anomaly_type=alert_res.anomaly_type,
                justification=exp_detail.full_text,
                detectors_fired=alert_res.detectors_fired,
                matched_rules=alert_res.matched_rules,
                metrics={"cpu": cpu_val, "ram": ram_val, "disk_w_mb": disk_w_mb},
                remedial_actions=alert_res.remedial_actions,
                timestamp=now
            )

            alert_dict = {
                "id": alert_id,
                "timestamp": now,
                "score": alert_res.score,
                "severity": alert_res.severity,
                "module": alert_res.module,
                "anomaly_type": alert_res.anomaly_type,
                "justification": exp_detail.full_text,
                "detectors_fired": alert_res.detectors_fired,
                "matched_rules": alert_res.matched_rules,
                "remedial_actions": alert_res.remedial_actions
            }
            self.sig_alert_generated.emit(alert_dict)

        metrics_dict = {
            "cpu": cpu_val,
            "ram": ram_val,
            "swap": swap_val,
            "disk_w_mb": disk_w_mb,
            "net_s_mb": net_s_mb,
            "top_procs": wf.top_processes,
            "is_anomaly": ens_res.is_anomaly or bool(rule_matches)
        }
        self.sig_metrics_updated.emit(metrics_dict)
        self.sig_score_updated.emit(alert_res.score, alert_res.severity)

    def stop(self) -> None:
        self._running = False
        self.wait(2000)

    # Injections
    def inject_cpu_spike(self) -> None:
        now = time.time()
        for i in range(8):
            self.queue.push(TelemetryEvent(
                timestamp=now - (7 - i),
                source="metrics",
                module="CPU",
                type="metric",
                metric_name="cpu_percent",
                value=96.5,
                severity_level="WARNING"
            ))
        self.queue.push(TelemetryEvent(
            timestamp=now,
            source="processes",
            module="Process",
            type="process_top",
            metric_name="top_process_cpu",
            value=89.0,
            details={"top_cpu": [{"pid": 8844, "name": "stress_calc.exe", "cpu": 89.2, "mem": 14.5, "exe": "C:\\Program Files\\stress_calc.exe"}]}
        ))

    def inject_memory_spike(self) -> None:
        now = time.time()
        for i in range(6):
            self.queue.push(TelemetryEvent(
                timestamp=now - (5 - i),
                source="metrics",
                module="RAM",
                type="metric",
                metric_name="memory_percent",
                value=93.0
            ))
            self.queue.push(TelemetryEvent(
                timestamp=now - (5 - i),
                source="metrics",
                module="RAM",
                type="metric",
                metric_name="swap_percent",
                value=68.0
            ))

    def inject_error_storm(self) -> None:
        now = time.time()
        for i in range(10):
            self.queue.push(TelemetryEvent(
                timestamp=now - (10 - i) * 0.5,
                source="eventlogs",
                module="SystemLog",
                type="log_event",
                metric_name="error_count",
                value=1.0,
                severity_level="ERROR",
                raw_text=f"CRITICAL: Kernel driver watchdog timeout on subsystem channel {i+1}"
            ))

    def inject_ransomware_spike(self) -> None:
        now = time.time()
        for i in range(25):
            self.queue.push(TelemetryEvent(
                timestamp=now - (25 - i) * 0.1,
                source="filewatch",
                module="FileSystem",
                type="file_event",
                metric_name="file_activity_count",
                value=1.0,
                raw_text=f"file_modified: C:\\Users\\Public\\Documents\\financial_{i}.docx.locked"
            ))
        self.queue.push(TelemetryEvent(
            timestamp=now,
            source="metrics",
            module="Disk",
            type="metric",
            metric_name="disk_write_bytes_sec",
            value=35.0 * 1024 * 1024
        ))

    def update_settings(self, cfg: Dict[str, Any]) -> None:
        if "w_stat" in cfg:
            self.scorer.w_stat = float(cfg["w_stat"])
        if "w_rule" in cfg:
            self.scorer.w_rule = float(cfg["w_rule"])
        if "alert_threshold" in cfg:
            self.scorer.alert_threshold = float(cfg["alert_threshold"])
        if "cooldown" in cfg:
            self.scorer.cooldown_seconds = float(cfg["cooldown"])
        if "window_size" in cfg:
            self.preprocessing.window_size_seconds = float(cfg["window_size"])
        for name, enabled in cfg.get("detectors", {}).items():
            self.ensemble.set_enabled(name, enabled)


class MainWindow(QMainWindow):
    """Clean, uncluttered Desktop Application Window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LXAD - Anomaly Detection Framework")
        self.resize(1200, 780)
        self.setStyleSheet(JET_BLACK_THEME_QSS)

        # Core subsystems
        self.queue = EventQueue(maxsize=5000)
        self.buffer = RingBuffer(capacity=5000, max_age_seconds=900.0)
        self.storage = SQLiteStorage(db_path="data/lxad_storage.db")
        self.rule_engine = RuleEngine()

        self.worker = PipelineWorker(self.queue, self.buffer, self.storage, self.rule_engine)

        self._alert_count = 0
        self._init_ui()
        self._init_tray()
        self._wire_signals()

        self.worker.start()

    def _init_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralWidget")
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==========================================
        # CLEAN MINIMALIST HEADER & NAV BAR
        # ==========================================
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #08090a; padding: 16px 24px 0px 24px;")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        # Top line: Title + Access Badge
        top_line = QHBoxLayout()
        top_line.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        lbl_title = QLabel("System Health")
        lbl_title.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: 700; letter-spacing: -0.5px;")
        title_box.addWidget(lbl_title)

        lbl_breadcrumb = QLabel("CMRIT  ›  CSE AI&ML  ›  Real-Time Observability")
        lbl_breadcrumb.setStyleSheet("color: #7d8590; font-size: 12px; font-weight: 500;")
        title_box.addWidget(lbl_breadcrumb)

        top_line.addLayout(title_box)
        top_line.addStretch()

        # Administrator Full-PC Access Badge (Blender Chiseled Workstation Aesthetic)
        if is_admin():
            lbl_access = QLabel()
            lbl_access.setTextFormat(Qt.RichText)
            lbl_access.setText(
                '<span style="color: #4cd97b; font-size: 11px;">●</span> '
                '<span style="color: #e2e8f0; font-weight: 700; font-size: 11px; letter-spacing: 0.6px;">ROOT ACCESS</span> '
                '<span style="color: #636b76; font-size: 11px; margin-left: 4px;">| PRIVILEGED</span>'
            )
            lbl_access.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a2d33, stop:1 #1c1e22);
                border: 1px solid #3c414a;
                border-top: 1px solid #4f5662;
                border-bottom: 1px solid #141618;
                border-radius: 4px;
                padding: 4px 12px;
            """)
            top_line.addWidget(lbl_access)
        else:
            btn_elevate = QPushButton()
            btn_elevate.setText("⚡ Elevate to Root")
            btn_elevate.setToolTip("Request Administrator Privileges (Windows UAC) for Full PC Visibility")
            btn_elevate.setCursor(Qt.PointingHandCursor)
            btn_elevate.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #343840, stop:1 #24272c);
                    border: 1px solid #454c56;
                    border-top: 1px solid #5a626f;
                    border-bottom: 1px solid #17191c;
                    border-radius: 4px;
                    padding: 5px 14px;
                    color: #f0f3f6;
                    font-size: 11px;
                    font-weight: 600;
                    letter-spacing: 0.4px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #424752, stop:1 #2e3239);
                    border-color: #646c7b;
                    border-top-color: #7b8596;
                    color: #ffffff;
                }
                QPushButton:pressed {
                    background: #191b1e;
                    border-color: #383e47;
                    border-top-color: #191b1e;
                    color: #8b949e;
                }
            """)
            btn_elevate.clicked.connect(relaunch_as_admin)
            top_line.addWidget(btn_elevate)

        header_layout.addLayout(top_line)

        # Tab Navigation Row: Clean, uncluttered text tabs
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 10, 0, 0)
        nav_row.setSpacing(4)

        self._nav_buttons: List[QPushButton] = []

        def create_tab_btn(title: str, idx: int) -> QPushButton:
            btn = QPushButton(title)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda: self._select_tab(idx))
            self._nav_buttons.append(btn)
            nav_row.addWidget(btn)
            return btn

        self.btn_tab_dashboard = create_tab_btn("Dashboard", 0)
        self.btn_tab_alerts = create_tab_btn("Alerts  0", 1)
        self.btn_tab_history = create_tab_btn("History", 2)
        self.btn_tab_benchmark = create_tab_btn("Benchmark", 3)
        self.btn_tab_settings = create_tab_btn("Settings", 4)

        nav_row.addStretch()

        # Clean Test Anomaly Dropdown / Button (Blender Header Style)
        self.btn_test_menu = QPushButton("⚡ Simulate Anomaly ▾")
        self.btn_test_menu.setCursor(Qt.PointingHandCursor)
        self.btn_test_menu.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b2e35, stop:1 #1e2025);
                color: #e6edf3;
                border: 1px solid #3c414b;
                border-top: 1px solid #4a505c;
                border-bottom: 1px solid #16181b;
                border-radius: 5px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #363a43, stop:1 #272a31);
                border-color: #555d6b;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #17191c;
                border-color: #2e3239;
                color: #8b949e;
            }
        """)

        menu_sim = QMenu(self)
        menu_sim.setStyleSheet("""
            QMenu {
                background-color: #14171d;
                border: 1px solid #2e3440;
                border-radius: 8px;
                padding: 6px;
                color: #f0f3f6;
                font-size: 12px;
            }
            QMenu::item {
                padding: 7px 24px 7px 12px;
                border-radius: 5px;
                margin: 1px 0px;
            }
            QMenu::item:selected {
                background-color: #242b38;
                color: #ffffff;
            }
        """)

        act_cpu = QAction("⚡ Runaway CPU Spike (95%)", self)
        act_cpu.triggered.connect(self.worker.inject_cpu_spike)
        menu_sim.addAction(act_cpu)

        act_mem = QAction("💧 Memory Leak & Swap (92%)", self)
        act_mem.triggered.connect(self.worker.inject_memory_spike)
        menu_sim.addAction(act_mem)

        act_err = QAction("⛈️ Kernel Error Storm Burst", self)
        act_err.triggered.connect(self.worker.inject_error_storm)
        menu_sim.addAction(act_err)

        act_ransom = QAction("🔒 Ransomware Disk Pattern", self)
        act_ransom.triggered.connect(self.worker.inject_ransomware_spike)
        menu_sim.addAction(act_ransom)

        self.btn_test_menu.setMenu(menu_sim)
        nav_row.addWidget(self.btn_test_menu)

        header_layout.addLayout(nav_row)

        # 1px border line under nav bar
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); min-height: 1px; max-height: 1px; border: none;")
        header_layout.addWidget(divider)

        main_layout.addWidget(header_widget)

        # ==========================================
        # STACKED VIEWS CONTENT
        # ==========================================
        self.stack = QStackedWidget()

        self.view_dashboard = DashboardView()
        self.view_alerts = AlertsView()
        self.view_history = HistoryView(storage=self.storage)
        self.view_settings = SettingsView(
            rule_engine=self.rule_engine,
            on_settings_changed=self.worker.update_settings
        )
        self._view_benchmark: Optional[QWidget] = None
        self._benchmark_tab_placeholder = QWidget()

        self.stack.addWidget(self.view_dashboard)       # 0
        self.stack.addWidget(self.view_alerts)          # 1
        self.stack.addWidget(self.view_history)         # 2
        self.stack.addWidget(self._benchmark_tab_placeholder) # 3
        self.stack.addWidget(self.view_settings)        # 4

        main_layout.addWidget(self.stack)
        self.setCentralWidget(central)

        self._select_tab(0)

    def _select_tab(self, index: int) -> None:
        """Switch views and update clean underline indicator."""
        if index == 3 and self._view_benchmark is None:
            from lxad.ui.benchmark_view import BenchmarkView
            self._view_benchmark = BenchmarkView()
            layout = QVBoxLayout(self._benchmark_tab_placeholder)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._view_benchmark)

        self.stack.setCurrentIndex(index)

        for i, btn in enumerate(self._nav_buttons):
            if i == index:
                btn.setChecked(True)
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #ffffff;
                        font-weight: 600;
                        font-size: 13px;
                        border: none;
                        border-bottom: 2px solid #ffffff;
                        padding: 8px 16px 10px 16px;
                        border-radius: 0px;
                    }
                """)
            else:
                btn.setChecked(False)
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #7d8590;
                        font-weight: 500;
                        font-size: 13px;
                        border: none;
                        border-bottom: 2px solid transparent;
                        padding: 8px 16px 10px 16px;
                        border-radius: 0px;
                    }
                    QPushButton:hover {
                        color: #c9d1d9;
                    }
                """)

    def _init_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.setWindowIcon(icon)

        menu = QMenu(self)
        action_show = QAction("Open System Health", self)
        action_show.triggered.connect(self.showNormal)
        menu.addAction(action_show)

        action_exit = QAction("Exit LXAD", self)
        action_exit.triggered.connect(self.close)
        menu.addAction(action_exit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _wire_signals(self) -> None:
        self.worker.sig_metrics_updated.connect(self._on_metrics_updated)
        self.worker.sig_score_updated.connect(self._on_score_updated)
        self.worker.sig_alert_generated.connect(self._on_alert_generated)

    def _on_metrics_updated(self, m: Dict[str, Any]) -> None:
        self.view_dashboard.update_metrics(
            cpu_val=m.get("cpu", 0.0),
            ram_val=m.get("ram", 0.0),
            swap_val=m.get("swap", 0.0),
            disk_write_mb=m.get("disk_w_mb", 0.0),
            net_sent_mb=m.get("net_s_mb", 0.0),
            top_procs=m.get("top_procs", []),
            anomaly_detected=m.get("is_anomaly", False)
        )

    def _on_score_updated(self, score: float, severity: str) -> None:
        self.view_dashboard.set_score(score, severity)

    def _on_alert_generated(self, alert_dict: Dict[str, Any]) -> None:
        self._alert_count += 1
        self.btn_tab_alerts.setText(f"Alerts  {self._alert_count}")

        self.view_alerts.add_alert(alert_dict)

        score = alert_dict.get("score", 0.0)
        sev = alert_dict.get("severity", "Medium")
        atype = alert_dict.get("anomaly_type", "Anomaly")
        msg = f"Score {score:.0f} [{sev.upper()}]: {atype}"

        if self.tray and self.tray.isVisible():
            self.tray.showMessage(
                "LXAD Anomaly Alert",
                msg,
                QSystemTrayIcon.MessageIcon.Warning,
                4000
            )

    def closeEvent(self, event) -> None:
        self.worker.stop()
        self.storage.close()
        event.accept()
