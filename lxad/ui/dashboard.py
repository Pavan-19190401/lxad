"""
Vercel / Datadog Aesthetic Telemetry Dashboard for LXAD.

Implements the exact layout and visual design from the user's reference:
- Header: Title, subtitle, and time-range toggle buttons [ 1m | 5m | 15m ]
- 2x2 Metric Sparkline Cards:
  * CPU saturation (trend %, bold value, smooth white curve with area fill)
  * Memory pressure (trend %, bold value, smooth white curve with area fill)
  * Disk write rate (trend %, bold value, smooth white curve with area fill)
  * Network outbound (trend %, bold value, smooth white curve with area fill)
- Wide Detailed Trend Card (bottom):
  * Left title & time scope
  * Right summary statistics (Current Big Value, Peak, Average, Status)
  * Full-width smooth waveform chart with shaded area under the curve
- Anomaly markers & interactive crosshairs on the waveform
"""

from __future__ import annotations

import collections
import time
from typing import Any, Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QFrame, QPushButton, QSizePolicy
)

# Dark theme pyqtgraph configuration
pg.setConfigOption("background", "#121417")
pg.setConfigOption("foreground", "#7d8590")
pg.setConfigOption("antialias", False)


class MetricSparklineCard(QFrame):
    """Sleek matte-black metric card with embedded axis-less sparkline."""
    clicked = Signal(str)

    def __init__(self, key: str, title: str, unit: str = "%", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.key = key
        self.title = title
        self.unit = unit
        self._history: collections.deque[float] = collections.deque(maxlen=60)
        self._is_selected = False

        self.setObjectName("sparklineCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(135)
        self.setCursor(Qt.PointingHandCursor)

        self._init_ui()
        self._update_border()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 8)
        layout.setSpacing(4)

        # Header Row: Metric Name on Left, Trend on Right
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        self.lbl_title = QLabel(self.title)
        self.lbl_title.setStyleSheet("color: #8b949e; font-size: 12px; font-weight: 500;")
        header_row.addWidget(self.lbl_title)
        header_row.addStretch()

        self.lbl_trend = QLabel("→ 0.0%")
        self.lbl_trend.setStyleSheet("color: #7d8590; font-size: 11px; font-weight: 600;")
        header_row.addWidget(self.lbl_trend)
        layout.addLayout(header_row)

        # Big Bold Value
        self.lbl_value = QLabel(f"0.0 {self.unit}")
        self.lbl_value.setStyleSheet("color: #ffffff; font-size: 24px; font-weight: 700; letter-spacing: -0.5px;")
        layout.addWidget(self.lbl_value)

        # Seamless Embedded Sparkline (No axes, no grid, clean white curve)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setFixedHeight(55)
        self.plot_widget.hideAxis("left")
        self.plot_widget.hideAxis("bottom")
        self.plot_widget.showGrid(False, False)
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setStyleSheet("background: transparent; border: none;")

        # Curve with subtle gradient area fill underneath
        self.curve = self.plot_widget.plot(
            pen=pg.mkPen("#ffffff", width=2),
            fillLevel=0.0,
            fillBrush=pg.mkBrush(255, 255, 255, 18)
        )

        # Crosshair / Anomaly indicator point
        self.anomaly_scatter = pg.ScatterPlotItem(
            size=8,
            symbol="s",  # Square marker like in the reference image
            pen=pg.mkPen("#f85149", width=1.5),
            brush=pg.mkBrush("#f85149")
        )
        self.plot_widget.addItem(self.anomaly_scatter)

        layout.addWidget(self.plot_widget)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.key)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        self._update_border()

    def _update_border(self) -> None:
        if self._is_selected:
            self.setStyleSheet("""
                QFrame#sparklineCard {
                    background-color: #121417;
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    border-radius: 10px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#sparklineCard {
                    background-color: #121417;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 10px;
                }
                QFrame#sparklineCard:hover {
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    background-color: #15171b;
                }
            """)

    def update_value(self, val: float, is_anomaly: bool = False) -> None:
        """Push new data point, calculate trend, and redraw sparkline."""
        prev_val = self._history[-1] if self._history else val
        self._history.append(val)

        # Format bold value
        if self.unit == "%":
            self.lbl_value.setText(f"{val:.1f} %")
        elif "MB" in self.unit:
            self.lbl_value.setText(f"{val:.2f} MB/s")
        else:
            self.lbl_value.setText(f"{val:.1f} {self.unit}")

        # Calculate percentage trend
        if prev_val > 0.001:
            diff_pct = ((val - prev_val) / prev_val) * 100.0
            if diff_pct > 0.5:
                self.lbl_trend.setText(f"↗ {abs(diff_pct):.1f}%")
                self.lbl_trend.setStyleSheet("color: #d29922; font-size: 11px; font-weight: 600;")
            elif diff_pct < -0.5:
                self.lbl_trend.setText(f"↘ {abs(diff_pct):.1f}%")
                self.lbl_trend.setStyleSheet("color: #3fb950; font-size: 11px; font-weight: 600;")
            else:
                self.lbl_trend.setText(f"→ {abs(diff_pct):.1f}%")
                self.lbl_trend.setStyleSheet("color: #7d8590; font-size: 11px; font-weight: 600;")

        # Update curve
        y_data = list(self._history)
        x_data = list(range(len(y_data)))
        self.curve.setData(x_data, y_data)

        # Plot anomaly marker if flagged
        if is_anomaly and y_data:
            self.anomaly_scatter.setData([{"pos": (len(y_data) - 1, y_data[-1])}])
        else:
            self.anomaly_scatter.clear()


class DetailedTrendCard(QFrame):
    """Wide detailed trend card matching the bottom section of the reference design."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._history: collections.deque[float] = collections.deque(maxlen=120)
        self._title = "System Alert Score & Composite Risk"
        self._unit = "Score"

        self.setObjectName("detailedCard")
        self.setStyleSheet("""
            QFrame#detailedCard {
                background-color: #121417;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        # Top Row: Title on Left, Detailed Summary Table on Right
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        # Left Title
        self.lbl_title = QLabel("System Alert Score & Composite Risk")
        self.lbl_title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 600;")
        top_row.addWidget(self.lbl_title)
        top_row.addStretch()

        # Right Summary Block: Big stat + Mini table (Peak, Average, Low)
        right_box = QHBoxLayout()
        right_box.setSpacing(16)

        self.lbl_big_stat = QLabel("0 Score")
        self.lbl_big_stat.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: 700; letter-spacing: -0.5px;")
        right_box.addWidget(self.lbl_big_stat)

        # Mini Stats Table
        mini_grid = QGridLayout()
        mini_grid.setContentsMargins(0, 0, 0, 0)
        mini_grid.setHorizontalSpacing(10)
        mini_grid.setVerticalSpacing(2)

        lbl_p_title = QLabel("Peak")
        lbl_p_title.setStyleSheet("color: #7d8590; font-size: 11px;")
        self.lbl_peak_val = QLabel("0.0")
        self.lbl_peak_val.setStyleSheet("color: #e6edf3; font-size: 11px; font-weight: 600;")

        lbl_a_title = QLabel("Average")
        lbl_a_title.setStyleSheet("color: #7d8590; font-size: 11px;")
        self.lbl_avg_val = QLabel("0.0")
        self.lbl_avg_val.setStyleSheet("color: #e6edf3; font-size: 11px; font-weight: 600;")

        lbl_l_title = QLabel("Status")
        lbl_l_title.setStyleSheet("color: #7d8590; font-size: 11px;")
        self.lbl_status_val = QLabel("Nominal")
        self.lbl_status_val.setStyleSheet("color: #3fb950; font-size: 11px; font-weight: 600;")

        mini_grid.addWidget(lbl_p_title, 0, 0)
        mini_grid.addWidget(self.lbl_peak_val, 0, 1)
        mini_grid.addWidget(lbl_a_title, 1, 0)
        mini_grid.addWidget(self.lbl_avg_val, 1, 1)
        mini_grid.addWidget(lbl_l_title, 2, 0)
        mini_grid.addWidget(self.lbl_status_val, 2, 1)

        right_box.addLayout(mini_grid)
        top_row.addLayout(right_box)
        layout.addLayout(top_row)

        # Wide Smooth Waveform Graph
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setFixedHeight(95)
        self.plot_widget.hideAxis("left")
        self.plot_widget.hideAxis("bottom")
        self.plot_widget.showGrid(False, False)
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setStyleSheet("background: transparent; border: none;")

        self.curve = self.plot_widget.plot(
            pen=pg.mkPen("#ffffff", width=2),
            fillLevel=0.0,
            fillBrush=pg.mkBrush(255, 255, 255, 18)
        )

        self.anomaly_scatter = pg.ScatterPlotItem(
            size=10,
            symbol="s",
            pen=pg.mkPen("#f85149", width=2),
            brush=pg.mkBrush("#b62324")
        )
        self.plot_widget.addItem(self.anomaly_scatter)

        layout.addWidget(self.plot_widget)

    def set_content_mode(self, title: str, unit: str) -> None:
        self._title = title
        self._unit = unit
        self.lbl_title.setText(title)
        self._history.clear()

    def update_data(self, val: float, is_anomaly: bool = False, severity: str = "Low") -> None:
        self._history.append(val)
        y_data = list(self._history)
        x_data = list(range(len(y_data)))

        # Update curve
        self.curve.setData(x_data, y_data)

        # Summary values
        peak = max(y_data) if y_data else 0.0
        avg = sum(y_data) / len(y_data) if y_data else 0.0

        if self._unit == "Score":
            self.lbl_big_stat.setText(f"{int(round(val))} Score")
            self.lbl_peak_val.setText(f"{peak:.0f}")
            self.lbl_avg_val.setText(f"{avg:.1f}")
            self.lbl_status_val.setText(f"{severity.capitalize()}")
            if severity in ("High", "Critical"):
                self.lbl_status_val.setStyleSheet("color: #f85149; font-size: 11px; font-weight: 600;")
                self.lbl_big_stat.setStyleSheet("color: #f85149; font-size: 22px; font-weight: 700;")
            elif severity == "Medium":
                self.lbl_status_val.setStyleSheet("color: #d29922; font-size: 11px; font-weight: 600;")
                self.lbl_big_stat.setStyleSheet("color: #d29922; font-size: 22px; font-weight: 700;")
            else:
                self.lbl_status_val.setStyleSheet("color: #3fb950; font-size: 11px; font-weight: 600;")
                self.lbl_big_stat.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: 700;")
        else:
            self.lbl_big_stat.setText(f"{val:.1f} {self._unit}")
            self.lbl_peak_val.setText(f"{peak:.1f} {self._unit}")
            self.lbl_avg_val.setText(f"{avg:.1f} {self._unit}")
            self.lbl_status_val.setText("Active")

        # Scatter marker
        if is_anomaly and y_data:
            self.anomaly_scatter.setData([{"pos": (len(y_data) - 1, y_data[-1])}])
        else:
            self.anomaly_scatter.clear()


class DashboardView(QWidget):
    """Refined Telemetry Dashboard implementing the Vercel/Datadog Sparkline Grid."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_selected_key = "score"

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(14)

        # ==========================================
        # TOP HEADER: Title, Subtitle & Time Range Pills
        # ==========================================
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        lbl_main = QLabel("Host PC Health & Telemetry")
        lbl_main.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: 700; letter-spacing: -0.4px;")
        title_box.addWidget(lbl_main)

        lbl_sub = QLabel("Live signals from full PC hardware & OS collectors. Select any card for detailed inspection.")
        lbl_sub.setStyleSheet("color: #7d8590; font-size: 12px; font-weight: 400;")
        title_box.addWidget(lbl_sub)
        header_row.addLayout(title_box)
        header_row.addStretch()

        # Time range pill buttons [ 1m | 5m | 15m ] as in screenshot
        range_frame = QFrame()
        range_frame.setStyleSheet("""
            QFrame {
                background-color: #121417;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 2px;
            }
        """)
        r_layout = QHBoxLayout(range_frame)
        r_layout.setContentsMargins(2, 2, 2, 2)
        r_layout.setSpacing(2)

        self.btn_r1 = QPushButton("1m")
        self.btn_r5 = QPushButton("5m")
        self.btn_r15 = QPushButton("15m")

        for b in [self.btn_r1, self.btn_r5, self.btn_r15]:
            b.setCheckable(True)
            b.setFixedSize(36, 24)
            b.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #7d8590;
                    border: none;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:checked {
                    background-color: #212429;
                    color: #ffffff;
                }
                QPushButton:hover:!checked {
                    color: #c9d1d9;
                }
            """)
        self.btn_r1.setChecked(True)
        r_layout.addWidget(self.btn_r1)
        r_layout.addWidget(self.btn_r5)
        r_layout.addWidget(self.btn_r15)

        header_row.addWidget(range_frame)
        main_layout.addLayout(header_row)

        # ==========================================
        # 2x2 METRIC SPARKLINE CARDS GRID (as in user screenshot)
        # ==========================================
        grid = QGridLayout()
        grid.setSpacing(14)

        # Card 1: CPU Saturation
        self.card_cpu = MetricSparklineCard(key="cpu", title="CPU saturation", unit="%")
        self.card_cpu.clicked.connect(self._on_card_clicked)
        grid.addWidget(self.card_cpu, 0, 0)

        # Card 2: Memory Pressure
        self.card_mem = MetricSparklineCard(key="mem", title="Memory utilization", unit="%")
        self.card_mem.clicked.connect(self._on_card_clicked)
        grid.addWidget(self.card_mem, 0, 1)

        # Card 3: Disk Write Rate
        self.card_disk = MetricSparklineCard(key="disk", title="Disk write throughput", unit="MB/s")
        self.card_disk.clicked.connect(self._on_card_clicked)
        grid.addWidget(self.card_disk, 1, 0)

        # Card 4: Network Outbound
        self.card_net = MetricSparklineCard(key="net", title="Network outbound rate", unit="MB/s")
        self.card_net.clicked.connect(self._on_card_clicked)
        grid.addWidget(self.card_net, 1, 1)

        main_layout.addLayout(grid)

        # ==========================================
        # BOTTOM WIDE CARD: Detailed Trend View
        # ==========================================
        self.detail_card = DetailedTrendCard()
        main_layout.addWidget(self.detail_card)

        # Default selection: Alert Score / CPU
        self.card_cpu.set_selected(True)

    def _on_card_clicked(self, key: str) -> None:
        """Switch wide detailed view based on selected sparkline card."""
        self._current_selected_key = key
        self.card_cpu.set_selected(key == "cpu")
        self.card_mem.set_selected(key == "mem")
        self.card_disk.set_selected(key == "disk")
        self.card_net.set_selected(key == "net")

        if key == "cpu":
            self.detail_card.set_content_mode("CPU saturation detailed trend (live)", "%")
        elif key == "mem":
            self.detail_card.set_content_mode("Memory utilization detailed trend (live)", "%")
        elif key == "disk":
            self.detail_card.set_content_mode("Disk write throughput trend (live)", "MB/s")
        elif key == "net":
            self.detail_card.set_content_mode("Network outbound bandwidth trend (live)", "MB/s")

    def update_metrics(
        self,
        cpu_val: float,
        ram_val: float,
        swap_val: float,
        disk_write_mb: float,
        net_sent_mb: float,
        top_procs: List[Dict[str, Any]],
        anomaly_detected: bool = False
    ) -> None:
        """Stream real-world data points to sparkline cards and wide detail card."""
        self.card_cpu.update_value(cpu_val, is_anomaly=anomaly_detected)
        self.card_mem.update_value(ram_val, is_anomaly=(ram_val > 88.0))
        self.card_disk.update_value(disk_write_mb, is_anomaly=(disk_write_mb > 15.0))
        self.card_net.update_value(net_sent_mb, is_anomaly=(net_sent_mb > 5.0))

        # Update detailed bottom card based on current active selection
        if self._current_selected_key == "cpu":
            self.detail_card.update_data(cpu_val, is_anomaly=anomaly_detected, severity="High" if cpu_val > 80 else "Low")
        elif self._current_selected_key == "mem":
            self.detail_card.update_data(ram_val, is_anomaly=(ram_val > 88.0), severity="High" if ram_val > 88 else "Low")
        elif self._current_selected_key == "disk":
            self.detail_card.update_data(disk_write_mb, is_anomaly=(disk_write_mb > 15.0), severity="Critical" if disk_write_mb > 25 else "Low")
        elif self._current_selected_key == "net":
            self.detail_card.update_data(net_sent_mb, is_anomaly=(net_sent_mb > 5.0), severity="Medium" if net_sent_mb > 5 else "Low")
        else:
            self.detail_card.update_data(cpu_val, is_anomaly=anomaly_detected)

    def set_score(self, score: float, severity: str) -> None:
        """Update system alert score when in score mode."""
        if self._current_selected_key == "score":
            self.detail_card.update_data(score, is_anomaly=(score >= 40.0), severity=severity)
