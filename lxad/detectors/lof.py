"""
Local Outlier Factor (LOF) Anomaly Detector for LXAD (Novelty Mode).

Measures the local deviation of density with respect to k-nearest neighbors.
Operates in novelty detection mode to score new streaming samples against a trained baseline.
"""

from __future__ import annotations

import collections
import logging
from typing import Any, Dict, List, Optional, Union
import numpy as np
from sklearn.neighbors import LocalOutlierFactor

logger = logging.getLogger(__name__)


class LOFDetector:
    """Density-based Local Outlier Factor novelty detector."""

    def __init__(
        self,
        n_neighbors: int = 15,
        contamination: float = 0.05,
        warmup_samples: int = 25,
        retrain_interval: int = 70
    ):
        self.n_neighbors = n_neighbors
        self.contamination = contamination
        self.warmup_samples = warmup_samples
        self.retrain_interval = retrain_interval

        self._model: Optional[LocalOutlierFactor] = None
        self._history: collections.deque[np.ndarray] = collections.deque(maxlen=150)
        self._samples_since_train = 0
        self._is_trained = False

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def fit(self, X: np.ndarray) -> None:
        """Fit LOF in novelty detection mode."""
        if len(X) <= self.n_neighbors:
            return
        self._model = LocalOutlierFactor(
            n_neighbors=min(self.n_neighbors, len(X) - 1),
            contamination=self.contamination,
            novelty=True,
            n_jobs=1
        )
        self._model.fit(X)
        self._is_trained = True
        self._samples_since_train = 0

    def detect(self, feature_vector: Union[List[float], np.ndarray], add_to_history: bool = True) -> Dict[str, Any]:
        """
        Score a single feature vector against local neighborhood density.
        """
        vec = np.asarray(feature_vector, dtype=np.float64).reshape(1, -1)

        if add_to_history:
            self._history.append(vec.ravel())
            self._samples_since_train += 1

        if not self._is_trained:
            if len(self._history) >= self.warmup_samples:
                X = np.array(self._history)
                self.fit(X)
            else:
                return {
                    "detector": "LOF",
                    "is_anomaly": False,
                    "score": 0.0,
                    "is_trained": False,
                    "samples_collected": len(self._history),
                    "warmup_needed": self.warmup_samples
                }
        elif self._samples_since_train >= self.retrain_interval:
            X = np.array(self._history)
            self.fit(X)

        if self._model is None or not self._is_trained:
            return {
                "detector": "LOF",
                "is_anomaly": False,
                "score": 0.0,
                "is_trained": False
            }

        decision = float(self._model.decision_function(vec)[0])
        pred = int(self._model.predict(vec)[0])  # -1 outlier, 1 inlier
        is_anomaly = bool(pred == -1 or decision < 0.0)

        # Map decision function to 0-1
        if decision >= 0.0:
            score = max(0.0, 0.5 - min(0.5, decision * 1.5))
        else:
            score = min(1.0, 0.5 + min(0.5, abs(decision) * 2.5))

        if is_anomaly:
            score = max(0.5, score)

        return {
            "detector": "LOF",
            "is_anomaly": is_anomaly,
            "score": float(round(score, 3)),
            "raw_score": float(round(decision, 4)),
            "is_trained": True
        }

    def reset(self) -> None:
        self._model = None
        self._history.clear()
        self._is_trained = False
        self._samples_since_train = 0
