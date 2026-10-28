"""
Isolation Forest Machine Learning Anomaly Detector for LXAD.

Unsupervised multi-attribute tree ensemble isolating anomalies in feature space.
Supports initial warm-up baseline training and continuous periodic refitting.
"""

from __future__ import annotations

import collections
import logging
from typing import Any, Dict, List, Optional, Union
import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)


class IsolationForestDetector:
    """Multivariate tree-based isolation anomaly detector."""

    def __init__(
        self,
        contamination: float = 0.05,
        n_estimators: int = 30,
        warmup_samples: int = 25,
        retrain_interval: int = 60,
        random_state: int = 42
    ):
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.warmup_samples = warmup_samples
        self.retrain_interval = retrain_interval
        self.random_state = random_state

        self._model: Optional[IsolationForest] = None
        self._history: collections.deque[np.ndarray] = collections.deque(maxlen=150)
        self._samples_since_train = 0
        self._is_trained = False

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def fit(self, X: np.ndarray) -> None:
        """Fit Isolation Forest on historical matrix X (n_samples, n_features)."""
        if len(X) < 10:
            return
        self._model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=1
        )
        self._model.fit(X)
        self._is_trained = True
        self._samples_since_train = 0

    def detect(self, feature_vector: Union[List[float], np.ndarray], add_to_history: bool = True) -> Dict[str, Any]:
        """
        Evaluate multivariate feature vector.
        Returns:
            dict with is_anomaly (bool), score (0.0-1.0), raw_score (float), is_trained (bool).
        """
        vec = np.asarray(feature_vector, dtype=np.float64).reshape(1, -1)

        if add_to_history:
            self._history.append(vec.ravel())
            self._samples_since_train += 1

        # Train if warmup threshold is reached or periodic retrain interval hits
        if not self._is_trained:
            if len(self._history) >= self.warmup_samples:
                X = np.array(self._history)
                self.fit(X)
            else:
                return {
                    "detector": "Isolation Forest",
                    "is_anomaly": False,
                    "score": 0.0,
                    "raw_score": 0.0,
                    "is_trained": False,
                    "samples_collected": len(self._history),
                    "warmup_needed": self.warmup_samples
                }
        elif self._samples_since_train >= self.retrain_interval:
            X = np.array(self._history)
            self.fit(X)

        if self._model is None or not self._is_trained:
            return {
                "detector": "Isolation Forest",
                "is_anomaly": False,
                "score": 0.0,
                "raw_score": 0.0,
                "is_trained": False
            }

        # score_samples returns opposite of anomaly score (lower means more anomalous)
        # Typically values around 0.5 are normal, < 0.35 are anomalous
        decision = float(self._model.decision_function(vec)[0])
        pred = int(self._model.predict(vec)[0])  # -1 for anomaly, 1 for inlier
        is_anomaly = bool(pred == -1 or decision < 0.0)

        # Normalize decision to 0-1 score
        # decision is > 0 for inliers, < 0 for outliers
        if decision >= 0.0:
            score = max(0.0, 0.5 - min(0.5, decision * 2.0))
        else:
            score = min(1.0, 0.5 + min(0.5, abs(decision) * 3.0))

        if is_anomaly:
            score = max(0.5, score)

        return {
            "detector": "Isolation Forest",
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
