from __future__ import annotations

import os
import threading
import time
from collections import deque
from statistics import mean
from typing import Any

import psutil


class MetricsRegistry:
    """Bounded in-memory metrics for the current server process."""

    def __init__(self, max_samples: int = 2000) -> None:
        self._lock = threading.Lock()
        self._samples: dict[str, deque[float]] = {}
        self._counters: dict[str, int] = {}
        self._max_samples = max_samples
        self._process = psutil.Process(os.getpid())
        self._started_at = time.time()

    def observe(self, name: str, value_ms: float) -> None:
        with self._lock:
            self._samples.setdefault(name, deque(maxlen=self._max_samples)).append(
                float(value_ms)
            )

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def snapshot(self, sessions: dict[str, int]) -> dict[str, Any]:
        with self._lock:
            samples = {name: list(values) for name, values in self._samples.items()}
            counters = dict(self._counters)
        return {
            "timestamp": time.time(),
            "started_at": self._started_at,
            "process": {
                "pid": os.getpid(),
                "rss_mb": round(
                    self._process.memory_info().rss / 1024**2,
                    3,
                ),
                "cpu_percent": self._process.cpu_percent(interval=None),
                "threads": self._process.num_threads(),
            },
            "sessions": sessions,
            "rest": {
                name: self._statistics(values)
                for name, values in samples.items()
                if name.endswith("_request_ms")
                or name in {"session_create_ms", "get_results_ms"}
            },
            "snapshot": {
                "solve_count": counters.get("snapshot_runs", 0),
                "solve": self._statistics(samples.get("snapshot_solve_ms", [])),
            },
            "qsts": {
                "runs": counters.get("qsts_runs", 0),
                "total_steps": counters.get("qsts_total_steps", 0),
                "elapsed": self._statistics(samples.get("qsts_elapsed_ms", [])),
                "step": self._statistics(samples.get("qsts_step_ms", [])),
            },
            "counters": counters,
            "sample_count": {name: len(values) for name, values in samples.items()},
        }

    @staticmethod
    def _statistics(values: list[float]) -> dict[str, float | int]:
        if not values:
            return {
                "count": 0,
                "mean": 0.0,
                "min": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
                "max": 0.0,
            }
        ordered = sorted(values)

        def percentile(value: float) -> float:
            if len(ordered) == 1:
                return ordered[0]
            position = (len(ordered) - 1) * value
            lower = int(position)
            upper = min(lower + 1, len(ordered) - 1)
            fraction = position - lower
            return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction

        return {
            "count": len(ordered),
            "mean": round(mean(ordered), 3),
            "min": round(ordered[0], 3),
            "p50": round(percentile(0.50), 3),
            "p95": round(percentile(0.95), 3),
            "p99": round(percentile(0.99), 3),
            "max": round(ordered[-1], 3),
        }


metrics = MetricsRegistry()
