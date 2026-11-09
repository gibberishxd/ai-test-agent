from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from worker.config import Settings


def make_engine(settings: Settings) -> Engine:
    # pool_pre_ping: check a pooled connection still works before using it (Postgres restarts).
    return create_engine(settings.sqlalchemy_url(), pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: objects stay readable after commit without another query.
    return sessionmaker(engine, expire_on_commit=False)
