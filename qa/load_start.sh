#!/bin/bash
. "$(dirname "$0")/env.sh"
export DATABASE_URL=${LOAD_DB:-sqlite:////tmp/qa/load.db} TMS_STORAGE_DIR=/tmp/qa/load-storage
cd $REPO/backend
nohup $PY -m uvicorn app.main:app --host 127.0.0.1 --port ${1:-18704} --workers ${2:-2} --log-level warning > /home/user/training/qa/logs/server_load.log 2>&1 &
echo $! > /tmp/qa/load.pid; sleep 3; curl -s localhost:${1:-18704}/ready
