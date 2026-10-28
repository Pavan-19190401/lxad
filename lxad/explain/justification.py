"""
Explainability and Justification Generator for LXAD.

Transforms statistical deviations, model outputs, and rule matches into coherent,
human-readable plain English justifications with specific remedial recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lxad.detectors.ensemble import EnsembleResult
from lxad.scoring.scorer import AlertScoreResult


@dataclass
class ExplanationDetail:
    """Structured breakdown of an anomaly justification."""
    headline: str
    full_text: str
    affected_module: str
    severity: str
    score: float
    detectors_fired: List[str]
    matched_rules: List[str]
    remedial_actions: List[str]
    metric_deviations: Dict[str, Any] = field(default_factory=dict)


class JustificationGenerator:
    """Generates transparent, auditable natural language explanations for alerts."""

    def generate(
        self,
        alert_res: AlertScoreResult,
        ensemble_res: EnsembleResult,
        primary_metric_name: str = "cpu_percent",
        current_metric_val: float = 0.0,
        baseline_metric_val: float = 0.0,
        extra_context: Optional[Dict[str, Any]] = None
    ) -> ExplanationDetail:
        """
        Synthesize plain-English root-cause justification for an alert.
        """
        ctx = extra_context or {}
        score = alert_res.score
        severity = alert_res.severity
        module = alert_res.module
        anomaly_type = alert_res.anomaly_type

        # 1. Headline summary
        headline = f"Score {score:.0f} ({severity}): {anomaly_type} detected on {module} subsystem"

        # 2. Statistical evidence segment
        fired_str = ", ".join(ensemble_res.detectors_fired) if ensemble_res.detectors_fired else "No statistical detectors"
        stat_evidence = []

        z_detail = ensemble_res.detector_details.get("zscore")
        if z_detail and z_detail.get("is_anomaly"):
            z_val = z_detail.get("z_score", 0.0)
            stat_evidence.append(f"Z-score={z_val:.1f}")

        ewma_detail = ensemble_res.detector_details.get("ewma")
        if ewma_detail and ewma_detail.get("is_anomaly"):
            ucl = ewma_detail.get("ucl", 0.0)
            stat_evidence.append(f"breached EWMA UCL ({ucl:.1f})")

        iqr_detail = ensemble_res.detector_details.get("iqr")
        if iqr_detail and iqr_detail.get("is_anomaly"):
            upper_fence = iqr_detail.get("upper_fence", 0.0)
            stat_evidence.append(f"exceeded IQR upper fence ({upper_fence:.1f})")

        if_detail = ensemble_res.detector_details.get("iforest")
        if if_detail and if_detail.get("is_anomaly"):
            stat_evidence.append("Isolation Forest density shift")

        lof_detail = ensemble_res.detector_details.get("lof")
        if lof_detail and lof_detail.get("is_anomaly"):
            stat_evidence.append("LOF local outlier")

        evidence_str = f" ({', '.join(stat_evidence)})" if stat_evidence else ""

        # Build metric context sentence
        metric_sentence = (
            f"{primary_metric_name.replace('_', ' ').title()} recorded at {current_metric_val:.1f} "
            f"(baseline ~{baseline_metric_val:.1f}{evidence_str}, flagged by {fired_str})."
        )

        # 3. Rule matching segment
        if alert_res.rule_explanations:
            rule_text = " ".join(
                f"Rule {r_id} matched: {exp}"
                for r_id, exp in zip(alert_res.matched_rules, alert_res.rule_explanations)
            )
        elif alert_res.matched_rules:
            rule_text = f"Triggered rules: {', '.join(alert_res.matched_rules)}."
        else:
            rule_text = "No deterministic policy rules violated; flagged via multivariate statistical deviation."

        # 4. Remedial actions segment
        if alert_res.remedial_actions:
            actions_formatted = " Suggested actions: " + " ".join(
                f"({i+1}) {act}" for i, act in enumerate(alert_res.remedial_actions)
            )
        else:
            actions_formatted = " Suggested actions: Inspect system processes and active resource consumption."

        # Full plain English narrative
        full_text = f"Score {score:.0f} ({severity}): {metric_sentence} {rule_text}{actions_formatted}"

        metric_deviations = {
            "metric": primary_metric_name,
            "current_value": current_metric_val,
            "baseline_value": baseline_metric_val,
            "stat_score": alert_res.stat_score,
            "rule_score": alert_res.rule_score,
        }

        return ExplanationDetail(
            headline=headline,
            full_text=full_text,
            affected_module=module,
            severity=severity,
            score=score,
            detectors_fired=list(ensemble_res.detectors_fired),
            matched_rules=list(alert_res.matched_rules),
            remedial_actions=list(alert_res.remedial_actions),
            metric_deviations=metric_deviations
        )
