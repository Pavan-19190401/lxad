"""
Unified Telemetry Ingestion Layer for LXAD.

Defines the standard TelemetryEvent schema and a thread-safe EventQueue
for multiplexing data from system collectors to storage and analytics.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class TelemetryEvent:
    """Standardized event representation for all system signals."""
    timestamp: float = field(default_factory=time.time)
    source: str = "system"                   # 'metrics', 'processes', 'eventlogs', 'filewatch', 'network', 'synthetic'
    module: str = "general"                  # 'CPU', 'RAM', 'Disk', 'Network', 'Process', 'Security', 'FileSystem'
    type: str = "metric"                     # 'metric', 'process_event', 'log_event', 'file_event', 'network_event'
    metric_name: str = ""                    # 'cpu_percent', 'memory_percent', 'disk_write_rate', etc.
    value: float = 0.0                       # Numerical value for statistical calculation
    severity_level: str = "INFO"             # 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    raw_text: str = ""                       # Raw log text, process commandline, file path, etc.
    template_id: Optional[str] = None        # Drain3 template id or log pattern id
    details: Dict[str, Any] = field(default_factory=dict)  # Key-value metadata

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataclass to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TelemetryEvent:
        """Construct TelemetryEvent from dictionary safely."""
        valid_keys = {
            "timestamp", "source", "module", "type", "metric_name",
            "value", "severity_level", "raw_text", "template_id", "details"
        }
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class EventQueue:
    """Thread-safe FIFO event queue with capacity constraints."""

    def __init__(self, maxsize: int = 5000):
        self._queue: queue.Queue[TelemetryEvent] = queue.Queue(maxsize=maxsize)
        self._dropped_count: int = 0

    def push(self, event: TelemetryEvent) -> bool:
        """Enqueue an event. If full, drops oldest to preserve real-time recency."""
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            try:
                # Drop oldest event to make room
                self._queue.get_nowait()
                self._dropped_count += 1
                self._queue.put_nowait(event)
                return True
            except (queue.Empty, queue.Full):
                self._dropped_count += 1
                return False

    def pop(self, timeout: float = 0.5) -> Optional[TelemetryEvent]:
        """Retrieve the next event, waiting up to timeout seconds."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain_batch(self, max_items: int = 500) -> List[TelemetryEvent]:
        """Retrieve up to max_items events immediately without blocking."""
        batch: List[TelemetryEvent] = []
        while len(batch) < max_items:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def qsize(self) -> int:
        """Return the current number of queued events."""
        return self._queue.qsize()

    @property
    def dropped_count(self) -> int:
        """Return total dropped events due to buffer overflow."""
        return self._dropped_count

    def clear(self) -> None:
        """Discard all pending items."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
