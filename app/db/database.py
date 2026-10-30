"""SQLAlchemy: engine, SessionLocal, Base, init_db."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Базовый класс для ORM-моделей."""


def _make_engine(url: str):
    # SQLite in-memory — нужен StaticPool, чтобы все сессии видели одну БД.
    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
        )

        @event.listens_for(engine, "connect")
        def _fk_pragma(dbapi_conn, _):
            # SQLite по умолчанию не включает foreign keys — включаем вручную,
            # чтобы ON DELETE CASCADE работал как в PostgreSQL.
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine

    return create_engine(url, pool_pre_ping=True, future=True)


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """Создать таблицы (для тестов/SQLite; в продакшене — Alembic)."""
    from app.db import models  # noqa: F401 — регистрирует ORM-классы в Base.metadata

    Base.metadata.create_all(bind=engine)
    