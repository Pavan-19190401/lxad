"""
Tests for Ingestion and Storage modules (Phase 1).
"""

import os
import tempfile
import time
import pytest

from lxad.core.ingestion import EventQueue, TelemetryEvent
from lxad.core.storage import RingBuffer, SQLiteStorage


def test_event_queue():
    q = EventQueue(maxsize=10)
    assert q.qsize() == 0

    # Test enqueue and pop
    ev1 = TelemetryEvent(module="CPU", metric_name="cpu_percent", value=45.0)
    assert q.push(ev1)
    assert q.qsize() == 1

    popped = q.pop(timeout=0.1)
    assert popped is not None
    assert popped.metric_name == "cpu_percent"
    assert popped.value == 45.0
    assert q.qsize() == 0

    # Test batch drain
    for i in range(5):
        q.push(TelemetryEvent(metric_name="m", value=float(i)))
    batch = q.drain_batch(max_items=3)
    assert len(batch) == 3
    assert q.qsize() == 2

    # Test queue overflow behavior (drops oldest)
    q.clear()
    for i in range(12):
        q.push(TelemetryEvent(metric_name="overflow", value=float(i)))
    assert q.qsize() == 10
    assert q.dropped_count > 0


def test_ring_buffer():
    buf = RingBuffer(capacity=100, max_age_seconds=2.0)
    now = time.time()

    # Add 5 events
    for i in range(5):
        buf.append(TelemetryEvent(timestamp=now - (4 - i) * 0.1, metric_name="cpu", value=float(i * 10)))

    assert len(buf) == 5

    # Test get_recent
    recent = buf.get_recent(seconds=1.0)
    assert len(recent) == 5

    # Test metric series
    series = buf.get_metric_series("cpu", seconds=1.0)
    assert len(series) == 5
    assert series[-1][1] == 40.0

    # Test expiration
    old_event = TelemetryEvent(timestamp=now - 5.0, metric_name="old", value=1.0)
    buf.append(old_event)
    # The prune operation evicts old events
    buf.append(TelemetryEvent(timestamp=now, metric_name="new", value=2.0))
    events = buf.get_recent(10.0)
    assert not any(e.metric_name == "old" for e in events)


def test_sqlite_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_lxad.db")
        storage = SQLiteStorage(db_path=db_path)

        # Save an alert
        alert_id = storage.save_alert(
            score=85.5,
            severity="High",
            module="CPU",
            anomaly_type="Runaway process",
            justification="CPU spiked to 98% due to bad_proc.exe",
            detectors_fired=["zscore", "iforest"],
            matched_rules=["R-001"],
            metrics={"cpu_percent": 98.0},
            remedial_actions=["Inspect PID 1234", "Restart process"]
        )
        assert alert_id > 0
        assert storage.get_alert_count() == 1

        # Query alert
        alerts = storage.get_alerts(min_score=50.0)
        assert len(alerts) == 1
        a = alerts[0]
        assert a["score"] == 85.5
        assert a["severity"] == "High"
        assert "bad_proc.exe" in a["justification"]
        assert a["matched_rules"] == ["R-001"]
        assert len(a["remedial_actions"]) == 2

        # Save metric summary
        storage.save_metric_summary("cpu_percent", "CPU", 42.0, 95.0, 12.5, 30)

        # Purge test
        deleted = storage.purge_retention(retention_days=7)
        assert deleted == 0  # Should not delete recent data

        # Close explicitly to release Windows SQLite file lock
        storage.close()
