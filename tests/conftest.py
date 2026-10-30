"""Общие фикстуры: SQLite in-memory + сессия + репозитории."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db import models 
from app.monitoring.engine import MonitorEngine
from app.services.monitor_service import MonitorService


@pytest.fixture
def _db_engine():
    """Один in-memory engine на весь тест. Общий для session_factory и db_session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def session_factory(_db_engine):
    """Фабрика сессий на общем engine."""
    return sessionmaker(
        bind=_db_engine, autoflush=False, autocommit=False,
        expire_on_commit=False,
    )


@pytest.fixture
def db_session(session_factory):
    """Одна сессия для тестов repository — на том же engine."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def target_repo(db_session):
    from app.db.repository import TargetRepository
    return TargetRepository(db_session)


@pytest.fixture
def result_repo(db_session):
    from app.db.repository import CheckResultRepository
    return CheckResultRepository(db_session)

@pytest.fixture
def session_factory():
    """Фабрика сессий на свежей SQLite in-memory (для service-тестов)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False,
        expire_on_commit=False,
    )
    yield factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def monitor_engine():
    return MonitorEngine([])


@pytest.fixture
def service(session_factory, monitor_engine):
    return MonitorService(monitor_engine, session_factory)