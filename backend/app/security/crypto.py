"""AES-256-GCM field encryption.

Format: ``v1.`` + urlsafe-base64(nonce(12) || ciphertext||tag). The *context* string
(``employee.national_code`` ...) is bound as AAD so a ciphertext copied into another column
fails authentication. Decryption tries the current key first, then the previous keys
(``TMS_DATA_KEY_PREVIOUS``) to allow rotation.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "v1."


class DecryptionError(RuntimeError):
    pass


class Cipher:
    def __init__(self, keys: list[bytes]):
        if not keys:
            raise ValueError("no data key configured")
        for k in keys:
            if len(k) != 32:
                raise ValueError("data key must be 32 bytes")
        self._aes = [AESGCM(k) for k in keys]

    def encrypt(self, plaintext: str, context: str) -> str:
        nonce = os.urandom(12)
        ct = self._aes[0].encrypt(nonce, plaintext.encode("utf-8"), context.encode())
        return PREFIX + base64.urlsafe_b64encode(nonce + ct).decode()

    def decrypt(self, token: str, context: str) -> str:
        if not token.startswith(PREFIX):
            raise DecryptionError("unknown ciphertext format")
        try:
            raw = base64.urlsafe_b64decode(token[len(PREFIX):])
        except Exception:
            raise DecryptionError("malformed ciphertext") from None
        if len(raw) < 12 + 16:
            raise DecryptionError("malformed ciphertext")
        nonce, ct = raw[:12], raw[12:]
        for aes in self._aes:
            try:
                return aes.decrypt(nonce, ct, context.encode()).decode("utf-8")
            except InvalidTag:
                continue
        raise DecryptionError("authentication failed (wrong key or context)")

    def encrypt_bytes(self, data: bytes, context: str) -> bytes:
        nonce = os.urandom(12)
        return b"TMS1" + nonce + self._aes[0].encrypt(nonce, data, context.encode())

    def decrypt_bytes(self, blob: bytes, context: str) -> bytes:
        if not blob.startswith(b"TMS1") or len(blob) < 4 + 12 + 16:
            raise DecryptionError("unknown file format")
        nonce, ct = blob[4:16], blob[16:]
        for aes in self._aes:
            try:
                return aes.decrypt(nonce, ct, context.encode())
            except InvalidTag:
                continue
        raise DecryptionError("authentication failed (wrong key or context)")

    def encrypt_json(self, obj: Any, context: str) -> str:
        return self.encrypt(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), context)

    def decrypt_json(self, token: str, context: str) -> Any:
        return json.loads(self.decrypt(token, context))


_cipher: Cipher | None = None


def configure(keys: list[bytes]) -> Cipher:
    global _cipher
    _cipher = Cipher(keys)
    return _cipher


def get_cipher() -> Cipher:
    if _cipher is None:
        raise RuntimeError("cipher not configured; call security.crypto.configure()")
    return _cipher
