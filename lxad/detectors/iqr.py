"""
Interquartile Range (IQR) Fence Anomaly Detector for LXAD.

Non-parametric robust detector resilient to skewed and non-normal metric distributions.
Computes Q1, Q3, and flags values beyond [Q1 - 1.5*IQR, Q3 + 1.5*IQR].
"""

from __future__ import annotations

import collections
from typing import Any, Dict, List, Optional
import numpy as np


class IQRDetector:
    """Non-parametric IQR fence detector."""

    def __init__(self, multiplier: float = 1.5, window_size: int = 40):
        self.multiplier = float(multiplier)
        self.window_size = max(10, window_size)
        self.history: collections.deque[float] = collections.deque(maxlen=self.window_size)

    def detect(self, value: float, add_to_history: bool = True) -> Dict[str, Any]:
        """Evaluate if value falls outside the IQR fence."""
        val = float(value)
        if len(self.history) < 8:
            if add_to_history:
                self.history.append(val)
            return {
                "detector": "IQR",
                "is_anomaly": False,
                "score": 0.0,
                "q1": val,
                "q3": val,
                "iqr": 0.0,
                "lower_fence": val,
                "upper_fence": val
            }

        arr = np.array(self.history, dtype=np.float64)
        q1 = float(np.percentile(arr, 25))
        q3 = float(np.percentile(arr, 75))
        iqr = max(1e-6, q3 - q1)

        lower_fence = q1 - self.multiplier * iqr
        upper_fence = q3 + self.multiplier * iqr

        is_anomaly = bool(val < lower_fence or val > upper_fence)

        # Deviation distance beyond fence
        if val > upper_fence:
            dist = (val - upper_fence) / iqr
            normalized_score = min(1.0, 0.5 + 0.5 * min(1.0, dist / 2.0))
        elif val < lower_fence:
            dist = (lower_fence - val) / iqr
            normalized_score = min(1.0, 0.5 + 0.5 * min(1.0, dist / 2.0))
        else:
            # Inside fence: distance from median
            median = float(np.median(arr))
            dist = abs(val - median) / (iqr * self.multiplier)
            normalized_score = min(0.49, dist * 0.49)

        if add_to_history and not is_anomaly:
            self.history.append(val)

        return {
            "detector": "IQR",
            "is_anomaly": is_anomaly,
            "score": float(normalized_score),
            "q1": float(round(q1, 2)),
            "q3": float(round(q3, 2)),
            "iqr": float(round(iqr, 2)),
            "lower_fence": float(round(lower_fence, 2)),
            "upper_fence": float(round(upper_fence, 2))
        }

    def reset(self) -> None:
        self.history.clear()
