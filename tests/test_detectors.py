"""
Tests for Anomaly Detectors (Z-score, EWMA, IQR, Isolation Forest, LOF, Ensemble).
"""

import numpy as np
import pytest

from lxad.detectors.zscore import ZScoreDetector
from lxad.detectors.ewma import EWMADetector
from lxad.detectors.iqr import IQRDetector
from lxad.detectors.iforest import IsolationForestDetector
from lxad.detectors.lof import LOFDetector
from lxad.detectors.ensemble import EnsembleDetector


def test_zscore_detector():
    det = ZScoreDetector(threshold=3.0)

    # Establish baseline around 25.0
    for v in [24.0, 26.0, 25.0, 25.5, 24.5, 25.0, 26.0, 24.8, 25.2, 25.0]:
        res = det.detect(v)
        assert not res["is_anomaly"]
        assert res["score"] < 0.5

    # Introduce extreme outlier (e.g. CPU 95.0%)
    spike = det.detect(95.0)
    assert spike["is_anomaly"]
    assert spike["z_score"] > 3.0
    assert spike["score"] >= 0.5


def test_ewma_detector():
    det = EWMADetector(alpha=0.3, L=3.0)

    # Stable baseline around 30.0
    for _ in range(20):
        det.detect(30.0)

    # Sudden step increase to 85.0
    res = det.detect(85.0)
    assert res["score"] > 0.0
    # Next sample at 95.0 should trigger EWMA anomaly
    res2 = det.detect(95.0)
    assert res2["is_anomaly"]


def test_iqr_detector():
    det = IQRDetector(multiplier=1.5)

    # Normal distribution values
    data = [20.0, 21.0, 19.5, 20.5, 22.0, 19.0, 21.5, 20.2, 19.8, 20.0, 21.0, 20.5]
    for d in data:
        det.detect(d)

    # Extreme value
    outlier = det.detect(85.0)
    assert outlier["is_anomaly"]
    assert outlier["score"] >= 0.5


def test_iforest_detector():
    det = IsolationForestDetector(warmup_samples=20)

    # Feed normal samples
    rng = np.random.default_rng(42)
    for _ in range(25):
        vec = rng.normal(loc=30.0, scale=2.0, size=(10,))
        det.detect(vec)

    assert det.is_trained

    # Outlier sample far from distribution
    outlier_vec = np.full((10,), 99.0)
    res = det.detect(outlier_vec)
    assert res["is_anomaly"]
    assert res["score"] >= 0.5


def test_lof_detector():
    det = LOFDetector(warmup_samples=20, n_neighbors=10)

    rng = np.random.default_rng(42)
    for _ in range(25):
        vec = rng.normal(loc=20.0, scale=1.5, size=(6,))
        det.detect(vec)

    assert det.is_trained

    # Outlier sample
    outlier_vec = np.full((6,), 150.0)
    res = det.detect(outlier_vec)
    assert res["is_anomaly"]
    assert res["score"] >= 0.5


def test_ensemble_detector():
    ens = EnsembleDetector()

    # Train baselines
    for _ in range(30):
        vec = np.full((13,), 25.0)
        ens.evaluate(primary_metric_val=25.0, feature_vector=vec)

    # Normal evaluation
    res_normal = ens.evaluate(primary_metric_val=25.0, feature_vector=np.full((13,), 25.0))
    assert not res_normal.is_anomaly
    assert res_normal.overall_score < 0.4

    # High anomaly evaluation (CPU 99.0)
    spike_vec = np.full((13,), 98.0)
    res_spike = ens.evaluate(primary_metric_val=98.0, feature_vector=spike_vec)
    assert res_spike.is_anomaly
    assert len(res_spike.detectors_fired) >= 2
    assert res_spike.overall_score >= 0.5
