"""Engine / session factory / declarative Base / migration helpers."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kw: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if ":memory:" in url or url in ("sqlite://", "sqlite:///"):
            kw["poolclass"] = StaticPool
        else:
            kw["poolclass"] = NullPool
    else:
        kw.update(pool_size=10, max_overflow=10, pool_recycle=1800)
    eng = create_engine(url, **kw)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _rec):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()
    return eng


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def alembic_config(url: str):
    from alembic.config import Config
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade_to_head(url: str) -> None:
    from alembic import command
    command.upgrade(alembic_config(url), "head")


def head_revision() -> str:
    from alembic.script import ScriptDirectory
    return ScriptDirectory(str(BACKEND_DIR / "alembic")).get_current_head() or ""


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as c:
        try:
            return c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            return None
