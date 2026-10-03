"""Deterministic SYNTHETIC demo data. No real person appears here: names are drawn from small
generic lists, national codes start with 999 (not a valid range), mobiles with 0990, e-mails
are @example.test. Same seed + same ``today`` => same data.

    python -m app.demo [--reset] [--employees 60] [--seed 1]
"""
from __future__ import annotations

import argparse
import os
import random
import secrets
import sys
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import db as dbm
from app.auth.passwords import hash_password
from app.config import ensure_dev_key, load_settings
from app.models import Course, CourseRun, Employee, Enrollment, Institute, User
from app.security import crypto

FIRST = [("Ali", "علی", "male"), ("Sara", "سارا", "female"), ("Reza", "رضا", "male"), ("Maryam", "مریم", "female"),
         ("Hamid", "حمید", "male"), ("Neda", "ندا", "female"), ("Omid", "امید", "male"), ("Laleh", "لاله", "female"),
         ("Kian", "کیان", "male"), ("Mina", "مینا", "female"), ("Farid", "فرید", "male"), ("Roya", "رویا", "female")]
LAST = [("Sample", "نمونه"), ("Testi", "آزمایشی"), ("Demo", "دمو"), ("Fakeh", "ساختگی"), ("Mock", "فرضی"),
        ("Alpha", "الفا"), ("Sigma", "سیگما"), ("Delta", "دلتا"), ("Omega", "امگا"), ("Nova", "نووا")]
DIVISIONS = ["Technology", "Finance", "Marketing", "Customer Care", "Human Resources", "Operations"]
COURSES = [("Effective Communication", "ارتباط مؤثر", "Soft Skill", 16), ("Leadership Basics", "مبانی رهبری", "Soft Skill", 24),
           ("Project Management", "مدیریت پروژه", "Technical", 40), ("Data Analysis", "تحلیل داده", "Technical", 32),
           ("Time Management", "مدیریت زمان", "Soft Skill", 8), ("Negotiation Skills", "مهارت‌های مذاکره", "Soft Skill", 16)]
INSTITUTES = [("Demo Academy", "آکادمی دمو", "SUP-001"), ("Sample Training Co", "شرکت آموزشی نمونه", "SUP-002")]


def generate(sf: sessionmaker[Session], employees: int = 60, seed: int = 1, today: date | None = None) -> dict:
    rng = random.Random(seed)
    today = today or date.today()
    with sf() as db:
        if db.scalar(select(Employee.id).where(Employee.source == "demo").limit(1)):
            return {"employees": 0, "runs": 0, "enrollments": 0}      # already loaded: idempotent
        insts = []
        for n, fa, code in INSTITUTES:
            i = db.scalar(select(Institute).where(Institute.name == n)) or Institute(name=n, name_fa=fa, supplier_code=code)
            db.add(i)
            insts.append(i)
        courses = []
        for n, fa, cat, h in COURSES:
            c = db.scalar(select(Course).where(Course.name == n)) or Course(name=n, name_fa=fa, category=cat, default_duration_h=h)
            db.add(c)
            courses.append(c)
        db.flush()
        emps: list[Employee] = []
        managers = max(1, employees // 8)
        for n in range(1, employees + 1):
            emp_no = f"D{n:05d}"
            if db.scalar(select(Employee.id).where(Employee.emp_no == emp_no)):
                continue
            fe, ff, g = rng.choice(FIRST)
            le, lf = rng.choice(LAST)
            e = Employee(
                emp_no=emp_no, first_name_en=fe, last_name_en=f"{le}{n}", first_name_fa=ff, last_name_fa=f"{lf}{n}", gender=g,
                email=f"{fe.lower()}.{le.lower()}{n}@example.test", mobile=f"0990{rng.randint(0, 9999999):07d}",
                national_code=f"999{rng.randint(0, 9999999):07d}",
                date_of_birth=(date(1975, 1, 1) + timedelta(days=rng.randint(0, 9000))).isoformat(),
                division=rng.choice(DIVISIONS), cost_center=f"CC{rng.randint(100, 199)}",
                org_code=f"ORG{rng.randint(10, 99)}", position_title="Specialist",
                supervisor_emp_no="" if n <= managers else f"D{rng.randint(1, managers):05d}",
                status="Active" if rng.random() > 0.05 else "Terminated", source="demo")
            db.add(e)
            emps.append(e)
        db.flush()
        created_emps = len(emps)
        emps = emps or list(db.scalars(select(Employee).where(Employee.source == "demo")))
        runs = []
        offsets = [-70, -30, -5, 12, 25, 45]
        for k, off in enumerate(offsets):
            c, inst = courses[k % len(courses)], insts[k % len(insts)]
            start = today + timedelta(days=off)
            key = f"{c.name}|{inst.name}|{start}".casefold()
            r = db.scalar(select(CourseRun).where(CourseRun.run_key == key))
            if r is None:
                r = CourseRun(run_key=key, course_id=c.id, institute_id=inst.id, type="online" if k % 3 == 0 else "in_person",
                              duration_h=c.default_duration_h, start_date=start, end_date=start + timedelta(days=2), days="Sat-Sun",
                              time="09:00-16:00", sessions=3, send_date=start - timedelta(days=20), deadline=start - timedelta(days=7),
                              amount=rng.choice([120_000_000, 240_000_000, 360_000_000]), section_b=f"MTC-{100000 + k}",
                              status="completed" if off < -10 else ("running" if off < 0 else "announced"))
                db.add(r)
            runs.append(r)
        db.flush()
        n_en = 0
        for i, e in enumerate(emps):
            for j in range(rng.randint(1, 3)):
                c = courses[(i + j) % len(courses)]
                r = runs[(i + j) % len(runs)] if rng.random() < 0.6 else None
                ticket = f"LMS-{700000 + i * 10 + j}"
                if db.scalar(select(Enrollment.id).where(Enrollment.ticket == ticket)):
                    continue
                past = r is not None and r.end_date < today
                level3 = past and (today - r.end_date).days > 60 and c.category == "Soft Skill"
                db.add(Enrollment(
                    ticket=ticket, employee_id=e.id, run_id=r.id if r else None,
                    course_name=f"{c.name} - {rng.choice(['Batch A', 'Batch B'])}", category=c.category,
                    delivery_method=rng.choice(["Online", "In-person"]), idp_type="Yearly", job_level=f"L{rng.randint(1, 5)}",
                    department=e.division if rng.random() > 0.05 else "Other Division",
                    current_status="Evaluation Level 3" if level3 else "Approved",
                    motivation=rng.choice(["Yes", "Yes", "No", ""]) if r else "",
                    attendance_status="Attended" if past else "-", start_date=r.start_date if r else None,
                    end_date=r.end_date if r else None, section_b=r.section_b if r else ""))
                n_en += 1
        db.commit()
        return {"employees": created_emps, "runs": len(runs), "enrollments": n_en}


def ensure_users(sf: sessionmaker[Session]) -> dict[str, str]:
    """Demo accounts. Passwords are random per run (printed once) unless TMS_DEMO_PASSWORD is set."""
    pw = os.environ.get("TMS_DEMO_PASSWORD") or secrets.token_urlsafe(12) + "-Aa1"
    made = {}
    with sf() as db:
        for role in ("admin", "hr", "viewer"):
            name = f"demo_{role}"
            if not db.scalar(select(User.id).where(User.username == name)):
                db.add(User(username=name, role=role, display_name=f"Demo {role}", password_hash=hash_password(pw)))
                made[name] = pw
        db.commit()
    return made


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--employees", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--reset", action="store_true", help="delete the (SQLite dev) database first")
    ap.add_argument("--force", action="store_true", help="allow TMS_ENV=production (never do this)")
    a = ap.parse_args(argv)
    s = load_settings()
    if s.is_production and not a.force:
        print("refusing to load demo data in production", file=sys.stderr)
        return 2
    s = ensure_dev_key(s)
    if a.reset and s.is_sqlite:
        path = s.database_url.split("///", 1)[-1]
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
    crypto.configure(s.data_keys())
    dbm.upgrade_to_head(s.database_url)
    engine = dbm.make_engine(s.database_url)
    sf = dbm.make_session_factory(engine)
    stats = generate(sf, a.employees, a.seed)
    made = ensure_users(sf)
    print(f"demo data: {stats}")
    for u, p in made.items():
        print(f"  login {u} / {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
