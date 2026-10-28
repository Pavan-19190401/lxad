"""
LogHub HDFS (HDFS_v1) Benchmark Dataset Loader for LXAD.

Parses HDFS log streams with Drain3, groups occurrences by Block ID (blk_-12345...),
constructs block event-count vectors, and aligns vectors with ground-truth anomaly labels.
Bundles a synthetic sample generator so the system works out-of-the-box offline.
"""

from __future__ import annotations

import collections
import csv
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

logger = logging.getLogger(__name__)

BLOCK_REGEX = re.compile(r"(blk_[-0-9]+)")


@dataclass
class HDFSBenchmarkData:
    """Prepared dataset for anomaly detection benchmarking."""
    block_ids: List[str]
    feature_matrix: np.ndarray      # Shape: (n_blocks, n_templates)
    ground_truth: np.ndarray        # Shape: (n_blocks,), 0=Normal, 1=Anomaly
    template_list: List[str]
    total_log_lines: int


def generate_synthetic_hdfs(
    log_file: str = "data/synthetic_hdfs.log",
    label_file: str = "data/synthetic_hdfs_labels.csv",
    n_blocks: int = 60,
    anomaly_ratio: float = 0.15
) -> Tuple[str, str]:
    """Create a realistic offline HDFS benchmark dataset sample."""
    os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)

    normal_templates = [
        "Receiving block {blk} src: /10.250.19.102:54106 dest: /10.250.19.102:50010",
        "BLOCK* NameSystem.allocateBlock: /mnt/hadoop/dfs/data/current/{blk}",
        "PacketResponder 1 for block {blk} terminating",
        "Received block {blk} of size 67108864 from /10.250.19.102",
        "Verification succeeded for block {blk}"
    ]

    anomaly_templates = [
        "BLOCK* NameSystem.addStoredBlock: Redundant addStoredBlock detected for {blk}",
        "Unexpected error reading block {blk} from datanode Connection reset by peer",
        "Block {blk} is corrupted! Checksum mismatch",
        "Failed to transfer {blk} to datanode 10.250.19.105:50010 timed out",
        "PacketResponder 2 for block {blk} error: SocketTimeoutException"
    ]

    rng = np.random.default_rng(42)
    n_anomalies = max(2, int(n_blocks * anomaly_ratio))
    anomaly_indices = set(rng.choice(n_blocks, size=n_anomalies, replace=False))

    labels_list = []
    log_lines = []
    base_ts = time.time() - 3600

    for idx in range(n_blocks):
        blk_id = f"blk_-{1000000000000000000 + idx * 7919}"
        is_anomaly = idx in anomaly_indices
        labels_list.append((blk_id, "Anomaly" if is_anomaly else "Normal"))

        # Generate 4-8 normal log lines
        n_lines = rng.integers(4, 8)
        for _ in range(n_lines):
            tmpl = rng.choice(normal_templates)
            msg = tmpl.format(blk=blk_id)
            log_lines.append(f"081109 203518 143 INFO dfs.DataNode: {msg}")

        # If anomalous, inject error events
        if is_anomaly:
            n_errs = rng.integers(2, 5)
            for _ in range(n_errs):
                tmpl = rng.choice(anomaly_templates)
                msg = tmpl.format(blk=blk_id)
                log_lines.append(f"081109 203525 147 ERROR dfs.DataNode: {msg}")

    # Write synthetic log file
    with open(log_file, "w", encoding="utf-8") as f:
        for line in log_lines:
            f.write(line + "\n")

    # Write synthetic labels CSV
    with open(label_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["BlockId", "Label"])
        for blk, lbl in labels_list:
            writer.writerow([blk, lbl])

    logger.info("Generated synthetic HDFS benchmark dataset: %d blocks (%d anomalies)", n_blocks, n_anomalies)
    return log_file, label_file


def load_hdfs_dataset(log_path: str, label_path: Optional[str] = None) -> HDFSBenchmarkData:
    """
    Parse HDFS log file with Drain3 and construct per-block event count vectors.
    """
    if not os.path.exists(log_path):
        raise FileNotFoundError(f"Log file {log_path} not found.")

    # Labels map: block_id -> 1 (Anomaly) or 0 (Normal)
    labels_map: Dict[str, int] = {}
    if label_path and os.path.exists(label_path):
        with open(label_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    blk = row[0].strip()
                    lbl = 1 if row[1].strip().lower() == "anomaly" else 0
                    labels_map[blk] = lbl

    # Setup Drain3 miner
    config = TemplateMinerConfig()
    config.profiling_enabled = False
    miner = TemplateMiner(config=config)

    # Map: block_id -> Counter of template_id
    block_counts: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    line_count = 0

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_count += 1
            match = BLOCK_REGEX.search(line)
            if not match:
                continue
            blk_id = match.group(1)

            # Mask out block ID for clean clustering
            clean_line = BLOCK_REGEX.sub("<*>", line.strip())
            res = miner.add_log_message(clean_line)
            if res:
                tid = res["cluster_id"]
                block_counts[blk_id][tid] += 1

    unique_blocks = list(block_counts.keys())
    all_template_ids = sorted({tid for counts in block_counts.values() for tid in counts.keys()})
    tid_to_col = {tid: i for i, tid in enumerate(all_template_ids)}

    n_blocks = len(unique_blocks)
    n_features = max(1, len(all_template_ids))
    X = np.zeros((n_blocks, n_features), dtype=np.float64)
    y = np.zeros(n_blocks, dtype=np.int32)

    for i, blk in enumerate(unique_blocks):
        for tid, count in block_counts[blk].items():
            col = tid_to_col[tid]
            X[i, col] = count

        if blk in labels_map:
            y[i] = labels_map[blk]
        else:
            # Default heuristic if labels not provided: blocks with error keywords are anomalous
            y[i] = 1 if any(t > 3 for t in block_counts[blk].keys()) else 0

    id_map = getattr(miner.drain, "id_to_cluster", {})
    templates_list = [id_map[tid].get_template() for tid in all_template_ids if tid in id_map]

    return HDFSBenchmarkData(
        block_ids=unique_blocks,
        feature_matrix=X,
        ground_truth=y,
        template_list=templates_list,
        total_log_lines=line_count
    )
