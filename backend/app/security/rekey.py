"""Bulk re-encryption for TMS_DATA_KEY rotation.

    TMS_DATA_KEY=<new> TMS_DATA_KEY_PREVIOUS=<old>[,<older>] DATABASE_URL=... python -m app.security.rekey [--dry-run] [--batch 500]

Every encrypted column (found by introspecting the models, so a new EncryptedText column is covered
automatically) is read as raw ciphertext; values the NEW key cannot open are decrypted with a previous
key and rewritten under the new one. Values already under the new key are left alone, so the command is
idempotent and safe to re-run. ``--dry-run`` reports and writes nothing. A value that no configured key
opens is reported (table, column, primary key -- never the value) and left untouched; exit status 1.
Take a backup first (deploy/backup.sh). Drop TMS_DATA_KEY_PREVIOUS only after a clean run.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

import app.models  # noqa: F401  (register tables)
from app.config import ensure_dev_key, load_settings
from app.db import Base, make_engine
from app.models.types import EncryptedJSON, EncryptedText
from app.security import crypto


@dataclass
class Report:
    scanned: int = 0
    rekeyed: int = 0
    current: int = 0
    empty: int = 0
    failed: list[str] = field(default_factory=list)


_COMPAT = {t.name: {c.name for c in t.columns if getattr(c.type, "legacy_plaintext_ok", False)} for t in Base.metadata.sorted_tables}


def targets() -> list[tuple[str, str, str, str]]:
    """(table, primary-key column, column, AAD context) of every encrypted column."""
    out = []
    for t in Base.metadata.sorted_tables:
        pk = [c.name for c in t.primary_key.columns]
        for c in t.columns:
            if isinstance(c.type, (EncryptedText, EncryptedJSON)) and len(pk) == 1:
                out.append((t.name, pk[0], c.name, c.type.context))
    return out


def _flush(engine: Engine, table: str, pk: str, col: str, pending: list[tuple[object, str]], dry_run: bool) -> None:
    if pending and not dry_run:
        with engine.begin() as c:
            for rid, tok in pending:
                c.execute(text(f'UPDATE "{table}" SET "{col}" = :v WHERE "{pk}" = :id'), {"v": tok, "id": rid})
    pending.clear()


def _rekey_files(folder: Path, primary: crypto.Cipher, anykey: crypto.Cipher, rep: Report, dry_run: bool) -> None:
    """Encrypted letter files (`TMS1` format). Legacy plain .docx files (zip magic) are encrypted too."""
    if not folder.is_dir():
        return
    for p in sorted(folder.iterdir()):
        if not p.is_file():
            continue
        rep.scanned += 1
        blob = p.read_bytes()
        if blob[:2] == b"PK":
            plain = blob
        else:
            try:
                primary.decrypt_bytes(blob, "letter.file")
                rep.current += 1
                continue
            except crypto.DecryptionError:
                pass
            try:
                plain = anykey.decrypt_bytes(blob, "letter.file")
            except crypto.DecryptionError:
                rep.failed.append(f"letters/{p.name}")
                continue
        rep.rekeyed += 1
        if not dry_run:
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_bytes(primary.encrypt_bytes(plain, "letter.file"))
            tmp.replace(p)


def rekey(engine: Engine, keys: list[bytes], *, dry_run: bool = False, batch: int = 500, storage_dir: Path | None = None) -> Report:
    if len(keys) < 2:
        raise ValueError("set TMS_DATA_KEY (new) and TMS_DATA_KEY_PREVIOUS (old)")
    primary, anykey = crypto.Cipher(keys[:1]), crypto.Cipher(keys)
    rep = Report()
    for table, pk, col, ctx in targets():
        with engine.connect() as c:
            rows = c.execute(text(f'SELECT "{pk}", "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL')).all()
        pending: list[tuple[object, str]] = []

        for rid, token in rows:
            rep.scanned += 1
            if token == "":
                rep.empty += 1
                continue
            if not token.startswith(crypto.PREFIX) and col in _COMPAT.get(table, ()):
                rep.rekeyed += 1                    # legacy plaintext row of a *Compat column: encrypt it now
                pending.append((rid, primary.encrypt(token, ctx)))
                continue
            try:
                primary.decrypt(token, ctx)
                rep.current += 1
                continue
            except crypto.DecryptionError:
                pass
            try:
                plain = anykey.decrypt(token, ctx)
            except crypto.DecryptionError:
                rep.failed.append(f"{table}.{col} id={rid}")
                continue
            rep.rekeyed += 1
            pending.append((rid, primary.encrypt(plain, ctx)))
            if len(pending) >= batch:
                _flush(engine, table, pk, col, pending, dry_run)
        _flush(engine, table, pk, col, pending, dry_run)
    if storage_dir is not None:
        _rekey_files(storage_dir / "letters", primary, anykey, rep, dry_run)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Re-encrypt personal data / connector secrets under the current TMS_DATA_KEY")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch", type=int, default=500)
    a = ap.parse_args(argv)
    s = load_settings()
    s.validate()
    s = ensure_dev_key(s)
    keys = s.data_keys()
    try:
        rep = rekey(make_engine(s.database_url), keys, dry_run=a.dry_run, batch=max(1, a.batch), storage_dir=s.storage_path)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    mode = "DRY RUN (nothing written)" if a.dry_run else "done"
    print(f"rekey {mode}: scanned={rep.scanned} rekeyed={rep.rekeyed} already_current={rep.current} empty={rep.empty} "
          f"failed={len(rep.failed)}")
    for f in rep.failed[:50]:
        print(f"  cannot decrypt: {f}", file=sys.stderr)
    return 1 if rep.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
