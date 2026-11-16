from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
from pathlib import Path

import httpx

from tools.evidence.common import ensure_run_dir, write_json


def password_for(label: str, env_name: str) -> str:
    value = os.getenv(env_name)
    return value or getpass.getpass(f"Password de {label}: ")


async def login(base_url: str, username: str, password: str) -> httpx.AsyncClient:
    client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=180.0)
    response = await client.post("/auth/token", data={"username": username, "password": password})
    response.raise_for_status()
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


async def main_async(args: argparse.Namespace) -> None:
    run_dir = ensure_run_dir(args.output_root, "security")
    results: list[dict] = []

    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=30.0) as anonymous:
        unauth = await anonymous.get("/simulations")
        results.append({"test": "REST sin token", "expected": 401, "actual": unauth.status_code})
        bad = await anonymous.get("/simulations", headers={"Authorization": "Bearer invalid.jwt.value"})
        results.append({"test": "token invalido", "expected": 401, "actual": bad.status_code})

    admin = await login(args.base_url, args.admin, password_for(args.admin, "OPENDSS_ADMIN_PASSWORD"))
    user1 = await login(args.base_url, args.user1, password_for(args.user1, "OPENDSS_USER1_PASSWORD"))
    user2 = await login(args.base_url, args.user2, password_for(args.user2, "OPENDSS_USER2_PASSWORD"))
    session_id = None
    admission_sessions: list[str] = []
    try:
        created = await user1.post("/simulations", json={"topology": "ieee123"})
        created.raise_for_status()
        session_id = created.json()["session_id"]

        denied_detail = await user2.get(f"/simulations/{session_id}")
        results.append({"test": "aislamiento detail user2->user1", "expected": 403, "actual": denied_detail.status_code})
        denied_solve = await user2.post(
            f"/simulations/{session_id}/solve", json={"simulation_type": "snapshot"}
        )
        results.append({"test": "aislamiento solve user2->user1", "expected": 403, "actual": denied_solve.status_code})

        viewer = await user1.post(
            f"/simulations/{session_id}/viewers", json={"username": args.user2}
        )
        viewer.raise_for_status()
        viewer_detail = await user2.get(f"/simulations/{session_id}")
        results.append({"test": "viewer puede ver", "expected": 200, "actual": viewer_detail.status_code})
        viewer_solve = await user2.post(
            f"/simulations/{session_id}/solve", json={"simulation_type": "snapshot"}
        )
        results.append({"test": "viewer no controla", "expected": 403, "actual": viewer_solve.status_code})

        metrics = await admin.get("/metrics")
        results.append({"test": "metrics admin", "expected": 200, "actual": metrics.status_code})
        if metrics.status_code == 200:
            write_json(run_dir / "metrics_security.json", metrics.json())
        summary_before = await admin.get("/admin/security/summary")
        if summary_before.status_code == 200:
            write_json(run_dir / "security_summary_before_rate_limit.json", summary_before.json())

        if args.test_admission:
            for _ in range(3):
                response = await user1.post("/simulations", json={"topology": "ieee123"})
                response.raise_for_status()
                admission_sessions.append(response.json()["session_id"])
            payload = {
                "simulation_type": "qsts",
                "qsts": {
                    "duration_hours": 1.0,
                    "step_minutes": 1.0,
                    "profile_source": "synthetic_daily",
                },
            }
            first = asyncio.create_task(user1.post(f"/simulations/{admission_sessions[0]}/solve", json=payload))
            second = asyncio.create_task(user1.post(f"/simulations/{admission_sessions[1]}/solve", json=payload))
            await asyncio.sleep(0.2)
            third = await user1.post(f"/simulations/{admission_sessions[2]}/solve", json=payload)
            results.append({"test": "tercer job concurrente", "expected": 429, "actual": third.status_code})
            await asyncio.gather(first, second)

        # Delete protected test sessions BEFORE deliberately exhausting the IP rate
        # limiter. Otherwise cleanup requests may themselves receive 429.
        if session_id:
            cleanup = await user1.delete(f"/simulations/{session_id}")
            results.append({"test": "cleanup owner session", "expected": 204, "actual": cleanup.status_code})
            session_id = None
        for item in list(admission_sessions):
            cleanup = await user1.delete(f"/simulations/{item}")
            results.append({"test": f"cleanup admission {item}", "expected": 204, "actual": cleanup.status_code})
        admission_sessions.clear()

        # Rate limit last, because it is intentionally keyed to the client IP.
        statuses = []
        async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=30.0) as burst:
            for _ in range(args.rate_requests):
                response = await burst.get("/simulations")
                statuses.append(response.status_code)
            health = await burst.get("/health")
        results.append({
            "test": "rate limit produce 429",
            "expected": 429,
            "actual": 429 if 429 in statuses else max(statuses),
            "counts": {str(code): statuses.count(code) for code in sorted(set(statuses))},
        })
        results.append({"test": "health bajo rate limit", "expected": 200, "actual": health.status_code})

    finally:
        # Best-effort cleanup only for sessions that were not already deleted before
        # the rate-limit burst. Errors are ignored here so they cannot mask evidence.
        if session_id:
            try:
                await user1.delete(f"/simulations/{session_id}")
            except Exception:
                pass
        for item in admission_sessions:
            try:
                await user1.delete(f"/simulations/{item}")
            except Exception:
                pass
        await admin.aclose()
        await user1.aclose()
        await user2.aclose()

    passed = all(item["actual"] == item["expected"] for item in results)
    write_json(run_dir / "security_results.json", results)
    write_json(run_dir / "summary.json", {"passed": passed, "tests": results})
    (run_dir / "REPORT.md").write_text(
        "# Evidencia Entregable 3 — Seguridad\n\n"
        f"Resultado: **{'PASS' if passed else 'FAIL'}**\n\n"
        "Incluye autenticación, aislamiento horizontal, permisos de espectadores, "
        "métricas administrativas, rate limiting y disponibilidad de `/health`.\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": passed, "tests": results}, indent=2))
    print(f"Evidence: {run_dir}")
    raise SystemExit(0 if passed else 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin", default="admin")
    parser.add_argument("--user1", default="user1")
    parser.add_argument("--user2", default="user2")
    parser.add_argument("--rate-requests", type=int, default=140)
    parser.add_argument("--test-admission", action="store_true")
    parser.add_argument("--output-root", default="docs/evidence/deliverable_3")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
