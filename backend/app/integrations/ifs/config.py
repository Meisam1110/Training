"""IFS connector configuration and the documented default field map.

Nothing tenant-specific is hard-coded: ``employees_path`` and every ``field_map`` entry are
overridable from the ConnectorConfig JSON. The defaults below match the *typical* shape of an
IFS Cloud OData v4 ``PersonInfo``/``CompanyPerson``-style entity set and are a STARTING POINT
that an administrator must verify against the tenant's `$metadata`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlsplit

AUTH_MODES = ("oauth2_client_credentials", "basic", "session_login")

# EmployeeRecord field -> ordered list of candidate JSON keys (first non-empty wins).
# A candidate may be a dotted path ("Position.Title") to reach nested objects.
DEFAULT_FIELD_MAP: dict[str, list[str]] = {
    "emp_no": ["EmpNo", "PersonId", "EmployeeId", "CompanyPersonId"],
    "first_name_en": ["FirstName", "Fname"],
    "last_name_en": ["LastName", "Lname"],
    "first_name_fa": ["FarsiFirstName", "AlternativeFirstName", "LocalFirstName"],
    "last_name_fa": ["FarsiLastName", "AlternativeLastName", "LocalLastName"],
    "gender": ["Gender", "Sex"],
    "email": ["Email", "PrimaryEmail", "EmailAddress"],
    "mobile": ["Mobile", "MobilePhone", "MobileNo"],
    "national_code": ["NationalCode", "NationalId", "PersonalIdentityNo"],
    "division": ["Division", "OrganizationName", "OrgName"],
    "cost_center": ["CostCenter", "CostCenterCode"],
    "org_code": ["OrgCode", "OrganizationCode"],
    "position_title": ["PositionTitle", "JobTitle", "Position.Title"],
    "supervisor_emp_no": ["SupEmpNo", "SupervisorId", "ManagerId"],
    "status": ["EmployeeStatus", "Status"],
}
REQUIRED_TARGETS = ("emp_no", "first_name_en", "last_name_en")

DEFAULT_EMPLOYEES_PATH = "/PersonInfo"   # relative to base_url; tenant specific -> override


class IfsConfigError(ValueError):
    """Invalid connector configuration (message never contains secret values)."""


def _num(v: Any, default: float) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        raise IfsConfigError("numeric option has an invalid value") from None


@dataclass(frozen=True)
class IfsConfig:
    base_url: str
    auth_mode: str
    client_id: str = ""
    client_secret: str = ""
    token_url: str = ""
    scope: str = ""
    username: str = ""
    password: str = ""
    login_url: str = ""
    login_user_field: str = "username"
    login_password_field: str = "password"
    verify_tls: bool = True
    ca_bundle: str = ""
    timeout_s: float = 30.0
    employees_path: str = DEFAULT_EMPLOYEES_PATH
    page_size: int = 500
    max_retries: int = 4
    backoff_base_s: float = 0.5
    backoff_max_s: float = 30.0
    breaker_threshold: int = 5
    breaker_cooldown_s: float = 60.0
    allow_private_hosts: bool = False   # see app/integrations/urlcheck.py; set true for an on-prem IFS on a private network
    max_response_bytes: int = 64 * 1024 * 1024
    modified_field: str = "ModifiedDate"
    delta_mode: str = "server"          # "server" -> $filter ; "client" -> filter after fetching
    active_statuses: tuple[str, ...] = ("active",)
    field_map: Mapping[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_FIELD_MAP))

    @property
    def secrets(self) -> list[str]:
        return [s for s in (self.client_secret, self.password) if s]

    @classmethod
    def from_dict(cls, cfg: Mapping[str, Any]) -> "IfsConfig":
        base = str(cfg.get("base_url", "")).strip().rstrip("/")
        if not base.lower().startswith(("http://", "https://")):
            raise IfsConfigError("base_url must start with http:// or https://")
        parts = urlsplit(base)
        if not parts.hostname:
            raise IfsConfigError("base_url has no host")
        if parts.username or parts.password:
            raise IfsConfigError("credentials must not be embedded in base_url")
        allow_private = cfg.get("allow_private_hosts", False) in (True, "true", "True", 1, "1")
        mode = str(cfg.get("auth_mode", "")).strip()
        if mode not in AUTH_MODES:
            raise IfsConfigError(f"auth_mode must be one of: {', '.join(AUTH_MODES)}")
        need = {"oauth2_client_credentials": ("client_id", "client_secret", "token_url"),
                "basic": ("username", "password"),
                "session_login": ("username", "password", "login_url")}[mode]
        missing = [k for k in need if not str(cfg.get(k, "")).strip()]
        if missing:
            raise IfsConfigError(f"missing required option(s) for {mode}: {', '.join(missing)}")
        fmap: dict[str, list[str]] = {k: list(v) for k, v in DEFAULT_FIELD_MAP.items()}
        for k, v in (cfg.get("field_map") or {}).items():
            if k not in DEFAULT_FIELD_MAP:
                raise IfsConfigError(f"field_map: unknown target field '{k}'")
            fmap[k] = [v] if isinstance(v, str) else [str(x) for x in v]
        verify = cfg.get("verify_tls", True)
        delta_mode = str(cfg.get("delta_mode", "server"))
        if delta_mode not in ("server", "client"):
            raise IfsConfigError("delta_mode must be 'server' or 'client'")
        from urllib.parse import urljoin

        from app.integrations.urlcheck import UnsafeUrlError, check_url

        def absolute(name: str, value: str) -> str:
            u = value if value.lower().startswith(("http://", "https://")) else urljoin(base + "/", value.lstrip("/"))
            try:
                return check_url(u, name, allow_private_hosts=allow_private)
            except UnsafeUrlError as exc:
                raise IfsConfigError(str(exc)) from None

        absolute("base_url", base)
        for opt in ("token_url", "login_url"):
            if str(cfg.get(opt, "")).strip():
                absolute(opt, str(cfg[opt]).strip())
        ep = str(cfg.get("employees_path") or DEFAULT_EMPLOYEES_PATH)
        if ep.lower().startswith(("http://", "https://")):
            if urlsplit(absolute("employees_path", ep))[:2] != urlsplit(base)[:2]:
                raise IfsConfigError("employees_path must be on the same host as base_url")
        page = int(_num(cfg.get("page_size"), 500))
        if page < 1 or page > 10000:
            raise IfsConfigError("page_size out of range (1..10000)")
        return cls(
            base_url=base, auth_mode=mode,
            client_id=str(cfg.get("client_id", "")), client_secret=str(cfg.get("client_secret", "")),
            token_url=str(cfg.get("token_url", "")), scope=str(cfg.get("scope", "")),
            username=str(cfg.get("username", "")), password=str(cfg.get("password", "")),
            login_url=str(cfg.get("login_url", "")),
            login_user_field=str(cfg.get("login_user_field", "username")),
            login_password_field=str(cfg.get("login_password_field", "password")),
            verify_tls=False if verify in (False, "false", "False", 0, "0") else True,
            ca_bundle=str(cfg.get("ca_bundle", "")),
            timeout_s=_num(cfg.get("timeout_s"), 30.0),
            employees_path=str(cfg.get("employees_path") or DEFAULT_EMPLOYEES_PATH),
            page_size=page, max_retries=int(_num(cfg.get("max_retries"), 4)),
            backoff_base_s=_num(cfg.get("backoff_base_s"), 0.5),
            backoff_max_s=_num(cfg.get("backoff_max_s"), 30.0),
            breaker_threshold=int(_num(cfg.get("breaker_threshold"), 5)),
            breaker_cooldown_s=_num(cfg.get("breaker_cooldown_s"), 60.0),
            allow_private_hosts=allow_private,
            max_response_bytes=int(_num(cfg.get("max_response_bytes"), 64 * 1024 * 1024)),
            modified_field=str(cfg.get("modified_field", "ModifiedDate")),
            delta_mode=delta_mode,
            active_statuses=tuple(str(s).lower() for s in cfg.get("active_statuses", ("active",))),
            field_map=fmap,
        )
