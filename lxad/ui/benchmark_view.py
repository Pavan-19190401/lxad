"""
LogHub HDFS Benchmark Evaluation View for LXAD.

Allows running comparative validation of anomaly detectors on HDFS block datasets,
visualizing Precision, Recall, F1, ROC-AUC, and latency metrics with CSV export.
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QGroupBox, QPushButton, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QRadioButton, QButtonGroup,
    QProgressBar
)

from lxad.benchmark.loghub_hdfs import generate_synthetic_hdfs, load_hdfs_dataset, HDFSBenchmarkData
from lxad.benchmark.evaluate import BenchmarkEvaluator, BenchmarkReport


class _BenchmarkWorker(QThread):
    """Background worker executing benchmark evaluation off the UI thread."""
    sig_finished = Signal(object)
    sig_error = Signal(str)

    def __init__(self, log_path: str, label_path: Optional[str]):
        super().__init__()
        self.log_path = log_path
        self.label_path = label_path

    def run(self) -> None:
        try:
            dataset = load_hdfs_dataset(self.log_path, self.label_path)
            evaluator = BenchmarkEvaluator()
            report = evaluator.run_benchmark(dataset)
            self.sig_finished.emit(report)
        except Exception as e:
            self.sig_error.emit(str(e))


class BenchmarkView(QWidget):
    """GUI interface for dataset benchmarking and comparative metrics."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_report: Optional[BenchmarkReport] = None
        self._worker: Optional[_BenchmarkWorker] = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Header info
        lbl_info = QLabel("📊 Project Evaluation Benchmark: LogHub HDFS Dataset Validation")
        lbl_info.setStyleSheet("font-size: 15px; font-weight: bold; color: #58a6ff;")
        layout.addWidget(lbl_info)

        # Dataset Selection Box
        grp_data = QGroupBox("Select Evaluation Dataset")
        d_layout = QVBoxLayout(grp_data)

        self.btn_group = QButtonGroup(self)
        self.radio_bundled = QRadioButton("Bundled Synthetic HDFS Dataset (Instant Offline Validation)")
        self.radio_bundled.setChecked(True)
        self.radio_custom = QRadioButton("Custom Local HDFS Log & Label File (User-Selected)")
        self.btn_group.addButton(self.radio_bundled)
        self.btn_group.addButton(self.radio_custom)

        d_layout.addWidget(self.radio_bundled)
        d_layout.addWidget(self.radio_custom)

        custom_row = QHBoxLayout()
        self.lbl_selected_path = QLabel("Using default offline synthetic sample (data/synthetic_hdfs.log)")
        self.lbl_selected_path.setStyleSheet("color: #8b949e; font-size: 11px;")
        custom_row.addWidget(self.lbl_selected_path, stretch=1)

        self.btn_browse = QPushButton("📁 Browse Log File...")
        self.btn_browse.setProperty("class", "secondary")
        self.btn_browse.setEnabled(False)
        self.btn_browse.clicked.connect(self._browse_custom_log)
        custom_row.addWidget(self.btn_browse)

        self.radio_custom.toggled.connect(lambda checked: self.btn_browse.setEnabled(checked))
        d_layout.addLayout(custom_row)

        # Action Buttons
        btn_box = QHBoxLayout()
        self.btn_run = QPushButton("🚀 Run Benchmark Evaluation")
        self.btn_run.setProperty("class", "inject")
        self.btn_run.clicked.connect(self._run_benchmark)
        btn_box.addWidget(self.btn_run)

        self.btn_export_csv = QPushButton("📄 Export Benchmark Results (CSV)")
        self.btn_export_csv.setProperty("class", "secondary")
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_csv.setEnabled(False)
        btn_box.addWidget(self.btn_export_csv)
        btn_box.addStretch()

        d_layout.addLayout(btn_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        d_layout.addWidget(self.progress_bar)

        layout.addWidget(grp_data)

        # Performance Summary Cards
        summary_group = QGroupBox("Ensemble Framework Highlights")
        s_layout = QGridLayout(summary_group)
        s_layout.setSpacing(12)

        self.card_f1 = self._create_card("F1-Score", "--")
        self.card_prec = self._create_card("Precision", "--")
        self.card_rec = self._create_card("Recall", "--")
        self.card_auc = self._create_card("ROC-AUC", "--")
        self.card_lat = self._create_card("Avg Latency", "-- ms")
        self.card_cpu = self._create_card("CPU Overhead", "-- %")

        s_layout.addWidget(self.card_f1, 0, 0)
        s_layout.addWidget(self.card_prec, 0, 1)
        s_layout.addWidget(self.card_rec, 0, 2)
        s_layout.addWidget(self.card_auc, 0, 3)
        s_layout.addWidget(self.card_lat, 0, 4)
        s_layout.addWidget(self.card_cpu, 0, 5)

        layout.addWidget(summary_group)

        # Comparison Table
        grp_table = QGroupBox("Model Comparison Matrix (Individual Detectors vs. LXAD Ensemble)")
        t_layout = QVBoxLayout(grp_table)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "Detector Algorithm", "Accuracy", "Precision", "Recall", "F1-Score",
            "ROC-AUC", "Latency (ms)", "TP", "FP", "TN", "FN"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        t_layout.addWidget(self.table)
        layout.addWidget(grp_table, stretch=1)

    def _create_card(self, title: str, initial_val: str) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 6px;")
        lyt = QVBoxLayout(box)
        lyt.setContentsMargins(6, 6, 6, 6)
        lyt.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: bold;")
        lbl_v = QLabel(initial_val)
        lbl_v.setObjectName("val_label")
        lbl_v.setStyleSheet("color: #58a6ff; font-size: 18px; font-weight: bold;")

        lyt.addWidget(lbl_t, alignment=Qt.AlignCenter)
        lyt.addWidget(lbl_v, alignment=Qt.AlignCenter)
        return box

    def _set_card_val(self, card_widget: QWidget, val_text: str, color_hex: str = "#58a6ff") -> None:
        lbl = card_widget.findChild(QLabel, "val_label")
        if lbl:
            lbl.setText(val_text)
            lbl.setStyleSheet(f"color: {color_hex}; font-size: 18px; font-weight: bold;")

    def _browse_custom_log(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select HDFS Log File", "", "Log Files (*.log *.txt);;All Files (*)")
        if path:
            self._custom_log_path = path
            self.lbl_selected_path.setText(f"Custom log: {path}")

    def _run_benchmark(self) -> None:
        if self.radio_bundled.isChecked():
            # Generate or reuse bundled dataset
            log_p, label_p = generate_synthetic_hdfs()
        else:
            log_p = getattr(self, "_custom_log_path", None)
            if not log_p or not os.path.exists(log_p):
                QMessageBox.warning(self, "Missing File", "Please select a valid HDFS log file.")
                return
            label_p = None

        self.btn_run.setEnabled(False)
        self.progress_bar.setVisible(True)

        self._worker = _BenchmarkWorker(log_p, label_p)
        self._worker.sig_finished.connect(self._on_benchmark_success)
        self._worker.sig_error.connect(self._on_benchmark_error)
        self._worker.start()

    def _on_benchmark_success(self, report: BenchmarkReport) -> None:
        self.btn_run.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.btn_export_csv.setEnabled(True)
        self._current_report = report

        # Populate table
        self.table.setRowCount(len(report.detector_results))
        for row, m in enumerate(report.detector_results):
            is_ensemble = "Ensemble" in m.name

            item_name = QTableWidgetItem(m.name)
            if is_ensemble:
                item_name.setForeground(Qt.cyan)

            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, QTableWidgetItem(f"{m.accuracy:.4f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{m.precision:.4f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{m.recall:.4f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{m.f1_score:.4f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{m.roc_auc:.4f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{m.latency_ms:.2f} ms"))
            self.table.setItem(row, 7, QTableWidgetItem(str(m.tp)))
            self.table.setItem(row, 8, QTableWidgetItem(str(m.fp)))
            self.table.setItem(row, 9, QTableWidgetItem(str(m.tn)))
            self.table.setItem(row, 10, QTableWidgetItem(str(m.fn)))

            # If ensemble, update summary cards
            if is_ensemble:
                self._set_card_val(self.card_f1, f"{m.f1_score:.3f}", "#3fb950")
                self._set_card_val(self.card_prec, f"{m.precision:.3f}")
                self._set_card_val(self.card_rec, f"{m.recall:.3f}")
                self._set_card_val(self.card_auc, f"{m.roc_auc:.3f}")
                self._set_card_val(self.card_lat, f"{m.latency_ms:.1f} ms")
                self._set_card_val(self.card_cpu, f"{report.cpu_overhead_percent:.1f}%")

        QMessageBox.information(
            self, "Benchmark Complete",
            f"Successfully evaluated {report.total_blocks} blocks ({report.anomaly_count} anomalies) across {len(report.detector_results)} models."
        )

    def _on_benchmark_error(self, err_msg: str) -> None:
        self.btn_run.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Benchmark Error", f"Evaluation failed:\n{err_msg}")

    def _export_csv(self) -> None:
        if not self._current_report:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Benchmark CSV", "lxad_benchmark_results.csv", "CSV Files (*.csv)")
        if path:
            try:
                self._current_report.to_csv(path)
                QMessageBox.information(self, "Success", f"Benchmark exported to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save CSV: {e}")
