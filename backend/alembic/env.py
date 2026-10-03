import os

from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (register tables)
from alembic import context
from app.db import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return (config.get_main_option("sqlalchemy.url") or os.environ.get("DATABASE_URL")
            or os.environ.get("TMS_DATABASE_URL") or "sqlite:///./tms-dev.db")


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=_url().startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    engine = create_engine(url, poolclass=pool.NullPool,
                           connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata,
                          render_as_batch=url.startswith("sqlite"))
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
