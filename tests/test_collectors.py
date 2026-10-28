"""
Tests for System Collectors.
"""

import time
from lxad.core.ingestion import EventQueue
from lxad.collectors.metrics import MetricsCollector
from lxad.collectors.processes import ProcessCollector
from lxad.collectors.filewatch import FileWatchCollector
from lxad.collectors.network import NetworkCollector


def test_metrics_collector():
    q = EventQueue()
    col = MetricsCollector(queue=q, interval=0.5)
    col.start()
    assert col.is_alive()

    # Wait for at least one sample cycle
    time.sleep(1.2)
    col.stop()
    assert not col.is_alive()

    events = q.drain_batch(max_items=100)
    assert len(events) > 0
    metric_names = {e.metric_name for e in events}
    assert "cpu_percent" in metric_names
    assert "memory_percent" in metric_names


def test_process_collector():
    q = EventQueue()
    col = ProcessCollector(queue=q, interval=0.5)
    col.start()
    assert col.is_alive()

    time.sleep(1.2)
    col.stop()
    assert not col.is_alive()

    events = q.drain_batch(max_items=100)
    assert len(events) > 0
    assert any(e.source == "processes" for e in events)


def test_network_collector():
    q = EventQueue()
    col = NetworkCollector(queue=q, interval=0.5)
    col.start()
    assert col.is_alive()

    time.sleep(1.0)
    col.stop()
    assert not col.is_alive()

    events = q.drain_batch(max_items=100)
    assert len(events) > 0
    assert any(e.source == "network" for e in events)
