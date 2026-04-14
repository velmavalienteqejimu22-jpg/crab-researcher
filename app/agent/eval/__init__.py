"""
CrabRes Agent Evaluation — Lightweight metrics collection
"""

import json
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Lightweight metrics collection.
    Hooks into pipeline and LLM adapter. Writes JSONL.
    No external dependencies.
    """

    def __init__(self, base_dir: str = ".crabres/eval"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def record_session(self, session_id: str, metrics: dict):
        """Record metrics for a completed pipeline run"""
        entry = {
            "timestamp": time.time(),
            "session_id": session_id,
            **metrics,
        }
        path = self.base_dir / "sessions.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info(f"[Eval] Session {session_id}: TCR={metrics.get('tcr')}, TPT={metrics.get('tpt')}, CPT=${metrics.get('cpt', 0):.4f}")

    def record_event(self, event_type: str, data: dict):
        """Record individual events (LLM call, search, expert activation)"""
        entry = {
            "timestamp": time.time(),
            "event": event_type,
            **data,
        }
        path = self.base_dir / "events.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_summary(self, days: int = 7) -> dict:
        """Generate summary metrics for the last N days"""
        cutoff = time.time() - days * 86400
        metrics = []
        path = self.base_dir / "sessions.jsonl"
        if path.exists():
            for line in path.read_text().strip().split("\n"):
                if line:
                    try:
                        entry = json.loads(line)
                        if entry.get("timestamp", 0) > cutoff:
                            metrics.append(entry)
                    except json.JSONDecodeError:
                        continue

        if not metrics:
            return {"period_days": days, "sessions": 0}

        n = len(metrics)
        return {
            "period_days": days,
            "sessions": n,
            "avg_tcr": round(sum(m.get("tcr", 0) for m in metrics) / n, 2),
            "avg_rdr": round(sum(m.get("rdr", 0) for m in metrics) / n, 2),
            "avg_ear": round(sum(m.get("ear", 0) for m in metrics) / n, 2),
            "avg_tpt": round(sum(m.get("tpt", 0) for m in metrics) / n),
            "avg_cpt": round(sum(m.get("cpt", 0) for m in metrics) / n, 4),
            "avg_ttc": round(sum(m.get("ttc", 0) for m in metrics) / n, 1),
            "playbook_rate": round(sum(1 for m in metrics if m.get("pgr")) / n, 2),
            "deliverable_rate": round(sum(1 for m in metrics if m.get("dgr")) / n, 2),
        }


# Global singleton
_collector: Optional[MetricsCollector] = None


def get_collector() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
