"""LXAD: Lightweight Explainable Anomaly Detection Framework."""

import os

# Limit internal math library thread allocations to preserve <5% CPU and <300MB RAM budget
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

__version__ = "1.0.0"
