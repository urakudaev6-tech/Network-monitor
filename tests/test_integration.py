"""Интеграция: устройство и история сохраняются между "перезапусками" приложения.

Используем файловый SQLite (tmp_path), а не in-memory, чтобы данные
действительно пережили пересоздание engine + session_factory.
"""

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.db.database import Base
from app.db import models  # noqa: F401
from app.main import create_app


def _make_factory(db_path):
    """Новая engine + sessionmaker на ТОТ ЖЕ файл — имитация перезапуска."""
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False,
                        expire_on_commit=False)


def test_targets_and_history_survive_restart(tmp_path):
    db_path = tmp_path / "integration.db"

    # --- Первый "запуск" ---
    factory1 = _make_factory(db_path)
    app1 = create_app(session_factory=factory1)
    with TestClient(app1) as client1:
        r = client1.post("/targets", json={"host": "8.8.8.8", "type": "icmp"})
        assert r.status_code == 201
        tid = r.json()["id"]

        with patch(
            "app.monitoring.engine.check_icmp",
            return_value={"ok": True, "ms": 5.0, "error": None},
        ):
            r = client1.post("/monitor/run")
        assert r.status_code == 200

    # --- Второй "запуск": новая engine, тот же файл ---
    factory2 = _make_factory(db_path)
    app2 = create_app(session_factory=factory2)
    with TestClient(app2) as client2:
        # target восстановлен при startup (load_from_db)
        targets = client2.get("/targets").json()
        assert len(targets) == 1
        assert targets[0]["id"] == tid
        assert targets[0]["host"] == "8.8.8.8"

        # история жива
        hist = client2.get(f"/targets/{tid}/history").json()
        assert len(hist) == 1
        assert hist[0]["ok"] is True
        assert hist[0]["ms"] == 5.0