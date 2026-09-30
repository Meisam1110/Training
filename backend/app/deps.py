"""FastAPI dependencies: DB session, current user (session cookie), RBAC, CSRF."""
from __future__ import annotations

import hmac
import ipaddress
from typing import Annotated, Callable, Iterator

from fastapi import Depends, Path, Request
from sqlalchemy.orm import Session

from app.api.errors import ApiError, forbidden
from app.auth import sessions
from app.config import Settings
from app.models import User, UserSession

PathId = Annotated[int, Path(ge=1, le=2**31 - 1)]     # 422 for 0, negatives and ids beyond the DB integer range
RANK = {"viewer": 1, "hr": 2, "admin": 3}
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db: Session = request.app.state.session_factory()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _nets(request: Request):
    st = request.app.state
    nets = getattr(st, "trusted_nets", None)
    if nets is None:
        nets = st.trusted_nets = [ipaddress.ip_network(c, strict=False) for c in st.settings.trusted_proxies]
    return nets


def client_ip(request: Request) -> str:
    """Real client address. X-Forwarded-For is honoured ONLY when the TCP peer is a trusted proxy
    (TMS_TRUSTED_PROXIES, default loopback + the docker bridge range), and the chain is read from the
    right: the first hop that is not itself a trusted proxy is the client. Anything a client puts at the
    left of the header is ignored, so it cannot be spoofed to dodge the per-IP limit or falsify the audit IP."""
    peer = request.client.host if request.client else ""
    xff = request.headers.get("x-forwarded-for", "")
    try:
        nets = _nets(request)
        if not xff or not peer or not any(ipaddress.ip_address(peer) in n for n in nets):
            return peer
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        for hop in reversed(hops):
            try:
                addr = ipaddress.ip_address(hop)
            except ValueError:
                return peer            # garbage in the chain: do not guess
            if not any(addr in n for n in nets):
                return str(addr)
        return str(ipaddress.ip_address(hops[0])) if hops else peer
    except ValueError:
        return peer


def current_session(request: Request, db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings)) -> UserSession:
    s = sessions.lookup(db, request.cookies.get(sessions.COOKIE), settings.secret_key)
    if not s:
        raise ApiError("unauthorized", "ورود لازم است")
    if request.method in UNSAFE:
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not hmac.compare_digest(sent, s.csrf_token):
            raise forbidden("توکن CSRF نامعتبر است")
    request.state.user_id = s.user_id
    request.scope.setdefault("state", {})["user_id"] = s.user_id
    return s


def current_user(s: UserSession = Depends(current_session)) -> User:
    return s.user


def require(role: str) -> Callable[..., User]:
    """Dependency factory: the caller needs at least ``role`` (admin > hr > viewer)."""
    need = RANK[role]

    def dep(user: User = Depends(current_user)) -> User:
        if RANK.get(user.role, 0) < need:
            raise forbidden()
        return user

    dep.required_role = role  # type: ignore[attr-defined]
    return dep
