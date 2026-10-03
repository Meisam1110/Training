#!/bin/bash
. "$(dirname "$0")/env.sh"
export DATABASE_URL=sqlite:////tmp/qa/sched.db TMS_STORAGE_DIR=/tmp/qa/sched-storage TMS_AUTOMATION_ENABLED=true TMS_AUTOMATION_INTERVAL_S=60
rm -rf /tmp/qa/sched.db* $TMS_STORAGE_DIR; mkdir -p $TMS_STORAGE_DIR; cd $REPO/backend
$PY -m alembic upgrade head > /dev/null 2>&1; $PY -m app.demo >/dev/null 2>&1
nohup $PY -m uvicorn app.main:app --host 127.0.0.1 --port 18703 --workers 2 --log-level warning > /home/user/training/qa/logs/server_sched.log 2>&1 &
echo $! > /tmp/qa/sched.pid; echo started $(date +%T)
