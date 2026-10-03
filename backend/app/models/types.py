"""Column types that encrypt transparently (AES-256-GCM) -- see security/crypto.py."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.security.crypto import get_cipher


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, context: str):
        super().__init__()
        self.context = context

    def process_bind_param(self, value: Any, dialect):
        if value is None or value == "":
            return None
        return get_cipher().encrypt(str(value), self.context)

    def process_result_value(self, value: Any, dialect):
        return None if value is None else get_cipher().decrypt(value, self.context)


class EncryptedJSON(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, context: str):
        super().__init__()
        self.context = context

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        return get_cipher().encrypt(json.dumps(value, ensure_ascii=False), self.context)

    def process_result_value(self, value: Any, dialect):
        return None if value is None else json.loads(get_cipher().decrypt(value, self.context))


class EncryptedTextCompat(EncryptedText):
    """Like EncryptedText, but a value that is not ``v1.``-prefixed is a pre-encryption legacy row and is
    returned as-is (it is encrypted the next time the row is written, or by ``python -m app.security.rekey``)."""
    cache_ok = True
    legacy_plaintext_ok = True

    def process_result_value(self, value: Any, dialect):
        if value is None:
            return None
        return get_cipher().decrypt(value, self.context) if value.startswith("v1.") else value
