"""Тесты API через TestClient. Сеть не используется: мокаем check_icmp/check_tcp."""

import inspect
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import create_app


@pytest.fixture
def client(session_factory):
    from app.main import create_app
    return TestClient(create_app(session_factory=session_factory))


# ---------- /health ----------


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------- GET /targets ----------


def test_list_targets_empty(client):
    r = client.get("/targets")
    assert r.status_code == 200
    assert r.json() == []


def test_list_targets_returns_added(client):
    client.post("/targets", json={"id": 1, "host": "8.8.8.8", "type": "icmp"})
    client.post("/targets", json={"id": 2, "host": "127.0.0.1", "type": "tcp", "port": 8000})
    r = client.get("/targets")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert ids == [1, 2]


# ---------- POST /targets ----------


def test_add_target_returns_201(client):
    r = client.post("/targets", json={"host": "8.8.8.8", "type": "icmp"})
    assert r.status_code == 201
    data = r.json()
    assert data["id"] == 1
    assert data["host"] == "8.8.8.8"
    assert data["type"] == "icmp"
    assert data["timeout"] == 2.0


def test_add_target_explicit_id(client):
    r = client.post("/targets", json={"id": 42, "host": "8.8.8.8", "type": "icmp"})
    assert r.status_code == 201
    assert r.json()["id"] == 42


def test_add_target_auto_id_sequential(client):
    client.post("/targets", json={"host": "a", "type": "icmp"})
    r = client.post("/targets", json={"host": "b", "type": "icmp"})
    assert r.json()["id"] == 2


def test_add_target_duplicate_id_409(client):
    client.post("/targets", json={"id": 1, "host": "a", "type": "icmp"})
    r = client.post("/targets", json={"id": 1, "host": "b", "type": "icmp"})
    assert r.status_code == 409


def test_add_target_tcp_without_port_422(client):
    r = client.post("/targets", json={"host": "127.0.0.1", "type": "tcp"})
    assert r.status_code == 422


def test_add_target_invalid_type_422(client):
    r = client.post("/targets", json={"host": "8.8.8.8", "type": "udp"})
    assert r.status_code == 422


def test_add_target_empty_host_422(client):
    r = client.post("/targets", json={"host": "", "type": "icmp"})
    assert r.status_code == 422


def test_add_target_negative_timeout_422(client):
    r = client.post("/targets", json={"host": "8.8.8.8", "type": "icmp", "timeout": -1})
    assert r.status_code == 422


def test_add_target_bad_port_422(client):
    r = client.post(
        "/targets", json={"host": "127.0.0.1", "type": "tcp", "port": 99999}
    )
    assert r.status_code == 422


# ---------- DELETE /targets/{id} ----------


def test_delete_target_204(client):
    client.post("/targets", json={"id": 1, "host": "8.8.8.8", "type": "icmp"})
    r = client.delete("/targets/1")
    assert r.status_code == 204
    assert client.get("/targets").json() == []


def test_delete_missing_target_404(client):
    r = client.delete("/targets/999")
    assert r.status_code == 404


# ---------- POST /monitor/run ----------


def test_run_monitor_empty(client):
    r = client.post("/monitor/run")
    assert r.status_code == 200
    assert r.json() == []


def test_run_monitor_returns_results(client):
    client.post("/targets", json={"id": 1, "host": "8.8.8.8", "type": "icmp"})
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        r = client.post("/monitor/run")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["ok"] is True
    assert data[0]["status_changed"] is False
    assert "checked_at" in data[0]


# ---------- GET /monitor/results ----------


def test_get_results_empty(client):
    r = client.get("/monitor/results")
    assert r.status_code == 200
    assert r.json() == []


def test_get_results_after_run(client):
    client.post("/targets", json={"id": 1, "host": "8.8.8.8", "type": "icmp"})
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        client.post("/monitor/run")
    r = client.get("/monitor/results")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ---------- Переходы состояний ----------


def test_status_changed_between_runs(client):
    client.post("/targets", json={"id": 1, "host": "8.8.8.8", "type": "icmp"})
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        r1 = client.post("/monitor/run").json()
    assert r1[0]["status_changed"] is False

    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": False, "ms": None, "error": "timeout"},
    ):
        r2 = client.post("/monitor/run").json()
    assert r2[0]["status_changed"] is True


# ---------- Требование 5: история оставшихся ----------


def test_history_preserved_after_delete(client):
    """Удаление одного target'а не сбрасывает историю другого."""
    client.post("/targets", json={"id": 1, "host": "a", "type": "icmp"})
    client.post("/targets", json={"id": 2, "host": "b", "type": "icmp"})
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        client.post("/monitor/run")

    # удаляем id=2, оставляем id=1
    client.delete("/targets/2")

    # если история id=1 сохранилась — UP→DOWN даст status_changed=True
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": False, "ms": None, "error": "down"},
    ):
        r = client.post("/monitor/run").json()
    assert r[0]["id"] == 1
    assert r[0]["status_changed"] is True


def test_deleted_target_not_in_results(client):
    client.post("/targets", json={"id": 1, "host": "a", "type": "icmp"})
    client.post("/targets", json={"id": 2, "host": "b", "type": "icmp"})
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        client.post("/monitor/run")
    client.delete("/targets/1")
    r = client.get("/monitor/results").json()
    assert [item["id"] for item in r] == [2]


# ---------- Требование 6: async / non-blocking ----------


def test_run_monitor_is_async():
    """/monitor/run объявлен async — не блокирует event loop."""
    assert inspect.iscoroutinefunction(routes.run_monitor)
def test_add_target_whitespace_host_422(client):
    r = client.post("/targets", json={"host": "   ", "type": "icmp"})
    assert r.status_code == 422


def test_add_target_inf_timeout_422(client):
    r = client.post(
        "/targets", json={"host": "8.8.8.8", "type": "icmp", "timeout": "inf"}
    )
    assert r.status_code == 422


def test_add_target_nan_timeout_422(client):
    r = client.post(
        "/targets", json={"host": "8.8.8.8", "type": "icmp", "timeout": "nan"}
    )
    assert r.status_code == 422


def test_add_target_host_is_stripped(client):
    r = client.post("/targets", json={"host": "  example.com  ", "type": "icmp"})
    assert r.status_code == 201
    assert r.json()["host"] == "example.com"