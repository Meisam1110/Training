"""Build the load-test DB: 5000 employees (demo generator), ~10k IDP requests, 300 runs. usage: build_load.py (env: DATABASE_URL, TMS_DATA_KEY)"""
import sys, random, time
sys.path.insert(0, "/home/user/training/backend")
from datetime import date, timedelta
from sqlalchemy import select
from app import db as dbm
from app.config import load_settings, ensure_dev_key
from app.security import crypto
from app.models import Course, CourseRun, Institute, Enrollment, Employee
from app import demo
s = ensure_dev_key(load_settings()); crypto.configure(s.data_keys())
dbm.upgrade_to_head(s.database_url); eng = dbm.make_engine(s.database_url); sf = dbm.make_session_factory(eng)
t = time.time(); print(demo.generate(sf, 5000), round(time.time() - t, 1), "s")
print(demo.ensure_users(sf))
rng = random.Random(7)
with sf() as db:
    courses = list(db.scalars(select(Course))); insts = list(db.scalars(select(Institute)))
    emps = list(db.scalars(select(Employee.id).limit(5000)))
    today = date.today(); n = 0
    for k in range(294):
        c, i = courses[k % len(courses)], insts[k % len(insts)]
        start = today + timedelta(days=rng.randint(-400, 300))
        r = CourseRun(run_key=f"{c.name}|{i.name}|{start}|{k}".casefold(), course_id=c.id, institute_id=i.id, type="in_person", duration_h=16, start_date=start,
                      end_date=start + timedelta(days=2), days="Sat", time="09:00-16:00", sessions=3, deadline=start - timedelta(days=7), amount=120_000_000,
                      section_b=f"MTC-{2000+k}", status="planned")
        db.add(r); db.flush()
        for e in rng.sample(emps, 8):
            db.add(Enrollment(ticket=f"LMS-{900000 + k*10 + (e % 10)}-{e}", employee_id=e, run_id=r.id, course_name=c.name, category=c.category, motivation="Yes", attendance_status="-", start_date=start, end_date=start + timedelta(days=2))); n += 1
    db.commit(); print("extra runs 294, enrollments", n)
    print({t.name: db.scalar(select(__import__("sqlalchemy").func.count()).select_from(t)) for t in (Employee.__table__, CourseRun.__table__, Enrollment.__table__)})
