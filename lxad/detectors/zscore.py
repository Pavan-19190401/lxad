"""
Rolling Z-score Anomaly Detector for LXAD.

Maintains a moving window of recent metric values to establish baseline mean
and standard deviation, evaluating current deviation against a configurable threshold.
"""

from __future__ import annotations

import collections
import math
from typing import Any, Dict, List, Optional


class ZScoreDetector:
    """Statistical detector identifying standard deviation outliers."""

    def __init__(self, threshold: float = 3.0, window_size: int = 30):
        self.threshold = threshold
        self.window_size = max(5, window_size)
        self.history: collections.deque[float] = collections.deque(maxlen=self.window_size)

    def update_baseline(self, value: float) -> None:
        """Add normal sample to rolling history."""
        self.history.append(float(value))

    def detect(self, value: float, add_to_history: bool = True) -> Dict[str, Any]:
        """
        Evaluate if value is an anomaly.
        Returns:
            dict containing is_anomaly (bool), score (0.0-1.0), z_score (float),
            mean (float), std (float), threshold (float).
        """
        val = float(value)
        if len(self.history) < 5:
            if add_to_history:
                self.history.append(val)
            return {
                "detector": "Z-score",
                "is_anomaly": False,
                "score": 0.0,
                "z_score": 0.0,
                "mean": val,
                "std": 0.0,
                "threshold": self.threshold
            }

        mean = sum(self.history) / len(self.history)
        variance = sum((x - mean) ** 2 for x in self.history) / (len(self.history) - 1)
        std = math.sqrt(max(1e-6, variance))

        z = abs(val - mean) / std
        is_anomaly = bool(z >= self.threshold)

        # Map Z to a smooth 0-1 score: 0 at z=0, 0.5 at threshold, approaching 1.0 above threshold
        normalized_score = min(1.0, max(0.0, z / (self.threshold * 2.0)))
        if is_anomaly:
            normalized_score = max(0.5, normalized_score)

        if add_to_history and not is_anomaly:
            # Don't contaminate baseline with severe outliers
            self.history.append(val)

        return {
            "detector": "Z-score",
            "is_anomaly": is_anomaly,
            "score": float(normalized_score),
            "z_score": float(round(z, 2)),
            "mean": float(round(mean, 2)),
            "std": float(round(std, 2)),
            "threshold": self.threshold
        }

    def reset(self) -> None:
        self.history.clear()
