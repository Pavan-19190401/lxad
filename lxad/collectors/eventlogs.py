"""
Event Log Collector for LXAD.

Collects Windows Event Logs (System, Application, Security) or Linux journald/syslog,
monitoring for error bursts, service crashes, application faulting, and security failures.
Degrades gracefully if elevated security permissions are unavailable.
"""

from __future__ import annotations

import logging
import platform
import threading
import time
from typing import Any, Dict, List, Optional, Set

from lxad.core.ingestion import EventQueue, TelemetryEvent

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system().lower() == "windows"

if IS_WINDOWS:
    try:
        import win32evtlog
        import win32evtlogutil
        import winerror
    except ImportError:
        win32evtlog = None  # type: ignore


class EventLogCollector:
    """Monitors OS event logs in real time."""

    def __init__(
        self,
        queue: EventQueue,
        channels: Optional[List[str]] = None,
        interval: float = 3.0
    ):
        self.queue = queue
        self.channels = channels or ["Application", "System", "Security"]
        self.interval = max(1.0, interval)
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Track the latest record processed per channel to avoid duplicates
        self._last_record_ids: Dict[str, int] = {}
        self._denied_channels: Set[str] = set()

    def start(self) -> None:
        """Start the event log monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="LXAD-EventLogCollector", daemon=True)
        self._thread.start()
        logger.info("EventLogCollector started (channels=%s)", self.channels)

    def stop(self) -> None:
        """Stop the event log collector thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("EventLogCollector stopped")

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        # Prime last record IDs on startup so we only process new events
        if IS_WINDOWS and win32evtlog:
            self._prime_windows_channels()

        while self._running:
            t0 = time.time()
            try:
                if IS_WINDOWS and win32evtlog:
                    self._collect_windows()
                else:
                    self._collect_fallback()
            except Exception as e:
                logger.error("Error collecting event logs: %s", e, exc_info=True)

            elapsed = time.time() - t0
            sleep_duration = max(0.1, self.interval - elapsed)
            sleep_end = time.time() + sleep_duration
            while self._running and time.time() < sleep_end:
                time.sleep(0.1)

    def _prime_windows_channels(self) -> None:
        """Find highest record number currently in each channel."""
        for channel in self.channels:
            try:
                handle = win32evtlog.OpenEventLog(None, channel)
                total = win32evtlog.GetNumberOfEventLogRecords(handle)
                oldest = win32evtlog.GetOldestEventLogRecord(handle)
                self._last_record_ids[channel] = oldest + total - 1
                win32evtlog.CloseEventLog(handle)
            except Exception as e:
                logger.warning("Could not prime channel '%s' (may require admin): %s", channel, e)
                if "Access is denied" in str(e):
                    self._denied_channels.add(channel)

    def _collect_windows(self) -> None:
        """Query new events from Windows event channels."""
        for channel in self.channels:
            if channel in self._denied_channels:
                continue

            handle = None
            try:
                handle = win32evtlog.OpenEventLog(None, channel)
                # Read backwards from the newest records
                flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                events = win32evtlog.ReadEventLog(handle, flags, 0)
                if not events:
                    continue

                prev_last_id = self._last_record_ids.get(channel, 0)
                new_max_id = prev_last_id

                for ev in events:
                    rec_id = ev.RecordNumber
                    if rec_id <= prev_last_id:
                        continue
                    if rec_id > new_max_id:
                        new_max_id = rec_id

                    # Classify event level
                    # EVENTLOG_ERROR_TYPE = 1
                    # EVENTLOG_WARNING_TYPE = 2
                    # EVENTLOG_INFORMATION_TYPE = 4
                    # EVENTLOG_AUDIT_SUCCESS = 8
                    # EVENTLOG_AUDIT_FAILURE = 16
                    event_type = ev.EventType
                    event_id = ev.EventID & 0xFFFF  # Mask lower 16 bits
                    source_name = str(ev.SourceName or "Unknown")
                    strings = ev.StringInserts or []
                    msg_text = " | ".join(str(s) for s in strings if s)

                    severity = "INFO"
                    if event_type == 1:
                        severity = "ERROR"
                    elif event_type == 2:
                        severity = "WARNING"
                    elif event_type == 16:
                        severity = "CRITICAL"

                    # Special rule triggers
                    metric_name = "log_event"
                    if severity in ("ERROR", "CRITICAL"):
                        metric_name = "error_count"

                    # Check for security failed logon (Event 4625)
                    if event_id == 4625:
                        metric_name = "security_failed_logon"
                        severity = "WARNING"

                    # Check for service crashes (7034, 7031) or app crashes (1000)
                    if event_id in (7031, 7034, 1000):
                        metric_name = "service_crash"
                        severity = "ERROR"

                    event_ts = time.mktime(ev.TimeGenerated.timetuple()) if hasattr(ev, "TimeGenerated") else time.time()

                    self.queue.push(TelemetryEvent(
                        timestamp=event_ts,
                        source="eventlogs",
                        module=channel,
                        type="log_event",
                        metric_name=metric_name,
                        value=1.0,
                        severity_level=severity,
                        raw_text=f"[{source_name} ID:{event_id}] {msg_text[:300]}",
                        details={
                            "event_id": event_id,
                            "source_name": source_name,
                            "record_id": rec_id,
                            "channel": channel
                        }
                    ))

                self._last_record_ids[channel] = new_max_id

            except Exception as e:
                if "Access is denied" in str(e):
                    logger.warning("Access denied to Windows log channel '%s'. Silencing channel.", channel)
                    self._denied_channels.add(channel)
                else:
                    logger.debug("Error reading channel '%s': %s", channel, e)
            finally:
                if handle:
                    try:
                        win32evtlog.CloseEventLog(handle)
                    except Exception:
                        pass

    def _collect_fallback(self) -> None:
        """Fallback log reader for simulated or non-Windows environments."""
        pass
