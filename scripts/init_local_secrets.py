from getpass import getpass
import json
import secrets
from pathlib import Path

from pwdlib import PasswordHash


ROOT = Path(__file__).resolve().parents[1]
SECRETS_DIR = ROOT / "secrets" / "local"


def _password_hash(username: str) -> str:
    first = getpass(f"Password para {username}: ")
    second = getpass(f"Repita password para {username}: ")
    if not first or first != second:
        raise ValueError(f"Las passwords de {username} no coinciden o están vacías")
    return PasswordHash.recommended().hash(first)


def main() -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    (SECRETS_DIR / "jwt_secret.txt").write_text(
        secrets.token_urlsafe(32),
        encoding="utf-8",
    )
    (SECRETS_DIR / "worker_shared_token.txt").write_text(
        secrets.token_urlsafe(32),
        encoding="utf-8",
    )
    users = {
        "admin": {
            "username": "admin",
            "role": "admin",
            "disabled": False,
            "password_hash": _password_hash("admin"),
        },
        "user1": {
            "username": "user1",
            "role": "user",
            "disabled": False,
            "password_hash": _password_hash("user1"),
        },
        "user2": {
            "username": "user2",
            "role": "user",
            "disabled": False,
            "password_hash": _password_hash("user2"),
        },
    }
    (SECRETS_DIR / "auth_users.json").write_text(
        json.dumps(users, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Secretos locales creados en {SECRETS_DIR}")


if __name__ == "__main__":
    main()
