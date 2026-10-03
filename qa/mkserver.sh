#!/bin/bash
# usage: mkserver.sh NAME PORT [--demo N]   -> scratch DB /tmp/qa/NAME.db, storage /tmp/qa/NAME-storage, log qa/logs/server_NAME.log
NAME=$1; PORT=$2
export DATABASE_URL=${DATABASE_URL:-sqlite:////tmp/qa/$NAME.db}
export TMS_STORAGE_DIR=/tmp/qa/$NAME-storage
. "$(dirname "$0")/env.sh"
[ -f /tmp/qa/$NAME.pid ] && kill $(cat /tmp/qa/$NAME.pid) 2>/dev/null; sleep 1
rm -rf /tmp/qa/$NAME.db* $TMS_STORAGE_DIR; mkdir -p $TMS_STORAGE_DIR
cd $REPO/backend
$PY -m alembic upgrade head >/tmp/qa/alembic_$NAME.log 2>&1 || { cat /tmp/qa/alembic_$NAME.log; exit 1; }
export TMS_DEMO_PASSWORD=${TMS_DEMO_PASSWORD:-Demo-QA-Pass-4521x}
if [ "$3" == "--demo" ]; then $PY -m app.demo ${4:+--employees $4} | tee /tmp/qa/demo_$NAME.txt; fi
nohup $PY -m uvicorn app.main:app --host 127.0.0.1 --port $PORT --log-level warning > /home/user/training/qa/logs/server_$NAME.log 2>&1 &
echo $! > /tmp/qa/$NAME.pid
for i in $(seq 40); do curl -sf localhost:$PORT/health >/dev/null && break; sleep 0.5; done
echo started $NAME on $PORT pid $(cat /tmp/qa/$NAME.pid)
