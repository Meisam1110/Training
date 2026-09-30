#!/usr/bin/env bash
# Backup with retention.  PostgreSQL: pg_dump (custom format).  SQLite: consistent online copy.
# Also archives the letters/ directory. The data key (TMS_DATA_KEY) is NOT included -- back it up
# separately, or the encrypted columns in a restored database cannot be read.
#
#   BACKUP_DIR=/var/backups/tms RETENTION_DAYS=30 deploy/backup.sh
# Env: DATABASE_URL (required), TMS_STORAGE_DIR (default /var/lib/tms), BACKUP_DIR, RETENTION_DAYS
set -euo pipefail
umask 077

: "${DATABASE_URL:?DATABASE_URL is required}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
STORAGE="${TMS_STORAGE_DIR:-/var/lib/tms}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

case "$DATABASE_URL" in
  postgresql*|postgres*)
    # strip the SQLAlchemy driver suffix (postgresql+psycopg://) for libpq tools
    PGURL="$(printf '%s' "$DATABASE_URL" | sed -E 's#^(postgres(ql)?)\+[a-z0-9]+://#\1://#')"
    # keep the password OUT of argv (visible in `ps`): pass it through PGPASSWORD and strip it from the URL
    PGPASSWORD="$(python3 -c 'import sys,urllib.parse as u; print(u.unquote(u.urlsplit(sys.argv[1]).password or ""))' "$PGURL")"
    export PGPASSWORD
    PGURL="$(python3 -c 'import sys,urllib.parse as u; p=u.urlsplit(sys.argv[1]); h=p.hostname or ""; h=f"[{h}]" if ":" in h else h; n=(p.username and u.quote(p.username) or "")+"@"+h+(f":{p.port}" if p.port else "") if p.username else h+(f":{p.port}" if p.port else ""); print(u.urlunsplit((p.scheme,n,p.path,p.query,"")))' "$PGURL")"
    OUT="$BACKUP_DIR/tms-db-$STAMP.dump"
    pg_dump --format=custom --no-owner --dbname="$PGURL" --file="$OUT"
    ;;
  sqlite*)
    DB="${DATABASE_URL#sqlite:///}"
    OUT="$BACKUP_DIR/tms-db-$STAMP.sqlite"
    if command -v sqlite3 >/dev/null 2>&1; then
      sqlite3 "$DB" ".backup '$OUT'"        # safe while the app is running (WAL aware)
    else
      python3 - "$DB" "$OUT" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
with dst: src.backup(dst)
PY
    fi
    ;;
  *) echo "unsupported DATABASE_URL scheme" >&2; exit 2 ;;
esac

if [ -d "$STORAGE/letters" ]; then
  tar -C "$STORAGE" -czf "$BACKUP_DIR/tms-letters-$STAMP.tar.gz" letters
fi

# retention: delete our own files older than N days
find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'tms-db-*' -o -name 'tms-letters-*' \) -mtime +"$RETENTION_DAYS" -delete

echo "backup written: $OUT"
