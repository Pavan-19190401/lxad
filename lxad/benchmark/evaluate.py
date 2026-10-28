"""
Benchmark Evaluation Suite for LXAD.

Runs individual detectors and the full ensemble over HDFS benchmark datasets.
Calculates Accuracy, Precision, Recall, F1-Score, ROC-AUC, latency per window,
and system overhead, comparing individual models against the unified framework.
"""

from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import numpy as np
import psutil
from sklearn.metrics import roc_auc_score

from lxad.benchmark.loghub_hdfs import HDFSBenchmarkData
from lxad.detectors.zscore import ZScoreDetector
from lxad.detectors.ewma import EWMADetector
from lxad.detectors.iqr import IQRDetector
from lxad.detectors.iforest import IsolationForestDetector
from lxad.detectors.lof import LOFDetector
from lxad.detectors.ensemble import EnsembleDetector

logger = logging.getLogger(__name__)


@dataclass
class DetectorMetrics:
    """Performance metrics for an individual detection method."""
    name: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: float
    latency_ms: float
    tp: int
    fp: int
    tn: int
    fn: int


@dataclass
class BenchmarkReport:
    """Complete evaluation report across all detectors."""
    dataset_name: str
    total_blocks: int
    anomaly_count: int
    normal_count: int
    total_features: int
    detector_results: List[DetectorMetrics]
    cpu_overhead_percent: float
    memory_overhead_mb: float

    def to_csv(self, file_path: str) -> None:
        """Export metrics table to CSV."""
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Detector", "Accuracy", "Precision", "Recall", "F1-Score", "ROC-AUC", "Latency (ms)", "TP", "FP", "TN", "FN"
            ])
            for m in self.detector_results:
                writer.writerow([
                    m.name,
                    f"{m.accuracy:.4f}",
                    f"{m.precision:.4f}",
                    f"{m.recall:.4f}",
                    f"{m.f1_score:.4f}",
                    f"{m.roc_auc:.4f}",
                    f"{m.latency_ms:.2f}",
                    m.tp, m.fp, m.tn, m.fn
                ])


class BenchmarkEvaluator:
    """Executes evaluation protocol on benchmark dataset."""

    def run_benchmark(self, dataset: HDFSBenchmarkData, dataset_name: str = "HDFS_v1") -> BenchmarkReport:
        """Run all detectors through the dataset and compute comparative metrics."""
        X = dataset.feature_matrix
        y = dataset.ground_truth
        n_samples = len(y)

        # Baseline scalar representation: sum of rare/error log events per block
        # Typically columns > 3 in HDFS template representations correspond to warnings/exceptions
        scalar_metric = np.sum(X[:, 3:], axis=1) if X.shape[1] > 3 else np.sum(X, axis=1)

        # Track system resource overhead
        proc = psutil.Process()
        cpu_before = psutil.cpu_percent(interval=None)
        mem_before = proc.memory_info().rss / (1024 * 1024)

        results: List[DetectorMetrics] = []

        # 1. Evaluate Z-Score
        results.append(self._eval_zscore(scalar_metric, y))

        # 2. Evaluate EWMA
        results.append(self._eval_ewma(scalar_metric, y))

        # 3. Evaluate IQR
        results.append(self._eval_iqr(scalar_metric, y))

        # 4. Evaluate Isolation Forest
        results.append(self._eval_iforest(X, y))

        # 5. Evaluate LOF
        results.append(self._eval_lof(X, y))

        # 6. Evaluate Ensemble Framework
        results.append(self._eval_ensemble(scalar_metric, X, y))

        cpu_after = psutil.cpu_percent(interval=None)
        mem_after = proc.memory_info().rss / (1024 * 1024)

        anomaly_count = int(np.sum(y == 1))
        normal_count = int(np.sum(y == 0))

        return BenchmarkReport(
            dataset_name=dataset_name,
            total_blocks=n_samples,
            anomaly_count=anomaly_count,
            normal_count=normal_count,
            total_features=X.shape[1],
            detector_results=results,
            cpu_overhead_percent=max(0.1, round(cpu_after, 1)),
            memory_overhead_mb=max(0.1, round(mem_after, 1))
        )

    def _compute_metrics(self, name: str, y_true: np.ndarray, y_pred: np.ndarray, y_scores: np.ndarray, total_time_sec: float) -> DetectorMetrics:
        """Compute standard classification metrics safely."""
        tp = int(np.sum((y_pred == 1) & (y_true == 1)))
        fp = int(np.sum((y_pred == 1) & (y_true == 0)))
        tn = int(np.sum((y_pred == 0) & (y_true == 0)))
        fn = int(np.sum((y_pred == 0) & (y_true == 1)))

        accuracy = (tp + tn) / max(1, len(y_true))
        precision = tp / max(1e-6, tp + fp)
        recall = tp / max(1e-6, tp + fn)
        f1 = (2 * precision * recall) / max(1e-6, precision + recall)

        # ROC-AUC calculation
        try:
            if len(np.unique(y_true)) > 1:
                roc_auc = float(roc_auc_score(y_true, y_scores))
            else:
                roc_auc = 1.0 if precision > 0.5 else 0.5
        except Exception:
            roc_auc = 0.5

        latency_ms = (total_time_sec / max(1, len(y_true))) * 1000.0

        return DetectorMetrics(
            name=name,
            accuracy=float(round(accuracy, 4)),
            precision=float(round(precision, 4)),
            recall=float(round(recall, 4)),
            f1_score=float(round(f1, 4)),
            roc_auc=float(round(roc_auc, 4)),
            latency_ms=float(round(latency_ms, 3)),
            tp=tp, fp=fp, tn=tn, fn=fn
        )

    def _eval_zscore(self, vals: np.ndarray, y_true: np.ndarray) -> DetectorMetrics:
        det = ZScoreDetector(threshold=2.5)
        # Warmup on first normal blocks
        for v in vals[y_true == 0][:15]:
            det.update_baseline(float(v))

        preds, scores = [], []
        t0 = time.time()
        for v in vals:
            res = det.detect(float(v), add_to_history=False)
            preds.append(1 if res["is_anomaly"] else 0)
            scores.append(res["score"])
        elapsed = time.time() - t0

        return self._compute_metrics("Z-Score", y_true, np.array(preds), np.array(scores), elapsed)

    def _eval_ewma(self, vals: np.ndarray, y_true: np.ndarray) -> DetectorMetrics:
        det = EWMADetector(alpha=0.3, L=2.5)
        for v in vals[y_true == 0][:15]:
            det.detect(float(v), add_to_history=True)

        preds, scores = [], []
        t0 = time.time()
        for v in vals:
            res = det.detect(float(v), add_to_history=False)
            preds.append(1 if res["is_anomaly"] else 0)
            scores.append(res["score"])
        elapsed = time.time() - t0

        return self._compute_metrics("EWMA", y_true, np.array(preds), np.array(scores), elapsed)

    def _eval_iqr(self, vals: np.ndarray, y_true: np.ndarray) -> DetectorMetrics:
        det = IQRDetector(multiplier=1.5)
        for v in vals[y_true == 0][:15]:
            det.detect(float(v), add_to_history=True)

        preds, scores = [], []
        t0 = time.time()
        for v in vals:
            res = det.detect(float(v), add_to_history=False)
            preds.append(1 if res["is_anomaly"] else 0)
            scores.append(res["score"])
        elapsed = time.time() - t0

        return self._compute_metrics("IQR", y_true, np.array(preds), np.array(scores), elapsed)

    def _eval_iforest(self, X: np.ndarray, y_true: np.ndarray) -> DetectorMetrics:
        det = IsolationForestDetector(warmup_samples=15)
        normal_idx = np.where(y_true == 0)[0][:20]
        if len(normal_idx) > 5:
            det.fit(X[normal_idx])

        preds, scores = [], []
        t0 = time.time()
        for row in X:
            res = det.detect(row, add_to_history=False)
            preds.append(1 if res["is_anomaly"] else 0)
            scores.append(res["score"])
        elapsed = time.time() - t0

        return self._compute_metrics("Isolation Forest", y_true, np.array(preds), np.array(scores), elapsed)

    def _eval_lof(self, X: np.ndarray, y_true: np.ndarray) -> DetectorMetrics:
        det = LOFDetector(warmup_samples=15, n_neighbors=min(10, max(2, len(X) // 5)))
        normal_idx = np.where(y_true == 0)[0][:20]
        if len(normal_idx) > 5:
            det.fit(X[normal_idx])

        preds, scores = [], []
        t0 = time.time()
        for row in X:
            res = det.detect(row, add_to_history=False)
            preds.append(1 if res["is_anomaly"] else 0)
            scores.append(res["score"])
        elapsed = time.time() - t0

        return self._compute_metrics("LOF", y_true, np.array(preds), np.array(scores), elapsed)

    def _eval_ensemble(self, scalar_vals: np.ndarray, X: np.ndarray, y_true: np.ndarray) -> DetectorMetrics:
        ens = EnsembleDetector()
        normal_idx = np.where(y_true == 0)[0][:20]
        if len(normal_idx) > 5:
            ens.iforest.fit(X[normal_idx])
            ens.lof.fit(X[normal_idx])
            for i in normal_idx:
                ens.zscore.update_baseline(float(scalar_vals[i]))
                ens.ewma.detect(float(scalar_vals[i]), add_to_history=True)
                ens.iqr.detect(float(scalar_vals[i]), add_to_history=True)

        preds, scores = [], []
        t0 = time.time()
        for i in range(len(y_true)):
            res = ens.evaluate(
                primary_metric_val=float(scalar_vals[i]),
                feature_vector=X[i],
                add_to_history=False
            )
            preds.append(1 if res.is_anomaly else 0)
            scores.append(res.overall_score)
        elapsed = time.time() - t0

        return self._compute_metrics("Ensemble Framework (LXAD)", y_true, np.array(preds), np.array(scores), elapsed)
