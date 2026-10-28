"""
Telemetry Preprocessing and Feature Extraction Module for LXAD.

Groups streaming events into time windows (tumbling and sliding),
computes rolling statistical moments (mean, max, std, rate of change),
mines log patterns using Drain3, and vectors features for statistical/ML detectors.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

from lxad.core.ingestion import TelemetryEvent

logger = logging.getLogger(__name__)


@dataclass
class WindowFeatures:
    """Aggregated features for a single analysis time window."""
    start_time: float
    end_time: float
    duration: float
    # Map of metric_name -> {'mean': float, 'max': float, 'min': float, 'std': float, 'roc': float, 'count': int, 'last': float}
    metric_stats: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # Event-type and signal counters
    error_count: int = 0
    warning_count: int = 0
    new_process_count: int = 0
    terminated_process_count: int = 0
    file_activity_count: int = 0
    security_failed_logon_count: int = 0
    service_crash_count: int = 0
    active_connections: float = 0.0
    # Log template mining features
    template_frequencies: Dict[int, int] = field(default_factory=dict)
    new_templates_detected: List[str] = field(default_factory=list)
    has_new_template: bool = False
    # Top offenders during this window
    top_processes: List[Dict[str, Any]] = field(default_factory=list)
    raw_events_count: int = 0

    def get_metric(self, name: str, stat: str = "mean", default: float = 0.0) -> float:
        """Safely fetch a specific statistic of a metric."""
        stats = self.metric_stats.get(name)
        if stats and stat in stats:
            return float(stats[stat])
        return default

    def to_vector(self, feature_order: Optional[List[str]] = None) -> np.ndarray:
        """Convert key metrics into a 1D numerical numpy array for ML algorithms."""
        order = feature_order or [
            "cpu_percent",
            "memory_percent",
            "swap_percent",
            "disk_usage_percent",
            "disk_write_bytes_sec",
            "net_sent_bytes_sec",
            "net_recv_bytes_sec",
            "active_connections_count"
        ]
        values = [self.get_metric(k, "mean", 0.0) for k in order]
        # Append counters
        values.append(float(self.error_count))
        values.append(float(self.warning_count))
        values.append(float(self.file_activity_count))
        values.append(float(self.new_process_count))
        values.append(float(1.0 if self.has_new_template else 0.0))
        return np.array(values, dtype=np.float64)


class PreprocessingPipeline:
    """Processes streams of TelemetryEvents into structured feature windows."""

    def __init__(self, window_size_seconds: float = 10.0):
        self.window_size_seconds = max(2.0, window_size_seconds)
        self._miner_config = TemplateMinerConfig()
        self._miner_config.profiling_enabled = False
        self._template_miner = TemplateMiner(config=self._miner_config)
        self._known_cluster_ids: Set[int] = set()

    def process_window(
        self,
        events: List[TelemetryEvent],
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None
    ) -> WindowFeatures:
        """Aggregate a collection of TelemetryEvents into a WindowFeatures object."""
        if not events and start_ts is None:
            now = 0.0
            return WindowFeatures(start_time=now, end_time=now, duration=self.window_size_seconds)

        t_min = start_ts if start_ts is not None else (min(e.timestamp for e in events) if events else 0.0)
        t_max = end_ts if end_ts is not None else (max(e.timestamp for e in events) if events else t_min + self.window_size_seconds)
        duration = max(0.001, t_max - t_min)

        wf = WindowFeatures(
            start_time=t_min,
            end_time=t_max,
            duration=duration,
            raw_events_count=len(events)
        )

        # Buckets for metric values: metric_name -> list of (timestamp, value)
        metric_values: Dict[str, List[Tuple[float, float]]] = {}
        top_procs: List[Dict[str, Any]] = []

        for ev in events:
            # 1. Classify severity counters
            if ev.severity_level in ("ERROR", "CRITICAL"):
                wf.error_count += 1
            elif ev.severity_level == "WARNING":
                wf.warning_count += 1

            # 2. Track specialized signal types
            if ev.type == "process_spawn":
                wf.new_process_count += 1
            elif ev.type == "process_exit":
                wf.terminated_process_count += 1
            elif ev.metric_name == "security_failed_logon":
                wf.security_failed_logon_count += 1
            elif ev.metric_name == "service_crash":
                wf.service_crash_count += 1
            elif ev.source == "filewatch":
                wf.file_activity_count += 1
            elif ev.metric_name == "active_connections_count":
                wf.active_connections = max(wf.active_connections, ev.value)

            # Store top processes
            if ev.type == "process_top" and ev.details.get("top_cpu"):
                top_procs = ev.details.get("top_cpu", [])

            # 3. Numeric metrics
            if ev.type == "metric" and ev.metric_name:
                metric_values.setdefault(ev.metric_name, []).append((ev.timestamp, ev.value))

            # 4. Drain3 Log Template Mining
            if ev.raw_text and ev.source in ("eventlogs", "log_file", "synthetic_log"):
                try:
                    cluster_res = self._template_miner.add_log_message(ev.raw_text)
                    if cluster_res:
                        cid = cluster_res["cluster_id"]
                        ev.template_id = str(cid)
                        wf.template_frequencies[cid] = wf.template_frequencies.get(cid, 0) + 1
                        if cid not in self._known_cluster_ids:
                            self._known_cluster_ids.add(cid)
                            wf.has_new_template = True
                            tmpl_str = cluster_res.get("template_mined", ev.raw_text[:80])
                            wf.new_templates_detected.append(tmpl_str)
                except Exception as e:
                    logger.debug("Drain3 parse error: %s", e)

        wf.top_processes = top_procs

        # Compute moments for each metric
        for m_name, series in metric_values.items():
            vals = [val for _, val in series]
            if not vals:
                continue

            arr = np.array(vals, dtype=np.float64)
            mean_val = float(np.mean(arr))
            max_val = float(np.max(arr))
            min_val = float(np.min(arr))
            std_val = float(np.std(arr)) if len(arr) > 1 else 0.0

            # Rate of change: (last_val - first_val) / time_span
            roc = 0.0
            if len(series) >= 2:
                dt = series[-1][0] - series[0][0]
                if dt > 0.001:
                    roc = float((series[-1][1] - series[0][1]) / dt)

            wf.metric_stats[m_name] = {
                "mean": mean_val,
                "max": max_val,
                "min": min_val,
                "std": std_val,
                "roc": roc,
                "count": len(vals),
                "last": float(series[-1][1])
            }

        return wf
