"""
Tests for Preprocessing module and Drain3 log template mining (Phase 2).
"""

import time
import numpy as np
from lxad.core.ingestion import TelemetryEvent
from lxad.core.preprocessing import PreprocessingPipeline, WindowFeatures


def test_preprocessing_moment_calculation():
    pipeline = PreprocessingPipeline(window_size_seconds=10.0)
    now = time.time()

    events = [
        TelemetryEvent(timestamp=now - 5, module="CPU", metric_name="cpu_percent", value=20.0),
        TelemetryEvent(timestamp=now - 3, module="CPU", metric_name="cpu_percent", value=30.0),
        TelemetryEvent(timestamp=now - 1, module="CPU", metric_name="cpu_percent", value=40.0),
        TelemetryEvent(timestamp=now - 2, module="SystemLog", severity_level="ERROR", raw_text="Failed database connection"),
        TelemetryEvent(timestamp=now - 1, module="SystemLog", severity_level="WARNING", raw_text="High disk latency"),
        TelemetryEvent(timestamp=now - 1, source="filewatch", type="file_event", value=1.0),
    ]

    wf = pipeline.process_window(events, start_ts=now - 10, end_ts=now)
    assert wf.raw_events_count == 6
    assert wf.error_count == 1
    assert wf.warning_count == 1
    assert wf.file_activity_count == 1

    # Check metric statistics
    assert "cpu_percent" in wf.metric_stats
    stats = wf.metric_stats["cpu_percent"]
    assert stats["mean"] == 30.0
    assert stats["min"] == 20.0
    assert stats["max"] == 40.0
    assert stats["count"] == 3
    assert stats["roc"] > 0  # 20 to 40 over 4 seconds

    # Check vector export
    vec = wf.to_vector()
    assert isinstance(vec, np.ndarray)
    assert len(vec) > 5


def test_drain3_log_clustering():
    pipeline = PreprocessingPipeline()
    now = time.time()

    # Repeated template messages
    events = [
        TelemetryEvent(timestamp=now, source="eventlogs", raw_text="Authentication failed for user admin from 192.168.1.10"),
        TelemetryEvent(timestamp=now, source="eventlogs", raw_text="Authentication failed for user root from 10.0.0.5"),
        TelemetryEvent(timestamp=now, source="eventlogs", raw_text="Service worker thread pool exhausted"),
    ]

    wf = pipeline.process_window(events)
    assert wf.has_new_template
    assert len(wf.new_templates_detected) > 0
    assert len(wf.template_frequencies) > 0
