from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--security-dir", default="")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)

    resilience = load(run_dir / "resilience_result.json") or {}
    manifest = load(run_dir / "manifest.json") or {}
    security = None
    if args.security_dir:
        security = load(Path(args.security_dir) / "summary.json")

    payload = {
        "resilience_passed": bool(resilience.get("passed")),
        "observed_qsts_restart": bool(resilience.get("observed_restart")),
        "initial_worker": resilience.get("initial_worker"),
        "stopped_task": manifest.get("stopped_task"),
        "security_passed": None if security is None else bool(security.get("passed")),
    }
    payload["passed"] = payload["resilience_passed"] and (
        payload["security_passed"] is not False
    )
    (run_dir / "SUMMARY.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report = f"""# Evidencia Entregable 3 — resiliencia

- Resiliencia completada: **{'PASS' if payload['resilience_passed'] else 'FAIL'}**
- Reinicio QSTS observado desde secuencia de progreso: **{'SI' if payload['observed_qsts_restart'] else 'NO'}**
- Worker inicial: `{payload['initial_worker']}`
- Task ECS detenida: `{payload['stopped_task']}`
- Suite de seguridad: **{('NO VINCULADA' if payload['security_passed'] is None else ('PASS' if payload['security_passed'] else 'FAIL'))}**

Los eventos crudos WebSocket están en `ws_events.jsonl`; los datos de la task detenida y del servicio ECS permanecen en esta misma carpeta.
"""
    (run_dir / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
