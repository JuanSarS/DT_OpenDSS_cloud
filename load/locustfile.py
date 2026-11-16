from __future__ import annotations

import os

from locust import HttpUser, between, task


class SimulationUser(HttpUser):
    abstract = True
    wait_time = between(0.2, 0.8)
    model = os.getenv("OPENDSS_LOAD_MODEL", "ieee123")

    def on_start(self) -> None:
        username = os.getenv("OPENDSS_LOAD_USERNAME", "admin")
        password = os.getenv("OPENDSS_LOAD_PASSWORD")
        if not password:
            raise RuntimeError("OPENDSS_LOAD_PASSWORD es obligatorio para Locust")
        response = self.client.post(
            "/auth/token",
            data={"username": username, "password": password},
            name="POST /auth/token",
        )
        if response.status_code != 200:
            response.failure(f"login failed: {response.status_code}")
            raise RuntimeError("No fue posible autenticar usuario Locust")
        token = response.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    def _create(self) -> str | None:
        with self.client.post(
            "/simulations",
            json={"topology": self.model},
            name="POST /simulations",
            catch_response=True,
        ) as response:

            if response.status_code != 201:
                response.failure(
                    f"creation failed HTTP {response.status_code}: "
                    f"{self._response_detail(response)}"
                )
                return None

            try:
                payload = response.json()
            except ValueError:
                response.failure(
                    "creation returned invalid JSON: "
                    f"{self._response_detail(response)}"
                )
                return None

            session_id = payload.get("session_id")

            if not session_id:
                response.failure(
                    "creation response has no session_id"
                )
                return None

            return session_id

    def _delete(self, session_id: str) -> None:
        with self.client.delete(
            f"/simulations/{session_id}",
            name="DELETE /simulations/{session_id}",
            catch_response=True,
        ) as response:

            if response.status_code != 204:
                response.failure(
                    f"deletion failed HTTP {response.status_code}: "
                    f"{self._response_detail(response)}"
                )
    def _response_detail(self, response) -> str:
        try:
            text = response.text or ""
        except Exception:
            text = ""

        text = " ".join(text.split())

        if len(text) > 500:
            text = text[:500] + "..."

        return text
@task
def snapshot(self) -> None:
    session_id = self._create()

    if session_id is None:
        return

    try:
        with self.client.post(
            f"/simulations/{session_id}/solve",
            name="POST /simulations/{session_id}/solve snapshot",
            catch_response=True,
        ) as response:

            if response.status_code != 200:
                response.failure(
                    f"snapshot failed HTTP {response.status_code}: "
                    f"{self._response_detail(response)}"
                )
                return

            try:
                payload = response.json()
            except ValueError:
                response.failure(
                    "snapshot returned invalid JSON"
                )
                return

            if not payload.get("converged"):
                response.failure(
                    "snapshot did not converge"
                )
                return

        with self.client.get(
            f"/simulations/{session_id}/results",
            name="GET /simulations/{session_id}/results",
            catch_response=True,
        ) as results:

            if results.status_code != 200:
                results.failure(
                    f"results failed HTTP {results.status_code}: "
                    f"{self._response_detail(results)}"
                )

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
            with self.client.post(
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
                catch_response=True,
            ) as response:

                if response.status_code != 200:
                    response.failure(
                        f"qsts failed HTTP {response.status_code}: "
                        f"{self._response_detail(response)}"
                    )
                    return

                try:
                    payload = response.json()
                except ValueError:
                    response.failure(
                        "qsts returned invalid JSON"
                    )
                    return

                summary = payload.get("summary", {})

                if summary.get("failed_steps", 1) != 0:
                    response.failure(
                        f"qsts had failed steps: {summary}"
                    )
                    return

            with self.client.get(
                f"/simulations/{session_id}/results",
                name="GET /simulations/{session_id}/results",
                catch_response=True,
            ) as results:

                if results.status_code != 200:
                    results.failure(
                        f"results failed HTTP {results.status_code}: "
                        f"{self._response_detail(results)}"
                    )

        finally:
            self._delete(session_id)