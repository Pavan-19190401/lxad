"""
Exponentially Weighted Moving Average (EWMA) Control Chart Detector for LXAD.

Detects subtle continuous shifts and persistent drifts in time series metrics.
Default parameters: alpha=0.3, L=3.0.
"""

from __future__ import annotations

import collections
import math
from typing import Any, Dict, Optional


class EWMADetector:
    """EWMA statistical quality control chart detector."""

    def __init__(self, alpha: float = 0.3, L: float = 3.0, window_size: int = 40):
        self.alpha = float(alpha)
        self.L = float(L)
        self.window_size = max(5, window_size)

        self._ewma: Optional[float] = None
        self._t: int = 0
        self.history: collections.deque[float] = collections.deque(maxlen=self.window_size)

    def detect(self, value: float, add_to_history: bool = True) -> Dict[str, Any]:
        """
        Evaluate if current value causes EWMA statistic to breach control limits.
        """
        val = float(value)
        self._t += 1

        if self._ewma is None:
            self._ewma = val
            if add_to_history:
                self.history.append(val)
            return {
                "detector": "EWMA",
                "is_anomaly": False,
                "score": 0.0,
                "ewma_value": val,
                "ucl": val,
                "lcl": val,
                "alpha": self.alpha,
                "L": self.L
            }

        # Update EWMA smoothed statistic
        self._ewma = self.alpha * val + (1.0 - self.alpha) * self._ewma

        if len(self.history) < 5:
            if add_to_history:
                self.history.append(val)
            return {
                "detector": "EWMA",
                "is_anomaly": False,
                "score": 0.0,
                "ewma_value": float(round(self._ewma, 2)),
                "ucl": float(round(self._ewma, 2)),
                "lcl": float(round(self._ewma, 2)),
                "alpha": self.alpha,
                "L": self.L
            }

        # Baseline mean and standard deviation from history
        mean = sum(self.history) / len(self.history)
        variance = sum((x - mean) ** 2 for x in self.history) / (len(self.history) - 1)
        sigma = math.sqrt(max(1e-6, variance))

        # Time-varying standard deviation factor for EWMA
        factor = (self.alpha / (2.0 - self.alpha)) * (1.0 - (1.0 - self.alpha) ** (2 * self._t))
        sigma_ewma = sigma * math.sqrt(max(1e-6, factor))

        ucl = mean + self.L * sigma_ewma
        lcl = mean - self.L * sigma_ewma

        deviation = abs(self._ewma - mean)
        limit_spread = self.L * sigma_ewma
        is_anomaly = bool(self._ewma > ucl or self._ewma < lcl)

        # Normalized score
        ratio = deviation / max(1e-6, limit_spread)
        normalized_score = min(1.0, max(0.0, ratio * 0.5))
        if is_anomaly:
            normalized_score = min(1.0, 0.5 + 0.5 * (ratio - 1.0))

        if add_to_history and not is_anomaly:
            self.history.append(val)

        return {
            "detector": "EWMA",
            "is_anomaly": is_anomaly,
            "score": float(normalized_score),
            "ewma_value": float(round(self._ewma, 2)),
            "ucl": float(round(ucl, 2)),
            "lcl": float(round(lcl, 2)),
            "alpha": self.alpha,
            "L": self.L
        }

    def reset(self) -> None:
        self._ewma = None
        self._t = 0
        self.history.clear()
