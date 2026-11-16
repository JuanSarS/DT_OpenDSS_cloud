import os
from pathlib import Path


def read_secret(name: str) -> str:
    file_name = os.getenv(
        f"{name}_FILE"
    )

    if file_name:
        value = Path(
            file_name
        ).read_text(
            encoding="utf-8"
        ).strip()

        if value:
            return value

    value = os.getenv(name)

    if value:
        return value.strip()

    raise RuntimeError(
        f"Required secret is missing: {name}"
    )