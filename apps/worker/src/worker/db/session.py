from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from worker.config import Settings


def make_engine(settings: Settings, admin: bool = False) -> Engine:
    """The worker's connection, or (admin=True) the admin one for maintenance commands.

    pool_pre_ping: check a pooled connection still works before using it (Postgres restarts)."""
    url = settings.admin_sqlalchemy_url() if admin else settings.sqlalchemy_url()
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: objects stay readable after commit without another query.
    return sessionmaker(engine, expire_on_commit=False)
