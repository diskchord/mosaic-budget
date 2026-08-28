from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


settings = get_settings()
_engine_options = {
    "pool_pre_ping": True,
    "pool_recycle": 1800,
    "future": True,
}
if settings.database_url.startswith("sqlite"):
    _engine_options["connect_args"] = {"check_same_thread": False}
    if ":memory:" in settings.database_url:
        _engine_options["poolclass"] = StaticPool
engine = create_engine(settings.database_url, **_engine_options)


if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _sqlite_compatibility(dbapi_connection, _connection_record) -> None:
        # Only used by the unit/smoke suite. Production deployments use
        # PostgreSQL, where date_part and deferred constraints are native.
        def date_part(part: str, value: object) -> int:
            if str(part).casefold() != "day":
                return 0
            text = str(value)
            try:
                return int(text[8:10])
            except (ValueError, IndexError):
                return 0

        dbapi_connection.create_function("date_part", 2, date_part)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
