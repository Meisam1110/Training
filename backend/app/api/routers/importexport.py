from __future__ import annotations

import dataclasses
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from starlette.background import BackgroundTask

from app.api.errors import forbidden, validation
from app.api.services import gateway, sync, upsert
from app.api.services import serializers as ser
from app.audit import record as audit
from app.config import Settings
from app.contracts import EmployeeRecord, IdpRow, LegacyData, RecordRow, RunRecord
from app.deps import client_ip, get_db, get_settings, require
from app.models import CourseRun, Employee, Enrollment, User

router = APIRouter(tags=["import-export"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _tmpdir(settings: Settings) -> Path:
    d = settings.storage_path / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_upload(f: UploadFile, settings: Settings) -> Path:
    name = (f.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise validation("انتقال اطلاعات: فقط فایل xlsx پذیرفته می‌شود", file="فقط xlsx")
    path = _tmpdir(settings) / f"up-{uuid.uuid4().hex}.xlsx"
    size, head = 0, b""
    with open(path, "wb") as out:
        while chunk := f.file.read(1 << 20):
            head = head or chunk[:4]
            size += len(chunk)
            if size > settings.max_upload_bytes:
                out.close()
                path.unlink(missing_ok=True)
                raise validation("انتقال اطلاعات: حجم فایل بیش از حد مجاز است", file="حجم زیاد")
            out.write(chunk)
    if size == 0 or head[:2] != b"PK":
        path.unlink(missing_ok=True)
        raise validation("انتقال اطلاعات: فایل xlsx معتبر نیست", file="xlsx نیست")
    try:
        check_xlsx(path, settings)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def check_xlsx(path: Path, settings: Settings) -> None:
    """Reject before parsing: structure, member count, DECOMPRESSED size and expansion ratio (zip bombs).
    The compressed-size cap alone let a 1 MiB file expand to 300 MB and keep a worker busy for a minute."""
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            names = {i.filename for i in infos}
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise validation("انتقال اطلاعات: فایل xlsx معتبر نیست", file="کارپوشهٔ xlsx معتبر نیست")
            if len(infos) > 2000 or any(i.filename.startswith(("/", "..")) or ".." in i.filename.split("/") for i in infos):
                raise validation("انتقال اطلاعات: ساختار فایل xlsx مجاز نیست", file="ساختار بایگانی نامعتبر است")
            total = sum(i.file_size for i in infos)
            comp = max(sum(i.compress_size for i in infos), 1)
            if total > settings.max_xlsx_uncompressed_bytes or total / comp > settings.max_xlsx_ratio:
                raise validation("انتقال اطلاعات: حجم بازشدهٔ فایل xlsx از سقف مجاز بیشتر است", file="سقف حجم بازشده یا نسبت فشرده‌سازی")
    except zipfile.BadZipFile:
        raise validation("انتقال اطلاعات: فایل xlsx معتبر نیست", file="بایگانی خراب است") from None


def _finish(request: Request, response: Response, db: Session, user: User, run, action: str):
    audit(db, action, user=user, entity="sync", entity_id=run.id, ip=client_ip(request))
    db.commit()
    if run.status == "running":
        response.status_code = 202          # big import: still running in the background, poll GET /sync/runs
    return ser.sync_run(run)


@router.post("/import/idp")
def import_idp(file: UploadFile, request: Request, response: Response, db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings), user: User = Depends(require("hr"))):
    path = _save_upload(file, settings)

    def work(wdb: Session, rep) -> None:
        upsert.upsert_idp(wdb, gateway.get_factory().build_excel_gateway().read_idp(str(path)), rep)

    run = sync.execute(db, request.app.state.session_factory, settings, "idp", work, user.username, cleanup=lambda: path.unlink(missing_ok=True))
    return _finish(request, response, db, user, run, "import.idp")


@router.post("/import/legacy-workbook")
def import_legacy(file: UploadFile, request: Request, response: Response, db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings), user: User = Depends(require("hr"))):
    path = _save_upload(file, settings)

    def work(wdb: Session, rep) -> None:
        upsert.upsert_legacy(wdb, gateway.get_factory().build_excel_gateway().read_legacy(str(path)), rep)

    run = sync.execute(db, request.app.state.session_factory, settings, "legacy", work, user.username,
                       cleanup=lambda: path.unlink(missing_ok=True))
    return _finish(request, response, db, user, run, "import.legacy")


_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def neutralize(v):
    """Spreadsheet formula injection: text that starts with = + - @ TAB CR is prefixed with an apostrophe so
    Excel/LibreOffice show it as text. A lone "-" (the IDP 'no attendance' marker) is not a formula and is kept."""
    if isinstance(v, str) and v and v != "-" and v[0] in _FORMULA:
        return "'" + v
    return v


def neutralize_obj(o):
    return dataclasses.replace(o, **{f.name: neutralize(getattr(o, f.name)) for f in dataclasses.fields(o)
                                     if isinstance(getattr(o, f.name), str)})


@router.get("/export/legacy.xlsx")
def export_legacy(request: Request, include_pii: int = Query(0, ge=0, le=1), db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings), user: User = Depends(require("hr"))):
    """National code and mobile are left blank unless ``include_pii=1`` (admin only): a bulk PII dump is a deliberate,
    audited admin action, not one click for every HR user."""
    if include_pii and user.role != "admin":
        raise forbidden("انتقال اطلاعات: خروجی شامل اطلاعات شخصی فقط برای مدیر سامانه مجاز است")
    data = LegacyData()
    for e in db.scalars(select(Employee).order_by(Employee.emp_no)):
        data.employees.append(EmployeeRecord(
            emp_no=e.emp_no, first_name_en=e.first_name_en, last_name_en=e.last_name_en, first_name_fa=e.first_name_fa,
            last_name_fa=e.last_name_fa, gender=e.gender if e.gender in ("male", "female") else "", email=e.email,
            mobile=(e.mobile or "") if include_pii else "", national_code=(e.national_code or "") if include_pii else "",
            division=e.division, cost_center=e.cost_center, org_code=e.org_code, position_title=e.position_title,
            supervisor_emp_no=e.supervisor_emp_no, status=e.status))
    for r in db.scalars(select(CourseRun).options(joinedload(CourseRun.course), joinedload(CourseRun.institute)).order_by(CourseRun.id)):
        data.runs.append(RunRecord(
            course_name=r.course.name, course_name_fa=r.course.name_fa, type=r.type if r.type in ("online", "in_person") else "in_person",
            institute=r.institute.name if r.institute else "", duration_h=float(r.duration_h or 0), start_date=r.start_date,
            end_date=r.end_date, days=r.days, time=r.time, sessions=r.sessions, send_date=r.send_date, deadline=r.deadline,
            amount=float(r.amount) if r.amount is not None else None, section_b=r.section_b, link=r.link))
    q = select(Enrollment).options(joinedload(Enrollment.employee), joinedload(Enrollment.run).joinedload(CourseRun.institute))
    for en in db.scalars(q.order_by(Enrollment.id)).unique():
        ru = en.run
        data.idp.append(IdpRow(
            emp_no=en.employee.emp_no, reporter_name=f"{en.employee.first_name_en} {en.employee.last_name_en}".strip(),
            job_level=en.job_level, department=en.department, summary=en.course_name, delivery_method=en.delivery_method,
            current_status=en.current_status, idp_type=en.idp_type, course_category=en.category,
            attendance_status=en.attendance_status, start_date=en.start_date, end_date=en.end_date, ticket=en.ticket,
            section_b=en.section_b or "-"))
        data.records.append(RecordRow(
            emp_no=en.employee.emp_no, ticket=en.ticket, course_name=en.course_name,
            institute=(ru.institute.name if ru and ru.institute else ""), start_date=ru.start_date if ru else en.start_date,
            motivation=en.motivation, registration=en.registration, calendar=en.calendar, payment=en.payment, comment=en.comment))
    data.employees = [neutralize_obj(x) for x in data.employees]
    data.runs = [neutralize_obj(x) for x in data.runs]
    data.idp = [neutralize_obj(x) for x in data.idp]
    data.records = [neutralize_obj(x) for x in data.records]
    path = _tmpdir(settings) / f"exp-{uuid.uuid4().hex}.xlsx"
    try:
        gateway.get_factory().build_excel_gateway().write_legacy(data, str(path))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    audit(db, "export.legacy", user=user, entity="export", ip=client_ip(request),
          detail={"employees": len(data.employees), "pii_included": bool(include_pii)})
    db.commit()
    return FileResponse(path, filename="legacy.xlsx", media_type=XLSX, background=BackgroundTask(lambda: path.unlink(missing_ok=True)))
