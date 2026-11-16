from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()


DUMMY_HASH = password_hash.hash(
    "opendss-dummy-password"
)


def verify_password(
    plain: str,
    hashed: str,
) -> bool:
    return password_hash.verify(
        plain,
        hashed,
    )