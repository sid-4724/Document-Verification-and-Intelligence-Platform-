from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


url = settings().database_url
if url.startswith("sqlite"):
    Path("var").mkdir(exist_ok=True)
engine = create_engine(
    url,
    pool_pre_ping=True,
    hide_parameters=True,
    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
)
if url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def sqlite_config(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")


SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
