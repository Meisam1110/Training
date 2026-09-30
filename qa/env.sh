# source this: QA scratch environment (own DB under /tmp/qa, never shared)
export QA_ROOT=/tmp/qa
export REPO=${REPO:-/home/user/training}
export PY=${PY:-$REPO/.venv/bin/python}
export TMS_ENV=development
export TMS_STORAGE_DIR=${TMS_STORAGE_DIR:-$QA_ROOT/storage}
export TMS_DATA_KEY=$(python3 -c "import base64,os;print(base64.b64encode(bytes(range(7,39))).decode())")
export TMS_SECRET_KEY=qa-secret-key-0123456789-abcdefghijklmnop
export TMS_BOOTSTRAP_ADMIN_USER=qaadmin
export TMS_BOOTSTRAP_ADMIN_PASSWORD='Qa-Admin-Pass-9137!x'
export DATABASE_URL=${DATABASE_URL:-sqlite:////tmp/qa/qa.db}
export QA_DEMO_PW=Demo-QA-Pass-4521x
