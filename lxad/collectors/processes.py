"""
Process Activity Collector for LXAD.

Monitors active processes, tracks process lifecycles (new spawns and terminations),
detects top resource offenders, and tracks process parent-child spawn relationships.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set

import psutil

from lxad.core.ingestion import EventQueue, TelemetryEvent

logger = logging.getLogger(__name__)


class ProcessCollector:
    """Monitors running processes and lifecycle changes."""

    def __init__(self, queue: EventQueue, interval: float = 2.0, top_k: int = 5):
        self.queue = queue
        self.interval = max(0.1, interval)
        self.top_k = top_k
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._known_pids: Set[int] = set()
        self._first_run = True

    def start(self) -> None:
        """Start the process collector thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="LXAD-ProcessCollector", daemon=True)
        self._thread.start()
        logger.info("ProcessCollector started (interval=%.1fs)", self.interval)

    def stop(self) -> None:
        """Signal collector to stop and wait for completion."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("ProcessCollector stopped")

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        while self._running:
            t0 = time.time()
            try:
                self._collect()
            except Exception as e:
                logger.error("Error during process collection: %s", e, exc_info=True)

            elapsed = time.time() - t0
            sleep_duration = max(0.1, self.interval - elapsed)
            sleep_end = time.time() + sleep_duration
            while self._running and time.time() < sleep_end:
                time.sleep(0.1)

    def _collect(self) -> None:
        now = time.time()
        current_procs: List[Dict[str, Any]] = []
        current_pids: Set[int] = set()

        # Fast attribute querying: <20ms for all 300+ processes
        fast_attrs = ["pid", "name", "cpu_percent", "memory_percent", "exe"]
        for p in psutil.process_iter(attrs=fast_attrs):
            if not self._running:
                return
            try:
                info = p.info
                pid = info["pid"]
                if pid == 0:  # Skip System Idle Process
                    continue
                current_pids.add(pid)
                current_procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # Detect new processes spawned since last sample
        if not self._first_run:
            new_pids = current_pids - self._known_pids
            for pid in new_pids:
                matching = next((p for p in current_procs if p["pid"] == pid), None)
                if matching:
                    exe_path = matching.get("exe") or ""
                    # Check parent PID only for newly spawned processes
                    parent_pid = None
                    try:
                        p_obj = psutil.Process(pid)
                        parent_pid = p_obj.ppid()
                    except Exception:
                        pass

                    # Check if spawned from temporary or user-writable locations
                    temp_dir = os.environ.get("TEMP", "").lower()
                    is_temp = bool(exe_path and temp_dir and temp_dir in exe_path.lower())

                    self.queue.push(TelemetryEvent(
                        timestamp=now,
                        source="processes",
                        module="Process",
                        type="process_spawn",
                        metric_name="process_spawn_count",
                        value=1.0,
                        severity_level="WARNING" if is_temp else "INFO",
                        raw_text=f"Process spawned: {matching.get('name')} (PID: {pid}, Parent: {parent_pid})",
                        details={
                            "pid": pid,
                            "name": matching.get("name"),
                            "ppid": parent_pid,
                            "exe": exe_path,
                            "is_temp": is_temp
                        }
                    ))

            # Detect terminated processes
            terminated_pids = self._known_pids - current_pids
            if terminated_pids:
                self.queue.push(TelemetryEvent(
                    timestamp=now,
                    source="processes",
                    module="Process",
                    type="process_exit",
                    metric_name="process_exit_count",
                    value=float(len(terminated_pids)),
                    severity_level="INFO",
                    raw_text=f"{len(terminated_pids)} process(es) terminated.",
                    details={"pids": list(terminated_pids)[:10]}
                ))

        self._known_pids = current_pids
        self._first_run = False

        # Identify top CPU and RAM consumers
        top_cpu = sorted(current_procs, key=lambda x: (x.get("cpu_percent") or 0.0), reverse=True)[:self.top_k]
        top_mem = sorted(current_procs, key=lambda x: (x.get("memory_percent") or 0.0), reverse=True)[:self.top_k]

        # Emit top offender event
        self.queue.push(TelemetryEvent(
            timestamp=now,
            source="processes",
            module="Process",
            type="process_top",
            metric_name="top_process_cpu",
            value=float(top_cpu[0].get("cpu_percent") or 0.0) if top_cpu else 0.0,
            raw_text=f"Top CPU process: {top_cpu[0].get('name')} ({top_cpu[0].get('cpu_percent', 0):.1f}%)" if top_cpu else "",
            details={
                "top_cpu": [
                    {"pid": p["pid"], "name": p["name"], "cpu": p.get("cpu_percent", 0.0), "mem": p.get("memory_percent", 0.0), "exe": p.get("exe", "")}
                    for p in top_cpu
                ],
                "top_mem": [
                    {"pid": p["pid"], "name": p["name"], "cpu": p.get("cpu_percent", 0.0), "mem": p.get("memory_percent", 0.0), "exe": p.get("exe", "")}
                    for p in top_mem
                ]
            }
        ))
