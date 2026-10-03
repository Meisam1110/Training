#!/bin/bash
# Index of QA scripts (each is self-contained; servers use scratch DBs under /tmp/qa, ports 18700-18705, PG 55432).
#   ./mkserver.sh main 18700 --demo 60        SQLite scratch app + synthetic demo data (logins demo_*/Demo-QA-Pass-4521x)
#   ./mkserver.sh imp 18701                   empty app (bootstrap admin qaadmin) for import/letter edge tests
#   DATABASE_URL=postgresql+psycopg://tms@127.0.0.1:55432/tms_app ./mkserver.sh pg 18702 --demo 60
#   ../.venv/bin/python smtp_sink.py 18025 &  (aiosmtpd sink)   |  python -m app.integrations.ifs.mock_server --port 18099 &  |  python faulty_ifs.py &
. "$(dirname "$0")/env.sh"; cd "$(dirname "$0")"; PYQ=$REPO/.venv/bin/python
$PYQ rbac_matrix.py; $PYQ sec_login.py; $PYQ sec_api.py; $PYQ probe_overflow.py; $PYQ upload_attacks.py; $PYQ imp_test.py; $PYQ export_inject.py
$PYQ email_e2e.py; $PYQ email_pending.py; $PYQ db_inspect.py; $PYQ ifs_e2e.py; $PYQ ifs_faults.py; $PYQ letters_e2e.py; $PYQ letters_edge.py
$PYQ level3_loop.py; $PYQ manual_edit_sync.py; $PYQ numbering_conc.py http://127.0.0.1:18700 30; $PYQ pg_specific.py; $PYQ proxy_ip_lockout.py
$PYQ migrations_test.py sqlite:////tmp/qa/mig.db; $PYQ migrations_test.py postgresql+psycopg://tms@127.0.0.1:55432/tms_mig
$PYQ prod_config.py; ./prod_probe.sh; bash rekey_backup.sh; $PYQ watcher_test.py; $PYQ tests/template_injection_probe.py
$PYQ /tmp/qa/tools/bin/python jalali_check.py 2>/dev/null || /tmp/qa/tools/bin/python jalali_check.py     # needs jdatetime+convertdate in a scratch venv
$PYQ build_load.py; ./load_start.sh; $PYQ load_test.py http://127.0.0.1:18704 50 25; $PYQ nplus1.py; ./sched_start.sh    # load / scheduler with 2 workers
$PYQ privacy_scan.py     # ground truth from /root/.claude/uploads (values stay in /tmp/qa/truth, only counts printed)
$PYQ -m pytest tests -o addopts="" -p no:cacheprovider    # reproduced findings: every failing test = a finding in docs/QA_REPORT.md
