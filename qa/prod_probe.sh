#!/bin/bash
. "$(dirname "$0")/env.sh"
export TMS_ENV=production DATABASE_URL=sqlite:////tmp/qa/prod.db TMS_STORAGE_DIR=/tmp/qa/prod-storage TMS_HSTS=true
export TMS_DATA_KEY=$(openssl rand -base64 32) TMS_SECRET_KEY=$(openssl rand -base64 48) TMS_BOOTSTRAP_ADMIN_USER=prodadmin TMS_BOOTSTRAP_ADMIN_PASSWORD='Pr0d-Adm1n-Str0ng-Pass!'
rm -rf /tmp/qa/prod.db* /tmp/qa/prod-storage; mkdir -p $TMS_STORAGE_DIR; cd $REPO/backend
$PY -m alembic upgrade head >/dev/null 2>&1
TMS_STATIC_ROOT=/home/user/training/frontend/dist nohup $PY -m uvicorn app.main:app --host 127.0.0.1 --port 18705 --log-level warning > /home/user/training/qa/logs/server_prod.log 2>&1 &
echo $! > /tmp/qa/prod.pid; sleep 3
echo "--- login"; curl -si -X POST localhost:18705/api/v1/auth/login -H 'content-type: application/json' -d '{"username":"prodadmin","password":"Pr0d-Adm1n-Str0ng-Pass!"}' | grep -iE "^HTTP|set-cookie|strict-transport"
echo "--- docs/openapi"; curl -s -o /dev/null -w "%{http_code} " localhost:18705/api/docs; curl -s -o /dev/null -w "%{http_code}\n" localhost:18705/api/openapi.json
echo "--- SPA"; curl -si localhost:18705/ | grep -iE "^HTTP|content-type|content-security|cache-control|x-frame"
echo "--- SPA deep link (history fallback?)"; curl -s -o /dev/null -w "%{http_code}\n" localhost:18705/some/route
echo "--- static traversal"; curl -s --path-as-is -o /dev/null -w "%{http_code} " "localhost:18705/../../etc/passwd"; curl -s --path-as-is -o /dev/null -w "%{http_code} " "localhost:18705/%2e%2e/%2e%2e/etc/passwd"; curl -s --path-as-is -o /dev/null -w "%{http_code}\n" "localhost:18705/assets/..%2f..%2fpackage.json"
echo "--- Host header / trusted hosts"; curl -s -o /dev/null -w "%{http_code}\n" -H 'Host: evil.example' localhost:18705/health
echo "--- health leak"; curl -s localhost:18705/ready
