"""Migration QA: fresh->head, head->base->head, 0001 with data -> head (0002 backfill), drift check, audit triggers survive.
usage: python migrations_test.py <sqlalchemy-url>   (run once for SQLite, once for PostgreSQL)"""
import sys, os, json
sys.path.insert(0, "/home/user/training/backend")
os.chdir("/home/user/training/backend")
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text, inspect
from app import db as dbm
import app.models  # noqa
url = sys.argv[1]
def cfg(): return dbm.alembic_config(url)
def rev():
    e = create_engine(url)
    with e.connect() as c: return c.execute(text("select version_num from alembic_version")).scalar()
def tables():
    return sorted(inspect(create_engine(url)).get_table_names())
def step(name, fn):
    try:
        fn(); print("PASS", name)
    except Exception as ex:
        print("FAIL", name, "->", type(ex).__name__, str(ex)[:300].replace("\n", " "))
from sqlalchemy.pool import NullPool
eng = create_engine(url, poolclass=NullPool)
def reset():
    if url.startswith("sqlite"):
        p = url.split("///", 1)[1]
        for s in ("", "-wal", "-shm"):
            try: os.remove(p + s)
            except FileNotFoundError: pass
    else:
        with eng.begin() as c:
            c.execute(text("drop schema public cascade")); c.execute(text("create schema public"))
reset()
step("fresh upgrade head", lambda: command.upgrade(cfg(), "head")); print("  rev:", rev(), "tables:", len(tables()))
def drift():
    with eng.connect() as c:
        diffs = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True, "compare_server_default": False}), dbm.Base.metadata)
    if diffs: raise AssertionError(f"{len(diffs)} drift items: {str(diffs)[:600]}")
step("models vs migrations drift (compare_type)", drift)
def drift_sd():
    with eng.connect() as c:
        diffs = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True, "compare_server_default": True}), dbm.Base.metadata)
    if diffs: raise AssertionError(f"{len(diffs)} items: {str(diffs)[:400]}")
step("drift incl. server_default (informational)", drift_sd)
step("downgrade base", lambda: command.downgrade(cfg(), "base")); print("  tables left:", [t for t in tables() if t != "alembic_version"])
step("upgrade head again", lambda: command.upgrade(cfg(), "head"))
# 0001 with data
reset()
step("upgrade to 0001", lambda: command.upgrade(cfg(), "0001"))
def seed():
    with eng.begin() as c:
        now = "2026-01-01 00:00:00"
        c.execute(text("insert into users(username,display_name,password_hash,role,is_active,created_at) values('u1','U','x','admin',true,:n)"), {"n": now})
        c.execute(text("insert into employees(emp_no,first_name_en,last_name_en,first_name_fa,last_name_fa,gender,email,mobile,national_code,date_of_birth,division,cost_center,org_code,position_title,supervisor_emp_no,status,source,updated_at) values('E1','A','B','','','','','v1.aaa','v1.bbb','v1.ccc','D','C','','','','Active','manual',:n)"), {"n": now})
        c.execute(text("insert into courses(name,name_fa,category,active,created_at) values('C1','','',true,:n)"), {"n": now})
        c.execute(text("insert into course_runs(run_key,course_id,type,days,time,sessions,section_b,status,link,payment_process,created_at) values('c1||2026-01-01',1,'in_person','','',0,'','planned','','',:n)"), {"n": now})
        c.execute(text("insert into enrollments(ticket,employee_id,run_id,course_name,category,delivery_method,idp_type,job_level,department,current_status,status,motivation,registration,calendar,attendance_status,payment,comment,section_b,level3_status,level3_sent,updated_at) values('LMS-1',1,1,'C1','','','','','','','requested','Yes','','','-','','','','',false,:n)"), {"n": now})
        c.execute(text("insert into audit_log(ts,actor,action,entity,entity_id,detail,ip) values(:n,'u1','x','','','{}','')"), {"n": now})
        c.execute(text("insert into connector_configs(kind,enabled,public,secrets,updated_at) values('smtp',true,'{}','v1.zzz',:n)"), {"n": now})
        c.execute(text("insert into sync_runs(source,status,started_at,created,updated,unchanged,skipped,errors,triggered_by) values('excel','ok',:n,0,0,0,0,'[]','')"), {"n": now})
step("seed data at 0001", seed)
step("upgrade 0001 -> head with data", lambda: command.upgrade(cfg(), "head"))
def check():
    with eng.connect() as c:
        offers = c.execute(text("select count(*) from enrollment_offers")).scalar()
        emp = c.execute(text("select mobile, national_code from employees")).one()
        msg = c.execute(text("select last_test_message from connector_configs")).scalar()
        sm = c.execute(text("select message from sync_runs")).scalar()
    assert offers == 1, f"backfill offers={offers}"
    assert emp == ("v1.aaa", "v1.bbb"), emp
    assert msg == "" and sm == "", (msg, sm)
step("data preserved + 0002 backfill + 0003 defaults", check)
def trig():
    with eng.begin() as c:
        try:
            c.execute(text("update audit_log set action='y'"))
        except Exception as e:
            return
        raise AssertionError("audit UPDATE was allowed after migration")
step("audit UPDATE blocked after upgrade-with-data", trig)
def trig2():
    with eng.begin() as c:
        try: c.execute(text("delete from audit_log"))
        except Exception: return
        raise AssertionError("audit DELETE allowed")
step("audit DELETE blocked", trig2)
if not url.startswith("sqlite"):
    def trunc():
        with eng.begin() as c:
            try: c.execute(text("truncate audit_log"))
            except Exception: return
            raise AssertionError("TRUNCATE allowed")
    step("audit TRUNCATE blocked (PG)", trunc)
step("downgrade head -> 0001 with data", lambda: command.downgrade(cfg(), "0001"))
step("re-upgrade head", lambda: command.upgrade(cfg(), "head"))
# downgrade to base with an audit row: documented as destructive; does the trigger get in the way?
step("downgrade base with audit rows present", lambda: command.downgrade(cfg(), "base"))
step("upgrade head after that", lambda: command.upgrade(cfg(), "head"))
print("final rev:", rev())
