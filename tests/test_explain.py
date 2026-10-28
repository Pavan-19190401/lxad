"""
Tests for Justification Generator (Phase 3).
"""

from lxad.detectors.ensemble import EnsembleResult
from lxad.scoring.scorer import AlertScoreResult
from lxad.explain.justification import JustificationGenerator


def test_justification_generator():
    generator = JustificationGenerator()

    ensemble_res = EnsembleResult(
        overall_score=0.85,
        is_anomaly=True,
        detectors_fired=["Z-score", "EWMA", "Isolation Forest"],
        detector_details={
            "zscore": {"is_anomaly": True, "z_score": 5.4},
            "ewma": {"is_anomaly": True, "ucl": 65.0},
            "iforest": {"is_anomaly": True}
        }
    )

    alert_res = AlertScoreResult(
        score=87.0,
        severity="High",
        stat_score=0.85,
        rule_score=0.9,
        is_alert=True,
        is_suppressed=False,
        module="CPU",
        anomaly_type="Runaway process",
        matched_rules=["R-001"],
        detectors_fired=["Z-score", "EWMA", "Isolation Forest"],
        remedial_actions=[
            "Inspect process 'xyz.exe' via Task Manager.",
            "Restart the service if unresponsive."
        ],
        rule_explanations=["Single process 'xyz.exe' used 88% CPU for 45 s."]
    )

    exp = generator.generate(
        alert_res=alert_res,
        ensemble_res=ensemble_res,
        primary_metric_name="cpu_percent",
        current_metric_val=96.0,
        baseline_metric_val=31.0
    )

    assert exp.score == 87.0
    assert exp.severity == "High"
    assert exp.affected_module == "CPU"
    assert "Z-score" in exp.detectors_fired
    assert "R-001" in exp.matched_rules
    assert len(exp.remedial_actions) == 2

    # Check key explanation elements in the plain English text
    text = exp.full_text
    assert "Score 87 (High)" in text
    assert "96.0" in text
    assert "31.0" in text
    assert "Rule R-001 matched" in text
    assert "xyz.exe" in text
    assert "Suggested actions:" in text
