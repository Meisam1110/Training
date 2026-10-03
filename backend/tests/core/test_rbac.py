"""Every route: unauthenticated -> 401, below-minimum role -> 403 (server-side RBAC)."""
import pytest
from fastapi.routing import APIRoute

from app.deps import RANK

ROLES = ["viewer", "hr", "admin"]
# (method, path, minimum role)
TABLE = [
    ("GET", "/auth/me", "viewer"),
    ("POST", "/auth/logout", "viewer"),
    ("GET", "/dashboard", "viewer"),
    ("GET", "/employees", "viewer"), ("GET", "/employees/E00001", "viewer"),
    ("GET", "/courses", "viewer"), ("POST", "/courses", "hr"), ("GET", "/courses/1", "viewer"), ("PATCH", "/courses/1", "hr"),
    ("GET", "/runs", "viewer"), ("POST", "/runs", "hr"), ("GET", "/runs/1", "viewer"), ("PATCH", "/runs/1", "hr"),
    ("GET", "/runs/1/enrollments", "viewer"), ("POST", "/runs/1/candidates:search", "hr"),
    ("GET", "/enrollments", "viewer"), ("PATCH", "/enrollments/1", "hr"), ("POST", "/enrollments:bulk", "hr"),
    ("GET", "/letters", "viewer"), ("POST", "/letters/preview", "hr"), ("POST", "/letters", "hr"), ("GET", "/letters/1/download", "hr"),
    ("POST", "/email/send", "hr"), ("GET", "/messages", "hr"),
    ("GET", "/connectors", "hr"), ("PUT", "/connectors/smtp", "admin"), ("POST", "/connectors/smtp:test", "admin"),
    ("POST", "/sync/excel:run", "hr"), ("GET", "/sync/runs", "hr"),
    ("GET", "/automation/due", "viewer"), ("POST", "/automation/run", "hr"), ("GET", "/automation/settings", "viewer"),
    ("PUT", "/automation/settings", "admin"),
    ("POST", "/import/idp", "hr"), ("POST", "/import/legacy-workbook", "hr"), ("GET", "/export/legacy.xlsx", "hr"),
    ("GET", "/users", "admin"), ("POST", "/users", "admin"), ("PATCH", "/users/1", "admin"), ("GET", "/audit", "admin"),
    ("GET", "/templates/fields", "viewer"), ("GET", "/templates", "viewer"), ("POST", "/templates", "hr"), ("POST", "/templates/preview", "hr"),
    ("GET", "/templates/1", "viewer"), ("PATCH", "/templates/1", "hr"), ("DELETE", "/templates/1", "hr"),
    ("POST", "/templates/1:duplicate", "hr"), ("POST", "/templates/1:set-default", "hr"), ("POST", "/templates/1:send-test", "hr"),
    ("GET", "/templates/1/versions", "viewer"), ("POST", "/templates/1/versions/1:restore", "hr"),
    ("GET", "/dashboard/widgets", "viewer"), ("GET", "/dashboard/data?widgets=kpi_enrollments", "viewer"),
    ("GET", "/me/dashboard-layout", "viewer"), ("PUT", "/me/dashboard-layout", "viewer"), ("DELETE", "/me/dashboard-layout", "viewer"),
    ("GET", "/me/preferences", "viewer"), ("PUT", "/me/preferences", "viewer"),
    ("GET", "/institutes", "viewer"), ("POST", "/institutes", "hr"), ("PATCH", "/institutes/1", "hr"),
]


@pytest.mark.parametrize("method,path,minimum", TABLE)
def test_role_matrix(api, method, path, minimum):
    anon = api(None)
    assert anon.req(method, path, json={}).status_code == 401, "anonymous must be 401"
    for role in ROLES:
        r = api(role).req(method, path, json={})
        if RANK[role] < RANK[minimum]:
            assert r.status_code == 403, f"{role} on {method} {path}"
            assert r.json()["error"]["code"] == "forbidden"
        else:
            assert r.status_code != 403 and r.status_code != 401, f"{role} on {method} {path}: {r.status_code}"


def test_every_api_route_is_covered_and_declares_a_role(app):
    import importlib
    import pkgutil

    import app.api.routers as pkg
    shapes = {(m, _shape("/api/v1" + p.split("?")[0])) for m, p, _ in TABLE}
    seen = 0
    for mod in pkgutil.iter_modules(pkg.__path__):
        router = importlib.import_module(f"app.api.routers.{mod.name}").router
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            full = "/api/v1" + route.path
            if full == "/api/v1/auth/login":
                continue
            names = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
            assert "dep" in names or "current_session" in names, f"{full} has no auth dependency"
            for m in route.methods - {"HEAD"}:
                assert (m, _shape(full)) in shapes, f"{m} {full} missing from the RBAC table"
                seen += 1
    assert seen >= len(TABLE) - 1


def _shape(p: str) -> str:
    import re
    out = []
    for seg in p.split("/"):
        seg = re.sub(r"^\{[a-z_]+\}", "{}", seg)
        seg = re.sub(r"^(E\d+|\d+)(?=:|$)", "{}", seg)
        seg = re.sub(r"^(excel|smtp)(:|$)", r"{}\2", seg)
        out.append(seg)
    return "/".join(out)
