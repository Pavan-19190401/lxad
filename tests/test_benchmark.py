"""
Tests for Benchmark Module and HDFS Evaluation Suite (Phase 5).
"""

import os
import tempfile
import pytest

from lxad.benchmark.loghub_hdfs import generate_synthetic_hdfs, load_hdfs_dataset
from lxad.benchmark.evaluate import BenchmarkEvaluator, BenchmarkReport


def test_synthetic_hdfs_generation_and_loading():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "test_hdfs.log")
        label_file = os.path.join(tmpdir, "test_labels.csv")

        generate_synthetic_hdfs(log_file=log_file, label_file=label_file, n_blocks=30, anomaly_ratio=0.2)
        assert os.path.exists(log_file)
        assert os.path.exists(label_file)

        dataset = load_hdfs_dataset(log_path=log_file, label_path=label_file)
        assert len(dataset.block_ids) == 30
        assert dataset.feature_matrix.shape[0] == 30
        assert dataset.ground_truth.shape[0] == 30
        assert sum(dataset.ground_truth == 1) >= 2


def test_benchmark_evaluator():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "test_hdfs.log")
        label_file = os.path.join(tmpdir, "test_labels.csv")

        generate_synthetic_hdfs(log_file=log_file, label_file=label_file, n_blocks=35, anomaly_ratio=0.2)
        dataset = load_hdfs_dataset(log_path=log_file, label_path=label_file)

        evaluator = BenchmarkEvaluator()
        report = evaluator.run_benchmark(dataset, dataset_name="TestHDFS")

        assert report.total_blocks == 35
        assert len(report.detector_results) >= 6
        detector_names = [m.name for m in report.detector_results]
        assert "Z-Score" in detector_names
        assert "EWMA" in detector_names
        assert "IQR" in detector_names
        assert "Isolation Forest" in detector_names
        assert "LOF" in detector_names
        assert "Ensemble Framework (LXAD)" in detector_names

        # Check metrics validity
        ens_metric = next(m for m in report.detector_results if "Ensemble" in m.name)
        assert 0.0 <= ens_metric.accuracy <= 1.0
        assert 0.0 <= ens_metric.f1_score <= 1.0
        assert 0.0 <= ens_metric.roc_auc <= 1.0
        assert ens_metric.latency_ms > 0

        # Test CSV export
        csv_path = os.path.join(tmpdir, "report.csv")
        report.to_csv(csv_path)
        assert os.path.exists(csv_path)
        with open(csv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) >= 7
