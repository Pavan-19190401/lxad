"""
End-to-End Pipeline Integration Test for LXAD.

Validates the full chain:
Telemetry Ingestion -> Storage -> Preprocessing -> Detection -> Rules -> Scoring -> Justification -> Persistence.
"""

import os
import tempfile
import time
import pytest

from lxad.core.ingestion import EventQueue, TelemetryEvent
from lxad.core.storage import RingBuffer, SQLiteStorage
from lxad.core.preprocessing import PreprocessingPipeline
from lxad.detectors.ensemble import EnsembleDetector
from lxad.rules.engine import RuleEngine
from lxad.scoring.scorer import AlertScorer
from lxad.explain.justification import JustificationGenerator


def test_end_to_end_pipeline():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "e2e_lxad.db")

        # 1. Initialize pipeline components
        queue = EventQueue()
        buffer = RingBuffer(capacity=1000, max_age_seconds=60.0)
        storage = SQLiteStorage(db_path=db_path)
        preprocessing = PreprocessingPipeline(window_size_seconds=10.0)
        ensemble = EnsembleDetector()
        rule_engine = RuleEngine()
        scorer = AlertScorer(w_stat=0.5, w_rule=0.5, alert_threshold=40.0)
        justification_gen = JustificationGenerator()

        now = time.time()

        # 2. Warm up baseline with normal samples
        for i in range(25):
            ev_cpu = TelemetryEvent(
                timestamp=now - 50 + i,
                source="metrics",
                module="CPU",
                type="metric",
                metric_name="cpu_percent",
                value=25.0 + (i % 3)
            )
            buffer.append(ev_cpu)
            # Evaluate to warm up detector baselines
            wf = preprocessing.process_window([ev_cpu])
            vec = wf.to_vector()
            ensemble.evaluate(primary_metric_val=25.0, feature_vector=vec, add_to_history=True)

        # 3. Ingest severe runaway anomaly events into queue
        spike_time = now
        queue.push(TelemetryEvent(
            timestamp=spike_time,
            source="metrics",
            module="CPU",
            type="metric",
            metric_name="cpu_percent",
            value=97.5,
            severity_level="WARNING"
        ))
        queue.push(TelemetryEvent(
            timestamp=spike_time,
            source="processes",
            module="Process",
            type="process_top",
            metric_name="top_process_cpu",
            value=92.0,
            details={"top_cpu": [{"pid": 9999, "name": "rogue_miner.exe", "cpu": 92.5, "mem": 18.0, "exe": "C:\\rogue_miner.exe"}]}
        ))

        # 4. Drain queue to buffer
        batch = queue.drain_batch(max_items=10)
        buffer.extend(batch)

        # 5. Preprocess window
        window_events = buffer.get_recent(seconds=10.0)
        wf = preprocessing.process_window(window_events, start_ts=now - 10.0, end_ts=now)
        assert wf.get_metric("cpu_percent", "mean") > 50.0

        # 6. Ensemble detection
        vec = wf.to_vector()
        ens_res = ensemble.evaluate(
            primary_metric_val=wf.get_metric("cpu_percent", "mean"),
            feature_vector=vec,
            add_to_history=False
        )
        assert ens_res.is_anomaly
        assert len(ens_res.detectors_fired) >= 2

        # 7. Rule evaluation
        rule_matches = rule_engine.evaluate(wf, baseline_metrics={"cpu_percent": 26.0})
        assert len(rule_matches) >= 1
        assert rule_matches[0].rule_id == "R-001"
        assert "rogue_miner.exe" in rule_matches[0].explanation

        # 8. Composite Scoring
        alert_res = scorer.score(ens_res, rule_matches)
        assert alert_res.is_alert
        assert alert_res.score >= 70.0  # High or Critical
        assert alert_res.severity in ("High", "Critical")

        # 9. Justification generation
        exp = justification_gen.generate(
            alert_res=alert_res,
            ensemble_res=ens_res,
            primary_metric_name="cpu_percent",
            current_metric_val=wf.get_metric("cpu_percent", "mean"),
            baseline_metric_val=26.0
        )
        assert "Score" in exp.full_text
        assert "rogue_miner.exe" in exp.full_text
        assert len(exp.remedial_actions) > 0

        # 10. Persistence
        alert_id = storage.save_alert(
            score=alert_res.score,
            severity=alert_res.severity,
            module=alert_res.module,
            anomaly_type=alert_res.anomaly_type,
            justification=exp.full_text,
            detectors_fired=alert_res.detectors_fired,
            matched_rules=alert_res.matched_rules,
            metrics={"cpu_percent": 97.5},
            remedial_actions=alert_res.remedial_actions,
            timestamp=spike_time
        )
        assert alert_id > 0

        # Query back and verify integrity
        saved_alerts = storage.get_alerts(min_score=50.0)
        assert len(saved_alerts) == 1
        stored = saved_alerts[0]
        assert stored["anomaly_type"] == "Runaway process"
        assert "rogue_miner.exe" in stored["justification"]
        assert "R-001" in stored["matched_rules"]

        storage.close()
