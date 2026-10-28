"""
Ensemble Anomaly Detector for LXAD.

Combines outputs from statistical detectors (Z-Score, EWMA, IQR) and machine learning
detectors (Isolation Forest, LOF) into a unified normalized statistical score [0.0 - 1.0],
recording which detectors triggered an alarm for explainability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from lxad.detectors.zscore import ZScoreDetector
from lxad.detectors.ewma import EWMADetector
from lxad.detectors.iqr import IQRDetector
from lxad.detectors.iforest import IsolationForestDetector
from lxad.detectors.lof import LOFDetector


@dataclass
class EnsembleResult:
    """Aggregated output from all active anomaly detectors."""
    overall_score: float = 0.0          # Normalized 0.0 to 1.0
    is_anomaly: bool = False
    detectors_fired: List[str] = field(default_factory=list)
    detector_scores: Dict[str, float] = field(default_factory=dict)
    detector_details: Dict[str, Any] = field(default_factory=dict)


class EnsembleDetector:
    """Orchestrates and fuses multi-algorithm anomaly detection."""

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        # Default weights summing to 1.0
        self.weights = weights or {
            "zscore": 0.25,
            "ewma": 0.20,
            "iqr": 0.20,
            "iforest": 0.20,
            "lof": 0.15
        }

        # Active detector toggles
        self.enabled = {
            "zscore": True,
            "ewma": True,
            "iqr": True,
            "iforest": True,
            "lof": True
        }

        # Sub-detectors
        self.zscore = ZScoreDetector()
        self.ewma = EWMADetector()
        self.iqr = IQRDetector()
        self.iforest = IsolationForestDetector()
        self.lof = LOFDetector()

    def set_enabled(self, name: str, is_enabled: bool) -> None:
        if name in self.enabled:
            self.enabled[name] = bool(is_enabled)

    def set_weight(self, name: str, weight: float) -> None:
        if name in self.weights:
            self.weights[name] = max(0.0, float(weight))

    def evaluate(
        self,
        primary_metric_val: float,
        feature_vector: np.ndarray,
        add_to_history: bool = True
    ) -> EnsembleResult:
        """
        Run all enabled detectors and synthesize the ensemble score.
        """
        scores: Dict[str, float] = {}
        details: Dict[str, Any] = {}
        fired: List[str] = []

        # 1. Z-Score
        if self.enabled.get("zscore"):
            res = self.zscore.detect(primary_metric_val, add_to_history=add_to_history)
            scores["zscore"] = res["score"]
            details["zscore"] = res
            if res["is_anomaly"]:
                fired.append("Z-score")

        # 2. EWMA
        if self.enabled.get("ewma"):
            res = self.ewma.detect(primary_metric_val, add_to_history=add_to_history)
            scores["ewma"] = res["score"]
            details["ewma"] = res
            if res["is_anomaly"]:
                fired.append("EWMA")

        # 3. IQR
        if self.enabled.get("iqr"):
            res = self.iqr.detect(primary_metric_val, add_to_history=add_to_history)
            scores["iqr"] = res["score"]
            details["iqr"] = res
            if res["is_anomaly"]:
                fired.append("IQR")

        # 4. Isolation Forest
        if self.enabled.get("iforest"):
            res = self.iforest.detect(feature_vector, add_to_history=add_to_history)
            scores["iforest"] = res["score"]
            details["iforest"] = res
            if res["is_anomaly"]:
                fired.append("Isolation Forest")

        # 5. LOF
        if self.enabled.get("lof"):
            res = self.lof.detect(feature_vector, add_to_history=add_to_history)
            scores["lof"] = res["score"]
            details["lof"] = res
            if res["is_anomaly"]:
                fired.append("LOF")

        # Calculate weighted average score
        total_weight = 0.0
        weighted_sum = 0.0
        for name, score in scores.items():
            w = self.weights.get(name, 0.2)
            weighted_sum += score * w
            total_weight += w

        overall = (weighted_sum / total_weight) if total_weight > 0 else 0.0
        is_anomaly = bool(len(fired) >= 2 or overall >= 0.5)

        return EnsembleResult(
            overall_score=float(round(overall, 4)),
            is_anomaly=is_anomaly,
            detectors_fired=fired,
            detector_scores=scores,
            detector_details=details
        )

    def reset_all(self) -> None:
        self.zscore.reset()
        self.ewma.reset()
        self.iqr.reset()
        self.iforest.reset()
        self.lof.reset()
