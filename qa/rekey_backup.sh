#!/bin/bash
# Key rotation (python -m app.security.rekey) and deploy/backup.sh + restore, on COPIES of the scratch DBs.
. "$(dirname "$0")/env.sh"
set -u
cd $REPO/backend
cp /tmp/qa/main.db /tmp/qa/rk.db
OLD=$TMS_DATA_KEY; NEW=$(openssl rand -base64 32)
export DATABASE_URL=sqlite:////tmp/qa/rk.db TMS_STORAGE_DIR=/tmp/qa/rk-storage; mkdir -p $TMS_STORAGE_DIR
echo "== rekey dry-run (new key + previous=old)"; TMS_DATA_KEY=$NEW TMS_DATA_KEY_PREVIOUS=$OLD $PY -m app.security.rekey --dry-run; echo "rc=$?"
echo "== rekey real"; TMS_DATA_KEY=$NEW TMS_DATA_KEY_PREVIOUS=$OLD $PY -m app.security.rekey; echo "rc=$?"
echo "== rekey again (idempotent?)"; TMS_DATA_KEY=$NEW TMS_DATA_KEY_PREVIOUS=$OLD $PY -m app.security.rekey; echo "rc=$?"
echo "== decrypt with NEW only"; TMS_DATA_KEY=$NEW $PY - <<'PY'
import sys, sqlite3
sys.path.insert(0, "/home/user/training/backend")
import os, base64
from app.security import crypto
from app.config import decode_key
crypto.configure([decode_key(os.environ["TMS_DATA_KEY"])])
c = sqlite3.connect("/tmp/qa/rk.db"); ok = bad = 0
for (v,) in c.execute("select national_code from employees where national_code is not null"):
    try: crypto.get_cipher().decrypt(v, "employee.national_code"); ok += 1
    except Exception: bad += 1
print("national_code ok:", ok, "undecryptable:", bad)
for (v,) in c.execute("select secrets from connector_configs where secrets is not null"):
    try: crypto.get_cipher().decrypt(v, "connector.secrets"); print("connector secrets ok")
    except Exception as e: print("connector secrets FAIL", e)
PY
echo "== decrypt with OLD only (must fail now)"; TMS_DATA_KEY=$OLD $PY - <<'PY'
import sys, sqlite3, os
sys.path.insert(0, "/home/user/training/backend")
from app.security import crypto
from app.config import decode_key
crypto.configure([decode_key(os.environ["TMS_DATA_KEY"])])
c = sqlite3.connect("/tmp/qa/rk.db"); v = c.execute("select national_code from employees where national_code is not null limit 1").fetchone()[0]
try: crypto.get_cipher().decrypt(v, "employee.national_code"); print("OLD key still works (rekey did nothing)")
except Exception: print("OLD key rejected (good)")
PY
echo "== backup.sh sqlite"; export DATABASE_URL=sqlite:////tmp/qa/main.db TMS_STORAGE_DIR=/tmp/qa/main-storage; ls /tmp/qa/main-storage 2>/dev/null | head -2
mkdir -p /tmp/qa/main-storage/letters; BACKUP_DIR=/tmp/qa/bk RETENTION_DAYS=30 bash $REPO/deploy/backup.sh; echo rc=$?; ls -la /tmp/qa/bk | tail -3
echo "== backup.sh postgres + restore"; export DATABASE_URL="postgresql+psycopg://tms@127.0.0.1:55432/tms_app"
PATH=/usr/lib/postgresql/16/bin:$PATH BACKUP_DIR=/tmp/qa/bk bash $REPO/deploy/backup.sh; echo rc=$?
DUMP=$(ls -t /tmp/qa/bk/tms-db-*.dump | head -1)
/usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -p 55432 -U tms -d postgres -qc "drop database if exists tms_restore" -c "create database tms_restore"
/usr/lib/postgresql/16/bin/pg_restore --clean --no-owner -h 127.0.0.1 -p 55432 -U tms -d tms_restore $DUMP; echo "pg_restore rc=$?"
/usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -p 55432 -U tms -d tms_restore -tc "select count(*) from employees" -c "select count(*) from audit_log" -c "select tgname from pg_trigger where not tgisinternal"
echo "== restored audit trigger still blocks?"; /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -p 55432 -U tms -d tms_restore -c "delete from audit_log" 2>&1 | tail -1
echo "== backup with sqlite path containing a space / relative"; cd /tmp/qa && cp main.db "/tmp/qa/my db.db" && DATABASE_URL="sqlite:////tmp/qa/my db.db" BACKUP_DIR=/tmp/qa/bk bash $REPO/deploy/backup.sh; echo rc=$?
