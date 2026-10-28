"""
Rule Engine for LXAD.

Loads declarative rule specifications from rules.yaml, executes deterministic pattern matching
against WindowFeatures and historical events, and synthesizes root-cause explanations.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from lxad.core.preprocessing import WindowFeatures

logger = logging.getLogger(__name__)


@dataclass
class RuleMatch:
    """Represents a successfully triggered rule condition."""
    rule_id: str
    rule_name: str
    module: str
    anomaly_type: str
    severity: str
    score: float
    explanation: str
    remedial_actions: List[str]
    details: Dict[str, Any] = field(default_factory=dict)


class RuleEngine:
    """Evaluates declarative rules against telemetry window features."""

    def __init__(self, rules_file: Optional[str] = None):
        if rules_file is None:
            # Look in same directory as this module
            cur_dir = os.path.dirname(os.path.abspath(__file__))
            rules_file = os.path.join(cur_dir, "rules.yaml")

        self.rules_file = rules_file
        self.rules: List[Dict[str, Any]] = []
        self.load_rules()

    def load_rules(self) -> None:
        """Load or reload YAML rules from file."""
        if not os.path.exists(self.rules_file):
            logger.warning("Rules file %s not found. Using empty rule set.", self.rules_file)
            self.rules = []
            return

        try:
            with open(self.rules_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.rules = data.get("rules", []) if isinstance(data, dict) else []
            logger.info("Loaded %d detection rules from %s", len(self.rules), self.rules_file)
        except Exception as e:
            logger.error("Failed to load rules YAML from %s: %s", self.rules_file, e)
            self.rules = []

    def save_rules(self, yaml_content: str) -> bool:
        """Update and persist rules file from raw YAML string."""
        try:
            parsed = yaml.safe_load(yaml_content)
            if not isinstance(parsed, dict) or "rules" not in parsed:
                return False
            with open(self.rules_file, "w", encoding="utf-8") as f:
                f.write(yaml_content)
            self.rules = parsed.get("rules", [])
            return True
        except Exception as e:
            logger.error("Error saving rules: %s", e)
            return False

    def evaluate(self, wf: WindowFeatures, baseline_metrics: Optional[Dict[str, float]] = None) -> List[RuleMatch]:
        """
        Evaluate all active rules against the provided WindowFeatures.
        """
        baselines = baseline_metrics or {}
        matches: List[RuleMatch] = []

        for r in self.rules:
            rule_id = r.get("id", "UNKNOWN")
            cond = r.get("condition", {})
            try:
                matched, match_ctx = self._check_condition(cond, wf, baselines)
                if matched:
                    # Render explanation template
                    tmpl = r.get("explanation_template", "")
                    try:
                        explanation = tmpl.format(**match_ctx)
                    except Exception:
                        explanation = f"Rule {rule_id} triggered: {r.get('anomaly_type')}"

                    actions = r.get("remedial_actions", [])
                    matches.append(RuleMatch(
                        rule_id=rule_id,
                        rule_name=r.get("name", "Unnamed Rule"),
                        module=r.get("module", "General"),
                        anomaly_type=r.get("anomaly_type", "Anomaly"),
                        severity=r.get("base_severity", "Medium"),
                        score=float(r.get("base_score", 0.5)),
                        explanation=explanation,
                        remedial_actions=list(actions),
                        details=match_ctx
                    ))
            except Exception as e:
                logger.debug("Error checking rule %s: %s", rule_id, e)

        return matches

    def _check_condition(
        self,
        cond: Dict[str, Any],
        wf: WindowFeatures,
        baselines: Dict[str, float]
    ) -> tuple[bool, Dict[str, Any]]:
        """Check individual rule condition constraints."""
        ctx: Dict[str, Any] = {}

        # 1. R-001 Runaway process spike
        if "top_process_min_cpu" in cond:
            cpu_val = wf.get_metric("cpu_percent", "mean", 0.0)
            threshold = float(cond.get("threshold", 85.0))
            if cpu_val >= threshold and wf.top_processes:
                top_p = wf.top_processes[0]
                p_cpu = float(top_p.get("cpu", 0.0))
                min_top_cpu = float(cond.get("top_process_min_cpu", 60.0))
                if p_cpu >= min_top_cpu:
                    ctx.update({
                        "metric_val": cpu_val,
                        "baseline": baselines.get("cpu_percent", 30.0),
                        "process_name": top_p.get("name", "unknown"),
                        "process_pid": top_p.get("pid", 0),
                        "process_cpu": p_cpu
                    })
                    return True, ctx
            return False, ctx

        # 2. R-002 Memory pressure
        if "swap_operator" in cond:
            mem_val = wf.get_metric("memory_percent", "mean", 0.0)
            swap_val = wf.get_metric("swap_percent", "mean", 0.0)
            mem_thresh = float(cond.get("threshold", 88.0))
            swap_thresh = float(cond.get("swap_threshold", 40.0))
            if mem_val >= mem_thresh and swap_val >= swap_thresh:
                ctx.update({
                    "metric_val": mem_val,
                    "swap_val": swap_val
                })
                return True, ctx
            return False, ctx

        # 3. R-003 Error storm
        if "error_count_min" in cond:
            min_errors = int(cond.get("error_count_min", 5))
            if wf.error_count >= min_errors:
                ctx.update({"error_count": wf.error_count})
                return True, ctx
            return False, ctx

        # 4. R-004 Brute force authentication
        if "failed_logons_min" in cond:
            min_failed = int(cond.get("failed_logons_min", 4))
            if wf.security_failed_logon_count >= min_failed:
                ctx.update({"failed_logons": wf.security_failed_logon_count})
                return True, ctx
            return False, ctx

        # 5. R-005 Ransomware-like activity
        if "disk_write_rate_mb_sec" in cond:
            min_files = int(cond.get("file_activity_min", 15))
            min_write_bytes = float(cond.get("disk_write_rate_mb_sec", 10.0)) * 1024 * 1024
            disk_write = wf.get_metric("disk_write_bytes_sec", "mean", 0.0)
            if wf.file_activity_count >= min_files and disk_write >= min_write_bytes:
                ctx.update({
                    "file_activity": wf.file_activity_count,
                    "disk_write_mb": disk_write / (1024 * 1024)
                })
                return True, ctx
            return False, ctx

        # 6. R-006 Suspicious process from temp
        if cond.get("new_temp_process"):
            if wf.new_process_count > 0:
                # Check top processes or recent events for temp folder execution
                for p in wf.top_processes:
                    exe = str(p.get("exe", "")).lower()
                    temp_dir = os.environ.get("TEMP", "").lower()
                    if temp_dir and temp_dir in exe:
                        ctx.update({
                            "process_name": p.get("name", "unknown"),
                            "process_pid": p.get("pid", 0),
                            "process_path": p.get("exe", "")
                        })
                        return True, ctx
            return False, ctx

        # 7. R-007 High outbound network spike
        if "threshold_mb_sec" in cond:
            thresh_bytes = float(cond.get("threshold_mb_sec", 5.0)) * 1024 * 1024
            sent_rate = wf.get_metric("net_sent_bytes_sec", "mean", 0.0)
            if sent_rate >= thresh_bytes:
                ctx.update({
                    "net_sent_mb": sent_rate / (1024 * 1024),
                    "baseline": baselines.get("net_sent_bytes_sec", 0.0) / (1024 * 1024)
                })
                return True, ctx
            return False, ctx

        # 8. R-008 Service instability
        if "service_crash_min" in cond:
            min_crashes = int(cond.get("service_crash_min", 1))
            if wf.service_crash_count >= min_crashes:
                ctx.update({"service_crash_count": wf.service_crash_count})
                return True, ctx
            return False, ctx

        return False, ctx
