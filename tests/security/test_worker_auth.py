import asyncio

import pytest
from fastapi import HTTPException

from services.simulation_worker.security import require_worker_token


def test_worker_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setenv("WORKER_SHARED_TOKEN", "worker-secret")
    with pytest.raises(HTTPException) as error:
        asyncio.run(require_worker_token(None))
    assert error.value.status_code == 401


def test_worker_accepts_shared_token(monkeypatch) -> None:
    monkeypatch.setenv("WORKER_SHARED_TOKEN", "worker-secret")
    asyncio.run(require_worker_token("Bearer worker-secret"))