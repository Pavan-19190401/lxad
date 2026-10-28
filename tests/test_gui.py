"""
Tests for PySide6 GUI Components (Phase 4).
Runs offscreen to verify UI widget creation and signal handling.
"""

import os
import pytest

# Configure Qt for headless offscreen testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from lxad.core.storage import SQLiteStorage
from lxad.rules.engine import RuleEngine
from lxad.ui.dashboard import DashboardView, MetricSparklineCard, DetailedTrendCard
from lxad.ui.alerts_view import AlertsView
from lxad.ui.history_view import HistoryView
from lxad.ui.settings_view import SettingsView
from lxad.ui.benchmark_view import BenchmarkView
from lxad.ui.permissions_dialog import PermissionsDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_sparkline_card(qapp):
    card = MetricSparklineCard(key="cpu", title="CPU saturation", unit="%")
    card.update_value(65.5, is_anomaly=False)
    assert "65.5" in card.lbl_value.text()
    assert len(card._history) == 1

    card.update_value(92.0, is_anomaly=True)
    assert "92.0" in card.lbl_value.text()


def test_detailed_trend_card(qapp):
    card = DetailedTrendCard()
    card.update_data(75.0, is_anomaly=True, severity="High")
    assert "75 Score" in card.lbl_big_stat.text()
    assert "High" in card.lbl_status_val.text()


def test_dashboard_view(qapp):
    view = DashboardView()
    view.update_metrics(
        cpu_val=45.0,
        ram_val=60.0,
        swap_val=10.0,
        disk_write_mb=2.5,
        net_sent_mb=1.2,
        top_procs=[{"pid": 1234, "name": "test.exe", "cpu": 25.0, "mem": 12.0}],
        anomaly_detected=False
    )
    assert len(view.card_cpu._history) == 1
    assert "45.0" in view.card_cpu.lbl_value.text()
    assert len(view.card_mem._history) == 1


def test_alerts_view(qapp):
    view = AlertsView()
    sample_alert = {
        "timestamp": 1700000000.0,
        "score": 88.0,
        "severity": "High",
        "module": "CPU",
        "anomaly_type": "Runaway process",
        "justification": "CPU spiked to 98% due to bad.exe",
        "detectors_fired": ["Z-Score", "EWMA"],
        "matched_rules": ["R-001"],
        "remedial_actions": ["Kill bad.exe", "Inspect task manager"]
    }
    view.add_alert(sample_alert)
    assert view.table.rowCount() == 1
    assert "Runaway process" in view.lbl_headline.text()

    view.clear_alerts()
    assert view.table.rowCount() == 0


def test_history_view(qapp, tmp_path):
    db_path = str(tmp_path / "test_hist.db")
    storage = SQLiteStorage(db_path=db_path)
    storage.save_alert(
        score=75.0,
        severity="High",
        module="RAM",
        anomaly_type="Memory pressure",
        justification="RAM at 92%",
        detectors_fired=["IQR"],
        matched_rules=["R-002"],
        metrics={},
        remedial_actions=["Close apps"]
    )

    view = HistoryView(storage=storage)
    assert view.table.rowCount() == 1
    storage.close()


def test_settings_view(qapp):
    engine = RuleEngine()
    view = SettingsView(rule_engine=engine)
    assert view.spin_w_stat.value() == 0.50
    assert view.chk_zscore.isChecked()
    assert len(view.txt_rules.toPlainText()) > 50


def test_benchmark_view(qapp):
    view = BenchmarkView()
    assert view.radio_bundled.isChecked()
    assert view.table.rowCount() == 0


def test_main_window_nav_bar(qapp):
    from lxad.ui.main_window import MainWindow
    win = MainWindow()
    assert len(win._nav_buttons) == 5
    assert win.btn_tab_dashboard.isChecked()

    # Test tab switching
    win._select_tab(1)
    assert win.stack.currentIndex() == 1
    assert win.btn_tab_alerts.isChecked()

    win.worker.stop()
    win.storage.close()
    win.close()
