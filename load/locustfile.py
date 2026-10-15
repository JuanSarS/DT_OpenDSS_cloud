from __future__ import annotations

import os

from locust import HttpUser, between, task


class SimulationUser(HttpUser):
    abstract = True
    wait_time = between(0.2, 0.8)
    model = os.getenv("OPENDSS_LOAD_MODEL", "ieee123")

    def _create(self) -> str | None:
        response = self.client.post(
            "/simulations",
            json={"topology": self.model},
            name="POST /simulations",
        )
        if response.status_code != 201:
            response.failure(f"creation failed: {response.status_code}")
            return None
        return response.json()["session_id"]

    def _delete(self, session_id: str) -> None:
        response = self.client.delete(
            f"/simulations/{session_id}",
            name="DELETE /simulations/{session_id}",
        )
        if response.status_code != 204:
            response.failure(f"deletion failed: {response.status_code}")


class SnapshotUser(SimulationUser):
    @task
    def snapshot(self) -> None:
        session_id = self._create()
        if session_id is None:
            return
        try:
            response = self.client.post(
                f"/simulations/{session_id}/solve",
                name="POST /simulations/{session_id}/solve snapshot",
            )
            if response.status_code != 200 or not response.json().get("converged"):
                response.failure("snapshot did not converge")
                return
            results = self.client.get(
                f"/simulations/{session_id}/results",
                name="GET /simulations/{session_id}/results",
            )
            if results.status_code != 200:
                results.failure(f"results failed: {results.status_code}")
        finally:
            self._delete(session_id)


class QSTSUser(SimulationUser):
    qsts_duration_hours = float(os.getenv("OPENDSS_LOAD_DURATION_HOURS", "0.25"))
    qsts_step_minutes = float(os.getenv("OPENDSS_LOAD_STEP_MINUTES", "5"))

    @task
    def qsts(self) -> None:
        session_id = self._create()
        if session_id is None:
            return
        try:
            response = self.client.post(
                f"/simulations/{session_id}/solve",
                json={
                    "simulation_type": "qsts",
                    "qsts": {
                        "duration_hours": self.qsts_duration_hours,
                        "step_minutes": self.qsts_step_minutes,
                        "profile_source": "synthetic_daily",
                    },
                },
                name="POST /simulations/{session_id}/solve qsts",
            )
            if response.status_code != 200:
                response.failure(f"qsts failed: {response.status_code}")
                return
            summary = response.json().get("summary", {})
            if summary.get("failed_steps", 1) != 0:
                response.failure("qsts had failed steps")
                return
            results = self.client.get(
                f"/simulations/{session_id}/results",
                name="GET /simulations/{session_id}/results",
            )
            if results.status_code != 200:
                results.failure(f"results failed: {results.status_code}")
        finally:
            self._delete(session_id)
