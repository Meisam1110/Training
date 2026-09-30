"""scrypt password hashing (stdlib only). The cost parameters are stored in the hash string,
so they can be raised later without invalidating existing passwords."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**15, 8, 1
_MAXMEM = 128 * 1024 * 1024


def _b(x: bytes) -> str:
    return base64.b64encode(x).decode()


def hash_password(password: str, *, n: int = N, r: int = R, p: int = P) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=_MAXMEM)
    return f"scrypt${n}${r}${p}${_b(salt)}${_b(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r),
                              p=int(p), dklen=32, maxmem=_MAXMEM)
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:
        return False


# Verified against when the username does not exist, so timing does not reveal valid names.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
