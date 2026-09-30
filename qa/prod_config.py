"""Production-mode start-up enforcement: run `python -c create_app()` in a subprocess with each env combination."""
import subprocess, os, sys, base64
PY = "/home/user/training/.venv/bin/python"
good_key = base64.b64encode(os.urandom(32)).decode(); good_sec = base64.urlsafe_b64encode(os.urandom(48)).decode()
def run(name, env, expect_fail):
    e = {"PATH": os.environ["PATH"], "TMS_STORAGE_DIR": "/tmp/qa/prod-storage", "DATABASE_URL": "sqlite:////tmp/qa/prod.db", **env}
    r = subprocess.run([PY, "-c", "import sys; sys.path.insert(0,'/home/user/training/backend'); from app.main import create_app; create_app(); print('STARTED')"],
                       env=e, capture_output=True, text=True, cwd="/home/user/training/backend")
    started = "STARTED" in r.stdout
    ok = (not started) if expect_fail else started
    print(("PASS" if ok else "FAIL"), f"{name:58s}", "started" if started else "refused:", (r.stderr.strip().splitlines() or [''])[-1][:110] if not started else "")
P = {"TMS_ENV": "production"}
run("prod, no keys", P, True)
run("prod, key ok, no secret", {**P, "TMS_DATA_KEY": good_key}, True)
run("prod, weak secret 'changeme...' (>=32)", {**P, "TMS_DATA_KEY": good_key, "TMS_SECRET_KEY": "changeme-changeme-changeme-changeme"}, True)
run("prod, short secret", {**P, "TMS_DATA_KEY": good_key, "TMS_SECRET_KEY": "abc123XYZ"}, True)
run("prod, weak data key (all zero bytes)", {**P, "TMS_DATA_KEY": base64.b64encode(bytes(32)).decode(), "TMS_SECRET_KEY": good_sec}, True)
run("prod, data key wrong length", {**P, "TMS_DATA_KEY": base64.b64encode(b"x" * 16).decode(), "TMS_SECRET_KEY": good_sec}, True)
run("prod, CORS *", {**P, "TMS_DATA_KEY": good_key, "TMS_SECRET_KEY": good_sec, "TMS_CORS_ORIGINS": "*"}, True)
run("prod, weak bootstrap pw", {**P, "TMS_DATA_KEY": good_key, "TMS_SECRET_KEY": good_sec, "TMS_BOOTSTRAP_ADMIN_PASSWORD": "admin", "TMS_BOOTSTRAP_ADMIN_USER": "admin"}, True)
run("prod, bootstrap pw 'Password123456' (12+ chars, common)", {**P, "TMS_DATA_KEY": good_key, "TMS_SECRET_KEY": good_sec, "TMS_BOOTSTRAP_ADMIN_PASSWORD": "Password123456"}, True)
run("prod, bootstrap pw '111111111111a' (low entropy)", {**P, "TMS_DATA_KEY": good_key, "TMS_SECRET_KEY": good_sec, "TMS_BOOTSTRAP_ADMIN_PASSWORD": "111111111111a"}, True)
run("prod, good config", {**P, "TMS_DATA_KEY": good_key, "TMS_SECRET_KEY": good_sec}, False)
run("prod, good + missing bootstrap password (no admin)", {**P, "TMS_DATA_KEY": good_key, "TMS_SECRET_KEY": good_sec, "TMS_BOOTSTRAP_ADMIN_USER": "admin"}, False)
run("TMS_ENV typo 'prod'", {"TMS_ENV": "prod"}, True)
run("TMS_ENV unset (development default) with no keys", {}, False)
