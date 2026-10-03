"""Model -> JSON dict. Personal data is masked here unless ``reveal`` is explicitly set."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.models import AuditLog, ConnectorConfig, Course, CourseRun, Employee, Enrollment, Letter, MessageLog, SyncRun, User
from app.security.masking import mask_date, mask_mobile, mask_national_code

SECRET_KEYS_BY_KIND = {"excel": set(), "ifs": {"client_secret", "password"}, "smtp": {"password"},
                       "graph": {"client_secret"}}
_STATIC_KEYS = {
    "excel": {"path", "watch_dir", "idp_path", "sheet"},
    "ifs": {"base_url", "auth_mode", "client_id", "client_secret", "token_url", "scope", "username", "password", "login_url",
            "login_user_field", "login_password_field", "verify_tls", "ca_bundle", "timeout_s", "employees_path", "page_size",
            "max_retries", "backoff_base_s", "backoff_max_s", "breaker_threshold", "breaker_cooldown_s", "modified_field",
            "delta_mode", "active_statuses", "field_map"},
    "smtp": {"host", "port", "username", "password", "from_addr", "from_name", "starttls", "use_ssl", "timeout_s", "ca_bundle",
             "verify_tls", "rate_limit_per_min", "allow_private_hosts"},
    "graph": {"tenant_id", "client_id", "client_secret", "sender", "authority_url", "graph_url", "save_to_sent_items", "timeout_s",
              "verify_tls", "rate_limit_per_min", "allow_private_hosts"},
}


def allowed_keys(kind: str) -> set[str]:
    """What the connector actually reads. IFS is derived from Dev-B's IfsConfig dataclass (so a new option there is
    accepted automatically); the other kinds are explicit lists that tests/core keep in step with the sources."""
    keys = set(_STATIC_KEYS[kind])
    if kind == "ifs":
        try:
            import dataclasses

            from app.integrations.ifs.config import IfsConfig
            keys |= {f.name for f in dataclasses.fields(IfsConfig)}
        except ImportError:   # pragma: no cover - integrations not installed
            pass
    return keys


ALLOWED_KEYS_BY_KIND = {k: allowed_keys(k) for k in _STATIC_KEYS}


def iso(d: Any) -> str | None:
    return d.isoformat() if d else None


def num(x: Any) -> float | None:
    return None if x is None else float(x)


def user(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "email": u.email or "", "role": u.role,
            "is_active": u.is_active, "created_at": iso(u.created_at), "last_login_at": iso(u.last_login_at)}


def employee(e: Employee, reveal: bool = False, detail: bool = False) -> dict:
    d = {
        "emp_no": e.emp_no, "first_name_en": e.first_name_en, "last_name_en": e.last_name_en,
        "first_name_fa": e.first_name_fa, "last_name_fa": e.last_name_fa, "gender": e.gender,
        "email": e.email, "division": e.division, "cost_center": e.cost_center, "org_code": e.org_code,
        "position_title": e.position_title, "supervisor_emp_no": e.supervisor_emp_no, "status": e.status,
        "source": e.source,
        "mobile": (e.mobile or "") if reveal else mask_mobile(e.mobile),
        "national_code": (e.national_code or "") if reveal else mask_national_code(e.national_code),
        "revealed": reveal,
    }
    if detail:
        d["date_of_birth"] = (e.date_of_birth or "") if reveal else mask_date(e.date_of_birth)
    return d


def course(c: Course) -> dict:
    return {"id": c.id, "name": c.name, "name_fa": c.name_fa, "category": c.category,
            "default_duration_h": num(c.default_duration_h), "active": c.active}


def run(r: CourseRun, today: date | None = None, counts: dict[str, int] | None = None) -> dict:
    d = {
        "id": r.id, "course_id": r.course_id, "course_name": r.course.name, "course_name_fa": r.course.name_fa,
        "type": r.type, "delivery_type": r.type, "institute": r.institute.name if r.institute else "", "institute_id": r.institute_id,
        "duration_h": num(r.duration_h), "start_date": iso(r.start_date), "end_date": iso(r.end_date),
        "days": r.days, "time": r.time, "sessions": r.sessions, "send_date": iso(r.send_date),
        "deadline": iso(r.deadline), "amount": num(r.amount), "section_b": r.section_b, "status": r.status,
        "link": r.link, "payment_process": r.payment_process,
        "pr_process_start_date": iso(r.pr_process_start_date),
        "invoice_receive_date": iso(r.invoice_receive_date), "run_key": r.run_key,
        "days_to_course": (r.start_date - today).days if (today and r.start_date) else None,
    }
    if counts is not None:
        d.update(counts, enrollment_count=counts["participants"], motivation_yes=counts["motivations_yes"])   # old names kept
    return d


class SupervisorEmails:
    """Lazy emp_no -> e-mail lookup with a per-request cache (avoids a join in every list query)."""

    def __init__(self, db):
        self.db, self.cache = db, {}

    def prefetch(self, emp_nos) -> None:
        need = {n for n in emp_nos if n and n not in self.cache}
        if need:
            from sqlalchemy import select
            found = dict(self.db.execute(select(Employee.emp_no, Employee.email).where(Employee.emp_no.in_(need))).all())
            for n in need:
                self.cache[n] = found.get(n, "") or ""

    def __call__(self, emp_no: str) -> str:
        if not emp_no:
            return ""
        if emp_no not in self.cache:
            from sqlalchemy import select
            self.cache[emp_no] = self.db.scalar(select(Employee.email).where(Employee.emp_no == emp_no)) or ""
        return self.cache[emp_no]


def enrollment(e: Enrollment, ticket_base: str = "", sup_email=None) -> dict:
    emp = e.employee
    return {
        "email": emp.email, "supervisor_emp_no": emp.supervisor_emp_no,
        "supervisor_email": sup_email(emp.supervisor_emp_no) if sup_email else "",
        "id": e.id, "ticket": e.ticket, "emp_no": emp.emp_no,
        "employee_name": f"{emp.first_name_en} {emp.last_name_en}".strip(),
        "employee_name_fa": f"{emp.first_name_fa} {emp.last_name_fa}".strip(),
        "division": emp.division, "run_id": e.run_id, "course_name": e.course_name, "category": e.category,
        "current_status": e.current_status, "status": e.status, "motivation": e.motivation,
        "registration": e.registration, "calendar": e.calendar, "attendance": e.attendance_status,
        "payment": e.payment, "comment": e.comment, "section_b": e.section_b,
        "start_date": iso(e.start_date), "end_date": iso(e.end_date), "level3_status": e.level3_status,
        "level3_sent": e.level3_sent, "link": f"{ticket_base}{e.ticket}" if ticket_base else "",
    }


def letter(x: Letter) -> dict:
    return {"id": x.id, "kind": x.kind, "run_id": x.run_id, "number": x.number, "state": x.state, "lang": x.lang,
            "filename": x.filename, "subject": x.subject, "enrollment_ids": x.enrollment_ids,
            "created_at": iso(x.created_at), "created_by": x.created_by,
            "download_url": f"/api/v1/letters/{x.id}/download"}


def message(m: MessageLog) -> dict:
    return {"id": m.id, "idempotency_key": m.idempotency_key, "letter_id": m.letter_id, "subject": m.subject,
            "recipients": m.recipients, "results": m.results, "dry_run": m.dry_run, "status": m.status,
            "channel": m.channel, "created_at": iso(m.created_at)}


def connector(kind: str, c: ConnectorConfig | None) -> dict:
    """Secrets are write-only: only the *names* of secret fields that have a value are exposed
    -- never a value, a mask, or a length."""
    if c is None:
        return {"kind": kind, "configured": False, "enabled": False, "config": {}, "secrets_set": [],
                "last_test_ok": None, "last_test_at": None, "last_test_message": "", "updated_at": None}
    return {"kind": kind, "configured": True, "enabled": c.enabled, "config": dict(c.public or {}),
            "secrets_set": sorted(k for k, v in (c.secrets or {}).items() if v not in (None, "")),
            "last_test_ok": c.last_test_ok, "last_test_at": iso(c.last_test_at),
            "last_test_message": c.last_test_message or "", "updated_at": iso(c.updated_at)}


def sync_run(s: SyncRun) -> dict:
    return {"id": s.id, "source": s.source, "status": s.status, "started_at": iso(s.started_at),
            "finished_at": iso(s.finished_at), "created": s.created, "updated": s.updated,
            "unchanged": s.unchanged, "skipped": s.skipped, "processed": s.processed or 0, "errors": s.errors, "message": s.message or "",
            "triggered_by": s.triggered_by}


def audit(a: AuditLog) -> dict:
    return {"id": a.id, "ts": iso(a.ts), "actor": a.actor, "actor_id": a.actor_id, "action": a.action,
            "entity": a.entity, "entity_id": a.entity_id, "detail": a.detail, "ip": a.ip}


def template(t, detail: bool = False) -> dict:
    d = {"id": t.id, "kind": t.kind, "name": t.name, "lang": t.lang, "subject": t.subject, "is_system": t.is_system,
         "is_default": t.is_default, "version": t.version, "created_by": t.created_by, "created_at": iso(t.created_at),
         "updated_at": iso(t.updated_at)}
    if detail:
        from app.api.services import rich_text
        d["body_html"] = t.body_html
        keys = rich_text.referenced_fields(t.body_html)
        d["fields_used"] = keys + [k for k in dict.fromkeys(rich_text.TOKEN_RE.findall(t.subject)) if k not in keys]
    return d
