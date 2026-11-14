from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerSettings:
    host: str
    port: int
    recycle_threshold: int
    test_progress_delay_ms: int


worker_settings = WorkerSettings(
    host=os.getenv(
        "WORKER_HOST",
        "0.0.0.0",
    ),
    port=int(
        os.getenv(
            "WORKER_PORT",
            "8100",
        )
    ),
    recycle_threshold=int(
        os.getenv(
            "RECYCLE_THRESHOLD",
            "162",
        )
    ),
    test_progress_delay_ms=int(
        os.getenv("WORKER_TEST_PROGRESS_DELAY_MS", "0")
    ),
)