#!/bin/bash
# usage: start_server.sh PORT [extra env assignments via environment]
. "$(dirname "$0")/env.sh"
PORT=${1:-18700}
mkdir -p $TMS_STORAGE_DIR
cd $REPO/backend
$PY -m alembic upgrade head >/tmp/qa/alembic.log 2>&1
exec $PY -m uvicorn app.main:app --host 127.0.0.1 --port $PORT --log-level warning
