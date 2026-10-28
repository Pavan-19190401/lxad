"""
Tests for Rule Engine and rules.yaml (Phase 3).
"""

import time
from lxad.core.preprocessing import WindowFeatures
from lxad.rules.engine import RuleEngine, RuleMatch


def test_rule_loading():
    engine = RuleEngine()
    assert len(engine.rules) >= 5
    rule_ids = [r["id"] for r in engine.rules]
    assert "R-001" in rule_ids
    assert "R-002" in rule_ids
    assert "R-003" in rule_ids


def test_runaway_process_rule():
    engine = RuleEngine()
    now = time.time()

    wf = WindowFeatures(
        start_time=now - 10,
        end_time=now,
        duration=10.0,
        metric_stats={"cpu_percent": {"mean": 92.0, "max": 96.0, "min": 88.0, "std": 2.0, "roc": 0.0, "count": 10, "last": 92.0}},
        top_processes=[{"pid": 4512, "name": "stress_worker.exe", "cpu": 88.5, "mem": 12.0}]
    )

    matches = engine.evaluate(wf, baseline_metrics={"cpu_percent": 30.0})
    r1_match = next((m for m in matches if m.rule_id == "R-001"), None)
    assert r1_match is not None
    assert r1_match.anomaly_type == "Runaway process"
    assert "stress_worker.exe" in r1_match.explanation
    assert len(r1_match.remedial_actions) > 0


def test_error_storm_rule():
    engine = RuleEngine()
    now = time.time()

    wf = WindowFeatures(
        start_time=now - 10,
        end_time=now,
        duration=10.0,
        error_count=8
    )

    matches = engine.evaluate(wf)
    r3_match = next((m for m in matches if m.rule_id == "R-003"), None)
    assert r3_match is not None
    assert r3_match.anomaly_type == "Error storm"
    assert "8 system/application error" in r3_match.explanation


def test_failed_logon_brute_force_rule():
    engine = RuleEngine()
    now = time.time()

    wf = WindowFeatures(
        start_time=now - 10,
        end_time=now,
        duration=10.0,
        security_failed_logon_count=6
    )

    matches = engine.evaluate(wf)
    r4_match = next((m for m in matches if m.rule_id == "R-004"), None)
    assert r4_match is not None
    assert r4_match.severity == "Critical"
    assert "6 failed logon" in r4_match.explanation
