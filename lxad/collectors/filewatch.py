"""
File System Activity Monitor for LXAD using Watchdog.

Watches user-selected log files and critical directories (e.g. Temp, AppData)
to detect rapid file modification bursts (ransomware-like patterns) and suspicious file drops.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from typing import List, Optional, Set

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from lxad.core.ingestion import EventQueue, TelemetryEvent

logger = logging.getLogger(__name__)


class _WatchdogHandler(FileSystemEventHandler):
    """Internal event handler dispatching filesystem events to EventQueue."""

    def __init__(self, queue: EventQueue):
        super().__init__()
        self.queue = queue

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._dispatch("file_modified", event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._dispatch("file_created", event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._dispatch("file_deleted", event.src_path)

    def _dispatch(self, action: str, path: str) -> None:
        # Ignore temporary git or pycache files
        if "__pycache__" in path or ".git" in path or path.endswith((".tmp", ".crdownload")):
            return

        self.queue.push(TelemetryEvent(
            timestamp=time.time(),
            source="filewatch",
            module="FileSystem",
            type="file_event",
            metric_name="file_activity_count",
            value=1.0,
            severity_level="INFO",
            raw_text=f"{action}: {path}",
            details={"action": action, "path": path}
        ))


class FileWatchCollector:
    """Manages watchdog observers for real-time filesystem tracking."""

    def __init__(self, queue: EventQueue, watch_paths: Optional[List[str]] = None):
        self.queue = queue
        default_paths = [tempfile.gettempdir()]
        self.watch_paths: Set[str] = set(watch_paths or default_paths)
        self._observer: Optional[Observer] = None
        self._handler = _WatchdogHandler(queue)
        self._running = False

    def add_path(self, path: str) -> bool:
        """Add a directory or file path to watch."""
        if not os.path.exists(path):
            return False
        abs_p = os.path.abspath(path)
        self.watch_paths.add(abs_p)
        if self._running and self._observer:
            try:
                self._observer.schedule(self._handler, abs_p, recursive=False)
                return True
            except Exception as e:
                logger.error("Failed to schedule watch on %s: %s", abs_p, e)
                return False
        return True

    def remove_path(self, path: str) -> None:
        abs_p = os.path.abspath(path)
        self.watch_paths.discard(abs_p)

    def start(self) -> None:
        """Start watchdog background observer."""
        if self._running:
            return
        self._observer = Observer()
        for p in self.watch_paths:
            if os.path.exists(p):
                try:
                    self._observer.schedule(self._handler, p, recursive=False)
                    logger.info("Watching directory: %s", p)
                except Exception as e:
                    logger.warning("Failed to watch directory %s: %s", p, e)

        self._observer.start()
        self._running = True
        logger.info("FileWatchCollector started")

    def stop(self) -> None:
        """Stop watchdog observer cleanly."""
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
        logger.info("FileWatchCollector stopped")

    def is_alive(self) -> bool:
        return bool(self._running and self._observer and self._observer.is_alive())
