from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.errors import forbidden, not_found
from app.api.pagination import PageParams, apply_sort, like, paginate
from app.api.services import serializers as ser
from app.audit import record as audit
from app.deps import RANK, client_ip, get_db, require
from app.models import Employee, User

router = APIRouter(prefix="/employees", tags=["employees"])
SORT = {"emp_no": Employee.emp_no, "last_name_en": Employee.last_name_en, "first_name_en": Employee.first_name_en,
        "division": Employee.division, "status": Employee.status}


@router.get("")
def list_employees(p: PageParams = Depends(), division: str = Query("", max_length=200), status: str = Query("", max_length=32),
                   supervisor: str = Query("", max_length=32), db: Session = Depends(get_db), _=Depends(require("viewer"))):
    stmt = select(Employee)
    if p.q:
        k = like(p.q)
        stmt = stmt.where(or_(*[c.ilike(k, escape="\\") for c in (Employee.emp_no, Employee.first_name_en, Employee.last_name_en,
                                                              Employee.first_name_fa, Employee.last_name_fa, Employee.email,
                                                              Employee.division)]))
    if division:
        stmt = stmt.where(Employee.division == division)
    if status:
        stmt = stmt.where(Employee.status == status)
    if supervisor:
        stmt = stmt.where(Employee.supervisor_emp_no == supervisor)
    return paginate(db, apply_sort(stmt, p.sort, SORT, "emp_no"), p, ser.employee)


@router.get("/{emp_no}")
def get_employee(emp_no: Annotated[str, Path(min_length=1, max_length=32, pattern=r"^[^\x00]+$")], request: Request,
                 reveal: int = Query(0, ge=0, le=1), db: Session = Depends(get_db), user: User = Depends(require("viewer"))):
    e = db.scalar(select(Employee).where(Employee.emp_no == emp_no))
    if not e:
        raise not_found("کارمند")
    if reveal:
        if RANK[user.role] < RANK["hr"]:
            raise forbidden("مشاهده اطلاعات شخصی فقط برای مدیر و منابع انسانی مجاز است")
        audit(db, "employee.reveal", user=user, entity="employee", entity_id=e.emp_no, ip=client_ip(request),
              detail={"fields": ["national_code", "mobile", "date_of_birth"]})
        db.commit()
    return ser.employee(e, reveal=bool(reveal), detail=True)
