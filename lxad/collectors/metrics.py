"""
System Metrics Collector for LXAD.

Collects CPU (per-core and total), RAM, swap, disk usage/IO, network IO,
battery and temperatures (if supported), sampling every 1-2 seconds in a background thread.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

import psutil

from lxad.core.ingestion import EventQueue, TelemetryEvent

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Background worker sampling system hardware performance metrics."""

    def __init__(self, queue: EventQueue, interval: float = 1.0):
        self.queue = queue
        self.interval = max(0.5, interval)
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Prior counters for calculating rates
        self._last_disk_io: Optional[Any] = None
        self._last_net_io: Optional[Any] = None
        self._last_sample_time: float = time.time()

        # Prime psutil cpu measurement
        try:
            psutil.cpu_percent(interval=None)
            psutil.cpu_percent(interval=None, percpu=True)
        except Exception as e:
            logger.debug("Failed initial CPU sample: %s", e)

    def start(self) -> None:
        """Start the metrics collector thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="LXAD-MetricsCollector", daemon=True)
        self._thread.start()
        logger.info("MetricsCollector started (interval=%.1fs)", self.interval)

    def stop(self) -> None:
        """Signal collector thread to stop and wait for completion."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("MetricsCollector stopped")

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        while self._running:
            t0 = time.time()
            try:
                self._collect()
            except Exception as e:
                logger.error("Error during metric collection: %s", e, exc_info=True)

            elapsed = time.time() - t0
            sleep_duration = max(0.1, self.interval - elapsed)
            # Sleep in small slices for fast cancellation
            sleep_end = time.time() + sleep_duration
            while self._running and time.time() < sleep_end:
                time.sleep(0.1)

    def _collect(self) -> None:
        now = time.time()
        dt = max(0.001, now - self._last_sample_time)
        self._last_sample_time = now

        # 1. CPU Metrics
        try:
            total_cpu = psutil.cpu_percent(interval=None)
            per_core = psutil.cpu_percent(interval=None, percpu=True)

            self.queue.push(TelemetryEvent(
                timestamp=now,
                source="metrics",
                module="CPU",
                type="metric",
                metric_name="cpu_percent",
                value=float(total_cpu),
                details={"per_core": per_core, "core_count": len(per_core)}
            ))
        except Exception as e:
            logger.debug("CPU metric error: %s", e)

        # 2. Memory Metrics
        try:
            vmem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            self.queue.push(TelemetryEvent(
                timestamp=now,
                source="metrics",
                module="RAM",
                type="metric",
                metric_name="memory_percent",
                value=float(vmem.percent),
                details={
                    "total_mb": vmem.total / (1024 * 1024),
                    "available_mb": vmem.available / (1024 * 1024),
                    "used_mb": vmem.used / (1024 * 1024)
                }
            ))

            self.queue.push(TelemetryEvent(
                timestamp=now,
                source="metrics",
                module="RAM",
                type="metric",
                metric_name="swap_percent",
                value=float(swap.percent),
                details={
                    "total_mb": swap.total / (1024 * 1024),
                    "used_mb": swap.used / (1024 * 1024)
                }
            ))
        except Exception as e:
            logger.debug("Memory metric error: %s", e)

        # 3. Disk Metrics (Usage & I/O rates)
        try:
            # Root/System disk usage
            disk_path = "C:\\" if psutil.WINDOWS else "/"
            disk_usage = psutil.disk_usage(disk_path)
            self.queue.push(TelemetryEvent(
                timestamp=now,
                source="metrics",
                module="Disk",
                type="metric",
                metric_name="disk_usage_percent",
                value=float(disk_usage.percent),
                details={"free_gb": disk_usage.free / (1024**3), "total_gb": disk_usage.total / (1024**3)}
            ))

            current_disk_io = psutil.disk_io_counters()
            if current_disk_io and self._last_disk_io:
                read_rate = (current_disk_io.read_bytes - self._last_disk_io.read_bytes) / dt
                write_rate = (current_disk_io.write_bytes - self._last_disk_io.write_bytes) / dt
                self.queue.push(TelemetryEvent(
                    timestamp=now,
                    source="metrics",
                    module="Disk",
                    type="metric",
                    metric_name="disk_read_bytes_sec",
                    value=max(0.0, float(read_rate)),
                ))
                self.queue.push(TelemetryEvent(
                    timestamp=now,
                    source="metrics",
                    module="Disk",
                    type="metric",
                    metric_name="disk_write_bytes_sec",
                    value=max(0.0, float(write_rate)),
                ))
            self._last_disk_io = current_disk_io
        except Exception as e:
            logger.debug("Disk metric error: %s", e)

        # 4. Network Metrics (I/O rate)
        try:
            current_net_io = psutil.net_io_counters()
            if current_net_io and self._last_net_io:
                sent_rate = (current_net_io.bytes_sent - self._last_net_io.bytes_sent) / dt
                recv_rate = (current_net_io.bytes_recv - self._last_net_io.bytes_recv) / dt
                self.queue.push(TelemetryEvent(
                    timestamp=now,
                    source="metrics",
                    module="Network",
                    type="metric",
                    metric_name="net_sent_bytes_sec",
                    value=max(0.0, float(sent_rate)),
                ))
                self.queue.push(TelemetryEvent(
                    timestamp=now,
                    source="metrics",
                    module="Network",
                    type="metric",
                    metric_name="net_recv_bytes_sec",
                    value=max(0.0, float(recv_rate)),
                ))
            self._last_net_io = current_net_io
        except Exception as e:
            logger.debug("Network metric error: %s", e)

        # 5. Sensors (Battery and Temperature if available)
        try:
            sensors_battery = psutil.sensors_battery()
            if sensors_battery is not None:
                self.queue.push(TelemetryEvent(
                    timestamp=now,
                    source="metrics",
                    module="Power",
                    type="metric",
                    metric_name="battery_percent",
                    value=float(sensors_battery.percent),
                    details={"power_plugged": sensors_battery.power_plugged}
                ))
        except Exception as e:
            logger.debug("Battery metric error: %s", e)

        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        if entries:
                            self.queue.push(TelemetryEvent(
                                timestamp=now,
                                source="metrics",
                                module="Temperature",
                                type="metric",
                                metric_name="temperature_celsius",
                                value=float(entries[0].current),
                                details={"sensor": name}
                            ))
        except Exception as e:
            logger.debug("Temperature metric error: %s", e)
