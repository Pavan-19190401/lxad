"""
Storage subsystem for LXAD: In-memory RingBuffer and SQLite persistence.

- RingBuffer: O(1) in-memory circular buffer keeping the last N minutes of TelemetryEvents
  for ultra-fast feature extraction and preprocessing without disk I/O.
- SQLiteStorage: Persistent ACID store for historical alerts, aggregations,
  and baselines with automatic retention management.
"""

from __future__ import annotations

import collections
import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from lxad.core.ingestion import TelemetryEvent


class RingBuffer:
    """Thread-safe circular buffer storing events within a moving time window."""

    def __init__(self, capacity: int = 10000, max_age_seconds: float = 900.0):
        self.capacity = capacity
        self.max_age_seconds = max_age_seconds  # Default 15 minutes
        self._buffer: collections.deque[TelemetryEvent] = collections.deque(maxlen=capacity)
        self._lock = threading.RLock()

    def append(self, event: TelemetryEvent) -> None:
        """Add event to buffer and periodically evict expired events."""
        with self._lock:
            self._buffer.append(event)
            self._prune_expired()

    def extend(self, events: List[TelemetryEvent]) -> None:
        """Add multiple events atomically."""
        with self._lock:
            self._buffer.extend(events)
            self._prune_expired()

    def _prune_expired(self) -> None:
        """Remove events older than max_age_seconds."""
        cutoff = time.time() - self.max_age_seconds
        # Filter all elements to keep only non-expired
        if self._buffer and any(e.timestamp < cutoff for e in self._buffer):
            self._buffer = collections.deque(
                (e for e in self._buffer if e.timestamp >= cutoff),
                maxlen=self.capacity
            )

    def get_events_since(self, since_timestamp: float) -> List[TelemetryEvent]:
        """Return all events recorded at or after since_timestamp."""
        with self._lock:
            return [e for e in self._buffer if e.timestamp >= since_timestamp]

    def get_events_window(self, start_ts: float, end_ts: float) -> List[TelemetryEvent]:
        """Return events occurring within [start_ts, end_ts]."""
        with self._lock:
            return [e for e in self._buffer if start_ts <= e.timestamp <= end_ts]

    def get_recent(self, seconds: float) -> List[TelemetryEvent]:
        """Return events from the last `seconds` duration."""
        cutoff = time.time() - seconds
        return self.get_events_since(cutoff)

    def get_metric_series(self, metric_name: str, seconds: float) -> List[Tuple[float, float]]:
        """Return (timestamp, value) pairs for a specific metric over the last `seconds`."""
        cutoff = time.time() - seconds
        with self._lock:
            return [
                (e.timestamp, e.value)
                for e in self._buffer
                if e.metric_name == metric_name and e.timestamp >= cutoff
            ]

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


class SQLiteStorage:
    """Thread-safe SQLite persistent storage for alerts and metric summaries."""

    def __init__(self, db_path: str = "data/lxad_storage.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA synchronous = NORMAL;")
        self._init_db()

    def close(self) -> None:
        """Close SQLite connection."""
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def _init_db(self) -> None:
        """Create necessary tables and indices."""
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    score REAL NOT NULL,
                    severity TEXT NOT NULL,
                    module TEXT NOT NULL,
                    anomaly_type TEXT NOT NULL,
                    justification TEXT NOT NULL,
                    detectors_fired TEXT NOT NULL,
                    matched_rules TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    remedial_actions TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(timestamp);
                CREATE INDEX IF NOT EXISTS idx_alerts_sev ON alerts(severity);
                CREATE INDEX IF NOT EXISTS idx_alerts_mod ON alerts(module);

                CREATE TABLE IF NOT EXISTS metric_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    metric_name TEXT NOT NULL,
                    module TEXT NOT NULL,
                    mean_val REAL NOT NULL,
                    max_val REAL NOT NULL,
                    std_val REAL NOT NULL,
                    sample_count INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_metric_ts ON metric_summaries(timestamp);
                CREATE INDEX IF NOT EXISTS idx_metric_name ON metric_summaries(metric_name);
            """)

    def save_alert(
        self,
        score: float,
        severity: str,
        module: str,
        anomaly_type: str,
        justification: str,
        detectors_fired: List[str],
        matched_rules: List[str],
        metrics: Dict[str, Any],
        remedial_actions: List[str],
        timestamp: Optional[float] = None
    ) -> int:
        """Store an anomaly alert into SQLite."""
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO alerts (
                    timestamp, score, severity, module, anomaly_type,
                    justification, detectors_fired, matched_rules,
                    metrics_json, remedial_actions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    score,
                    severity,
                    module,
                    anomaly_type,
                    justification,
                    json.dumps(detectors_fired),
                    json.dumps(matched_rules),
                    json.dumps(metrics),
                    json.dumps(remedial_actions),
                ),
            )
            self._conn.commit()
            return cursor.lastrowid or 0

    def get_alerts(
        self,
        limit: int = 100,
        min_score: float = 0.0,
        severity: Optional[str] = None,
        module: Optional[str] = None,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Query alerts with flexible filtering."""
        query = "SELECT * FROM alerts WHERE score >= ?"
        params: List[Any] = [min_score]

        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if module:
            query += " AND module = ?"
            params.append(module)
        if start_ts is not None:
            query += " AND timestamp >= ?"
            params.append(start_ts)
        if end_ts is not None:
            query += " AND timestamp <= ?"
            params.append(end_ts)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                results.append({
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "score": r["score"],
                    "severity": r["severity"],
                    "module": r["module"],
                    "anomaly_type": r["anomaly_type"],
                    "justification": r["justification"],
                    "detectors_fired": json.loads(r["detectors_fired"]),
                    "matched_rules": json.loads(r["matched_rules"]),
                    "metrics": json.loads(r["metrics_json"]),
                    "remedial_actions": json.loads(r["remedial_actions"]),
                })
            return results

    def save_metric_summary(
        self,
        metric_name: str,
        module: str,
        mean_val: float,
        max_val: float,
        std_val: float,
        sample_count: int,
        timestamp: Optional[float] = None
    ) -> None:
        """Save aggregated window metric summary."""
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO metric_summaries (
                    timestamp, metric_name, module, mean_val, max_val, std_val, sample_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, metric_name, module, mean_val, max_val, std_val, sample_count)
            )
            self._conn.commit()

    def purge_retention(self, retention_days: int = 7) -> int:
        """Remove alerts and metric summaries older than retention_days."""
        cutoff = time.time() - (retention_days * 86400.0)
        with self._lock:
            cur1 = self._conn.execute("DELETE FROM alerts WHERE timestamp < ?", (cutoff,))
            cur2 = self._conn.execute("DELETE FROM metric_summaries WHERE timestamp < ?", (cutoff,))
            self._conn.commit()
            deleted = cur1.rowcount + cur2.rowcount
            return deleted

    def get_alert_count(self) -> int:
        """Get total number of alerts recorded."""
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM alerts")
            return cur.fetchone()[0]
