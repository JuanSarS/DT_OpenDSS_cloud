from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"


def latest_dirs(parent: Path) -> list[Path]:
    if not parent.exists():
        return []
    return sorted([item for item in parent.iterdir() if item.is_dir()], reverse=True)


def main() -> None:
    lines = [
        "# Índice de evidencia",
        "",
        f"Generado UTC: `{datetime.now(timezone.utc).isoformat()}`",
        "",
    ]
    groups = [
        ("Regresión local", "regression"),
        ("Despliegues AWS", "deployments"),
        ("Entregable 1", "deliverable_1"),
        ("Entregable 2", "deliverable_2"),
        ("Entregable 3", "deliverable_3"),
    ]
    for title, folder in groups:
        lines += [f"## {title}", ""]
        runs = latest_dirs(EVIDENCE / folder)
        if not runs:
            lines += ["Sin ejecuciones registradas.", ""]
            continue
        for run in runs[:20]:
            relative = run.relative_to(ROOT).as_posix()
            report = run / "REPORT.md"
            summary_candidates = [run / "summary.json", run / "SUMMARY.json", run / "PERFORMANCE_SUMMARY.json", run / "manifest.json"]
            lines.append(f"- `{relative}/`")
            if report.exists():
                lines.append(f"  - Report: `{report.relative_to(ROOT).as_posix()}`")
            for candidate in summary_candidates:
                if candidate.exists():
                    lines.append(f"  - Datos: `{candidate.relative_to(ROOT).as_posix()}`")
        lines.append("")
    target = EVIDENCE / "EVIDENCE_INDEX.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
