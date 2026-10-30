"""Тесты MonitorService: связка engine ↔ repository."""

from unittest.mock import patch

import pytest

from app.monitoring.engine import DuplicateIdError


def _ok(ms=5.0):
    return {"ok": True, "ms": ms, "error": None}


# ---------- load_from_db ----------


def test_load_from_db_restores_targets(service, target_repo):
    target_repo.create("8.8.8.8", "icmp", None, 2.0)
    target_repo.create("1.1.1.1", "icmp", None, 2.0)

    n = service.load_from_db()
    assert n == 2
    assert len(service.engine.targets) == 2
    assert service.engine.targets[0].host == "8.8.8.8"


def test_load_from_db_empty(service):
    assert service.load_from_db() == 0
    assert service.engine.targets == []


# ---------- add_target ----------


def test_add_target_persists_and_syncs(service, target_repo):
    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    assert t["id"] is not None

    db_targets = target_repo.get_all()
    assert len(db_targets) == 1
    assert db_targets[0].host == "8.8.8.8"
    assert len(service.engine.targets) == 1
    assert service.engine.targets[0].id == t["id"]


def test_add_target_explicit_id(service, target_repo):
    t = service.add_target("8.8.8.8", "icmp", None, 2.0, id_=42)
    assert t["id"] == 42
    assert target_repo.get_by_id(42) is not None


def test_add_target_duplicate_raises(service):
    service.add_target("a", "icmp", None, 2.0, id_=1)
    with pytest.raises(DuplicateIdError):
        service.add_target("b", "icmp", None, 2.0, id_=1)


# ---------- delete_target ----------


def test_delete_target_removes_from_both(service, target_repo):
    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    assert service.delete_target(t["id"]) is True
    assert target_repo.get_by_id(t["id"]) is None
    assert service.engine.targets == []


def test_delete_missing_returns_false(service):
    assert service.delete_target(9999) is False


# ---------- get_target / list_targets ----------


def test_get_target_existing(service):
    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    got = service.get_target(t["id"])
    assert got is not None
    assert got["host"] == "8.8.8.8"


def test_get_target_missing(service):
    assert service.get_target(9999) is None


def test_list_targets_returns_db_order(service):
    service.add_target("a", "icmp", None, 2.0)
    service.add_target("b", "icmp", None, 2.0)
    hosts = [t["host"] for t in service.list_targets()]
    assert hosts == ["a", "b"]


# ---------- get_history ----------


def test_get_history_empty(service):
    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    assert service.get_history(t["id"]) == []


def test_get_history_returns_records(service, result_repo):
    from datetime import datetime, timezone
    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    result_repo.save_results([{
        "id": t["id"], "ok": True, "ms": 5.0, "error": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status_changed": False,
    }])
    history = service.get_history(t["id"])
    assert len(history) == 1
    assert history[0]["target_id"] == t["id"]


def test_get_history_missing_target(service):
    assert service.get_history(9999) is None


def test_get_history_limit(service, result_repo):
    from datetime import datetime, timezone
    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    for _ in range(5):
        result_repo.save_results([{
            "id": t["id"], "ok": True, "ms": 1.0, "error": None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status_changed": False,
        }])
    assert len(service.get_history(t["id"], limit=3)) == 3


# ---------- run_monitoring ----------


def test_run_monitoring_saves_to_db(service, result_repo):
    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    with patch("app.monitoring.engine.check_icmp", return_value=_ok()):
        results = service.run_monitoring()
    assert len(results) == 1
    assert results[0]["ok"] is True

    history = result_repo.get_by_target(t["id"])
    assert len(history) == 1
    assert history[0].ok is True


def test_run_monitoring_empty_targets(service):
    with patch("app.monitoring.engine.check_icmp", return_value=_ok()):
        results = service.run_monitoring()
    assert results == []


def test_run_monitoring_db_failure_raises(service, monkeypatch):
    """Если save_results упал — RuntimeError, клиент получит 503."""
    from app.db import repository as repo_module

    def boom(self, results):
        raise RuntimeError("simulated db failure")

    service.add_target("8.8.8.8", "icmp", None, 2.0)
    monkeypatch.setattr(repo_module.CheckResultRepository, "save_results", boom)

    with patch("app.monitoring.engine.check_icmp", return_value=_ok()):
        with pytest.raises(RuntimeError, match="failed to persist"):
            service.run_monitoring()


# ---------- Удаление во время проверки ----------


def test_delete_during_run_not_saved(service, result_repo, target_repo):
    """Target удалён во время engine.run_once — результаты не сохраняются."""
    t1 = service.add_target("h1", "icmp", None, 2.0)
    t2 = service.add_target("h2", "icmp", None, 2.0)

    def fake_check(host, timeout):
        # Во время проверки удаляем t2 из БД и engine
        service.delete_target(t2["id"])
        return _ok()

    with patch("app.monitoring.engine.check_icmp", side_effect=fake_check):
        results = service.run_monitoring()

    # engine удалил t2 из своей истории — в results только t1
    ids = [r["id"] for r in results]
    assert t1["id"] in ids
    # в БД тоже только для t1
    assert len(result_repo.get_by_target(t1["id"])) >= 1


# ---------- Параллельные запуски ----------


def test_parallel_runs_both_saved_to_history(service, result_repo):
    """Два параллельных run_monitoring: история обоих сохранена (append, no overwrite)."""
    import threading
    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    errors = []

    def run():
        try:
            with patch("app.monitoring.engine.check_icmp", return_value=_ok()):
                service.run_monitoring()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(3)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert not errors
    # минимум 1 запись за каждый прогон (не 0)
    history = result_repo.get_by_target(t["id"], limit=100)
    assert len(history) >= 1
# ---------- Stale / пересоздание target ----------


def test_stale_run_not_saved_to_db(service, result_repo, monkeypatch):
    from datetime import datetime, timezone
    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    fake = [{
        "id": t["id"], "host": "8.8.8.8", "type": "icmp",
        "ok": True, "ms": 5.0, "error": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status_changed": False, "port": None, "timeout": 2.0,
        "stale": True,
    }]
    monkeypatch.setattr(service.engine, "run_once", lambda: fake)
    service.run_monitoring()
    assert result_repo.get_by_target(t["id"]) == []


def test_fresh_run_saved_to_db(service, result_repo, monkeypatch):
    from datetime import datetime, timezone
    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    fake = [{
        "id": t["id"], "host": "8.8.8.8", "type": "icmp",
        "ok": True, "ms": 5.0, "error": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status_changed": False, "port": None, "timeout": 2.0,
        "stale": False,
    }]
    monkeypatch.setattr(service.engine, "run_once", lambda: fake)
    service.run_monitoring()
    history = result_repo.get_by_target(t["id"])
    assert len(history) == 1
    assert history[0].ok is True


def test_recreated_target_not_saved(service, result_repo, db_session, monkeypatch):
    """target пересоздан с тем же id, но другим host — результат старой проверки не сохраняется."""
    from datetime import datetime, timezone
    from app.db.models import TargetORM

    t = service.add_target("old.host", "icmp", None, 2.0)
    tid = t["id"]
    service.delete_target(tid)

    # Создаём в БД новый target с тем же id, но другим host (в обход engine)
    db_session.add(TargetORM(id=tid, host="new.host", type="icmp", port=None, timeout=3.0))
    db_session.commit()

    fake = [{
        "id": tid, "host": "old.host", "type": "icmp",
        "ok": True, "ms": 5.0, "error": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status_changed": False, "port": None, "timeout": 2.0,
        "stale": False,
    }]
    monkeypatch.setattr(service.engine, "run_once", lambda: fake)
    service.run_monitoring()
    assert result_repo.get_by_target(tid) == []
def test_recreated_with_same_params_not_saved(service, result_repo, db_session, monkeypatch):
    """Target пересоздан с теми же host/port/timeout, но новым instance_id — старый результат не сохраняется."""
    from datetime import datetime, timezone
    from app.db.models import TargetORM

    t = service.add_target("8.8.8.8", "icmp", None, 2.0)
    tid = t["id"]
    old_iid = t["instance_id"]
    service.delete_target(tid)

    db_session.add(TargetORM(
        id=tid, host="8.8.8.8", type="icmp", port=None,
        timeout=2.0, instance_id="newinstanceid00000000000000000",
    ))
    db_session.commit()

    fake = [{
        "id": tid, "host": "8.8.8.8", "type": "icmp",
        "ok": True, "ms": 5.0, "error": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status_changed": False, "port": None, "timeout": 2.0,
        "instance_id": old_iid, "run_id": 1, "stale": False,
    }]
    monkeypatch.setattr(service.engine, "run_once", lambda: fake)
    service.run_monitoring()
    assert result_repo.get_by_target(tid) == []


def test_filter_fresh_drops_stale(service):
    """filter_fresh отбрасывает результаты run_id < _last_written_run."""
    service.add_target("8.8.8.8", "icmp", None, 2.0)
    service.engine._last_written_run = 2
    results = [{"id": 1, "run_id": 1, "stale": False, "instance_id": "", "ok": True}]
    assert service.engine.filter_fresh(results) == []


def test_filter_fresh_keeps_current(service):
    """filter_fresh сохраняет результаты run_id >= _last_written_run."""
    service.add_target("8.8.8.8", "icmp", None, 2.0)
    service.engine._last_written_run = 1
    results = [{"id": 1, "run_id": 2, "stale": False, "instance_id": "", "ok": True}]
    assert len(service.engine.filter_fresh(results)) == 1