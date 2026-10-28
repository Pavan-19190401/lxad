"""
Network Activity and Connection Collector for LXAD.

Monitors active TCP/UDP socket connections, listening ports, connection state distribution,
and associates sockets with owning process IDs.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Set

import psutil

from lxad.core.ingestion import EventQueue, TelemetryEvent

logger = logging.getLogger(__name__)


class NetworkCollector:
    """Monitors live network sockets and connection state metrics."""

    def __init__(self, queue: EventQueue, interval: float = 3.0):
        self.queue = queue
        self.interval = max(1.0, interval)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._known_connections: Set[str] = set()

    def start(self) -> None:
        """Start the network collector thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="LXAD-NetworkCollector", daemon=True)
        self._thread.start()
        logger.info("NetworkCollector started (interval=%.1fs)", self.interval)

    def stop(self) -> None:
        """Stop the network collector thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("NetworkCollector stopped")

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        while self._running:
            t0 = time.time()
            try:
                self._collect()
            except Exception as e:
                logger.error("Error during network collection: %s", e, exc_info=True)

            elapsed = time.time() - t0
            sleep_duration = max(0.1, self.interval - elapsed)
            sleep_end = time.time() + sleep_duration
            while self._running and time.time() < sleep_end:
                time.sleep(0.1)

    def _collect(self) -> None:
        now = time.time()
        try:
            conns = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, Exception) as e:
            logger.debug("Failed to sample net_connections: %s", e)
            return

        total_conns = len(conns)
        status_counts: collections.Counter = collections.Counter()
        pid_conns: collections.Counter = collections.Counter()
        established_conns = 0
        listening_ports = 0

        for c in conns:
            st = c.status
            status_counts[st] += 1
            if st == psutil.CONN_ESTABLISHED:
                established_conns += 1
            elif st == psutil.CONN_LISTEN:
                listening_ports += 1

            if c.pid:
                pid_conns[c.pid] += 1

        # Emit summary metrics
        self.queue.push(TelemetryEvent(
            timestamp=now,
            source="network",
            module="Network",
            type="metric",
            metric_name="active_connections_count",
            value=float(total_conns),
            details={
                "established": established_conns,
                "listening": listening_ports,
                "status_breakdown": dict(status_counts),
                "top_pids": dict(pid_conns.most_common(5))
            }
        ))

        self.queue.push(TelemetryEvent(
            timestamp=now,
            source="network",
            module="Network",
            type="metric",
            metric_name="established_connections_count",
            value=float(established_conns),
        ))
