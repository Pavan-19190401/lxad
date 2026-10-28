"""
Unified Alert Scoring Engine for LXAD.

Combines statistical ensemble deviations (0-1) and rule-based evaluation (0-1)
into a unified 0-100 alert score: S = 100 * (w_stat * S_stat + w_rule * S_rule).
Applies severity band categorization and alert cooldown/de-duplication to prevent alert fatigue.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from lxad.detectors.ensemble import EnsembleResult
from lxad.rules.engine import RuleMatch

logger = logging.getLogger(__name__)


@dataclass
class AlertScoreResult:
    """Consolidated scoring and alert assessment result."""
    score: float                         # 0.0 to 100.0
    severity: str                        # 'Low', 'Medium', 'High', 'Critical'
    stat_score: float                    # 0.0 to 1.0
    rule_score: float                    # 0.0 to 1.0
    is_alert: bool                       # True if score >= threshold and not suppressed
    is_suppressed: bool                  # True if alert cooldown suppressed this occurrence
    module: str
    anomaly_type: str
    matched_rules: List[str] = field(default_factory=list)
    detectors_fired: List[str] = field(default_factory=list)
    remedial_actions: List[str] = field(default_factory=list)
    rule_explanations: List[str] = field(default_factory=list)


class AlertScorer:
    """Computes final composite alert score with cooldown management."""

    def __init__(
        self,
        w_stat: float = 0.5,
        w_rule: float = 0.5,
        alert_threshold: float = 40.0,
        cooldown_seconds: float = 30.0
    ):
        self.w_stat = float(w_stat)
        self.w_rule = float(w_rule)
        self.alert_threshold = float(alert_threshold)
        self.cooldown_seconds = float(cooldown_seconds)

        # Alert history for de-duplication: (module, anomaly_type) -> (timestamp, score, severity)
        self._cooldown_cache: Dict[Tuple[str, str], Tuple[float, float, str]] = {}

    def score(
        self,
        ensemble_res: EnsembleResult,
        rule_matches: List[RuleMatch],
        default_module: str = "System"
    ) -> AlertScoreResult:
        """
        Compute unified 0-100 score and determine alert publication status.
        """
        stat_s = ensemble_res.overall_score

        # Rule score calculation: highest matched rule score with bonus for multiple matching rules
        if rule_matches:
            max_rule = max(m.score for m in rule_matches)
            multi_rule_bonus = min(0.15, 0.05 * (len(rule_matches) - 1))
            rule_s = min(1.0, max_rule + multi_rule_bonus)
            primary_match = max(rule_matches, key=lambda m: m.score)
            module = primary_match.module
            anomaly_type = primary_match.anomaly_type
        else:
            rule_s = 0.0
            module = default_module
            anomaly_type = "Statistical Anomaly" if ensemble_res.is_anomaly else "Normal Activity"

        # If only stats fired without rules, balance weights gracefully
        if not rule_matches and stat_s > 0:
            # When no rules match, statistical score contributes its proportional weight
            composite = 100.0 * (self.w_stat * stat_s)
        elif rule_matches and stat_s == 0:
            composite = 100.0 * (self.w_rule * rule_s)
        else:
            composite = 100.0 * (self.w_stat * stat_s + self.w_rule * rule_s)

        final_score = float(round(min(100.0, max(0.0, composite)), 1))

        # Classify severity band:
        # 0-39: Low, 40-69: Medium, 70-89: High, 90-100: Critical
        if final_score >= 90.0:
            severity = "Critical"
        elif final_score >= 70.0:
            severity = "High"
        elif final_score >= 40.0:
            severity = "Medium"
        else:
            severity = "Low"

        # Check alert triggering and cooldown
        is_candidate = (final_score >= self.alert_threshold)
        is_suppressed = False

        if is_candidate:
            key = (module, anomaly_type)
            now = time.time()
            if key in self._cooldown_cache:
                last_ts, last_score, last_sev = self._cooldown_cache[key]
                time_diff = now - last_ts
                # Suppress if within cooldown, unless score escalates significantly (+15 points or higher band)
                score_escalated = (final_score >= last_score + 15.0) or (severity == "Critical" and last_sev != "Critical")
                if time_diff < self.cooldown_seconds and not score_escalated:
                    is_suppressed = True
                else:
                    self._cooldown_cache[key] = (now, final_score, severity)
            else:
                self._cooldown_cache[key] = (now, final_score, severity)

        # Aggregate actions and explanations
        actions: List[str] = []
        explanations: List[str] = []
        matched_rule_ids: List[str] = []

        for m in rule_matches:
            matched_rule_ids.append(m.rule_id)
            explanations.append(m.explanation)
            for act in m.remedial_actions:
                if act not in actions:
                    actions.append(act)

        # Fallback action if none provided
        if not actions and is_candidate:
            actions.append("Review background processes and system load logs.")

        return AlertScoreResult(
            score=final_score,
            severity=severity,
            stat_score=float(round(stat_s, 3)),
            rule_score=float(round(rule_s, 3)),
            is_alert=bool(is_candidate and not is_suppressed),
            is_suppressed=is_suppressed,
            module=module,
            anomaly_type=anomaly_type,
            matched_rules=matched_rule_ids,
            detectors_fired=list(ensemble_res.detectors_fired),
            remedial_actions=actions,
            rule_explanations=explanations
        )

    def reset_cooldown(self) -> None:
        """Clear the cooldown cache."""
        self._cooldown_cache.clear()
