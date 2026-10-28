"""
Tests for Alert Scorer and Cooldown De-duplication (Phase 3).
"""

import time
from lxad.detectors.ensemble import EnsembleResult
from lxad.rules.engine import RuleMatch
from lxad.scoring.scorer import AlertScorer


def test_scoring_formula():
    scorer = AlertScorer(w_stat=0.5, w_rule=0.5)

    ens = EnsembleResult(
        overall_score=0.8,
        is_anomaly=True,
        detectors_fired=["Z-score", "EWMA"]
    )

    matches = [
        RuleMatch(
            rule_id="R-001",
            rule_name="Runaway Process",
            module="CPU",
            anomaly_type="Runaway process",
            severity="High",
            score=0.9,
            explanation="CPU 95%",
            remedial_actions=["Inspect PID"]
        )
    ]

    res = scorer.score(ens, matches)
    # composite = 100 * (0.5 * 0.8 + 0.5 * 0.9) = 100 * (0.4 + 0.45) = 85.0
    assert 84.0 <= res.score <= 86.0
    assert res.severity == "High"
    assert res.is_alert
    assert not res.is_suppressed
    assert "R-001" in res.matched_rules
    assert "Z-score" in res.detectors_fired


def test_cooldown_deduplication():
    scorer = AlertScorer(cooldown_seconds=10.0)

    ens = EnsembleResult(overall_score=0.7, is_anomaly=True)
    match = RuleMatch(
        rule_id="R-003",
        rule_name="Error storm",
        module="SystemLog",
        anomaly_type="Error storm",
        severity="High",
        score=0.8,
        explanation="Errors",
        remedial_actions=["Check logs"]
    )

    # First alert should trigger
    res1 = scorer.score(ens, [match])
    assert res1.is_alert
    assert not res1.is_suppressed

    # Immediate second identical alert should be suppressed by cooldown
    res2 = scorer.score(ens, [match])
    assert res2.is_suppressed
    assert not res2.is_alert

    # Score escalation should bypass cooldown
    high_ens = EnsembleResult(overall_score=1.0, is_anomaly=True)
    high_match = RuleMatch(
        rule_id="R-003",
        rule_name="Error storm",
        module="SystemLog",
        anomaly_type="Error storm",
        severity="Critical",
        score=1.0,
        explanation="Massive errors",
        remedial_actions=["Check logs"]
    )
    res3 = scorer.score(high_ens, [high_match])
    assert res3.is_alert
    assert not res3.is_suppressed
