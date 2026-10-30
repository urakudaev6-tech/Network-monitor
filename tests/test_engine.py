"""Тесты для MonitorEngine.

Сеть не используется: check_tcp и check_icmp подменяются моками.
"""

import time
from unittest.mock import patch

import pytest

from app.monitoring.engine import MonitorEngine
from app.monitoring.models import Target


@pytest.fixture
def icmp_target():
    return {"id": 1, "host": "8.8.8.8", "type": "icmp", "timeout": 2.0}


@pytest.fixture
def tcp_target():
    return {"id": 2, "host": "127.0.0.1", "type": "tcp", "port": 8000, "timeout": 2.0}


# ---------- Базовые результаты ----------


def test_first_run_status_changed_false(icmp_target):
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        engine = MonitorEngine([icmp_target])
        results = engine.run_once()

    assert len(results) == 1
    r = results[0]
    assert r["id"] == 1
    assert r["host"] == "8.8.8.8"
    assert r["type"] == "icmp"
    assert r["ok"] is True
    assert r["ms"] == 5.0
    assert r["error"] is None
    assert r["status_changed"] is False
    assert isinstance(r["checked_at"], str)

def test_result_has_all_fields(icmp_target):
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        engine = MonitorEngine([icmp_target])
        results = engine.run_once()

    expected = {
        "id", "host", "type", "ok", "ms", "error", "checked_at", "status_changed",
        "port", "timeout", "stale",
    }
    assert set(results[0].keys()) == expected

# ---------- Переходы UP ↔ DOWN ----------


def test_up_to_down(icmp_target):
    with patch("app.monitoring.engine.check_icmp") as mock:
        mock.return_value = {"ok": True, "ms": 5.0, "error": None}
        engine = MonitorEngine([icmp_target])
        r1 = engine.run_once()
        assert r1[0]["status_changed"] is False

        mock.return_value = {"ok": False, "ms": None, "error": "timeout"}
        r2 = engine.run_once()
        assert r2[0]["status_changed"] is True
        assert r2[0]["ok"] is False


def test_down_to_up(icmp_target):
    with patch("app.monitoring.engine.check_icmp") as mock:
        mock.return_value = {"ok": False, "ms": None, "error": "timeout"}
        engine = MonitorEngine([icmp_target])
        engine.run_once()

        mock.return_value = {"ok": True, "ms": 5.0, "error": None}
        r2 = engine.run_once()
        assert r2[0]["status_changed"] is True


def test_same_state_no_change(icmp_target):
    with patch("app.monitoring.engine.check_icmp") as mock:
        mock.return_value = {"ok": True, "ms": 5.0, "error": None}
        engine = MonitorEngine([icmp_target])
        engine.run_once()
        r2 = engine.run_once()
        assert r2[0]["status_changed"] is False


# ---------- Устойчивость ----------


def test_engine_does_not_crash_on_one_failure(icmp_target, tcp_target):
    def boom(*a, **kw):
        raise RuntimeError("boom")

    with patch("app.monitoring.engine.check_icmp", side_effect=boom), patch(
        "app.monitoring.engine.check_tcp",
        return_value={"ok": True, "ms": 1.0, "error": None},
    ):
        engine = MonitorEngine([icmp_target, tcp_target])
        results = engine.run_once()

    assert len(results) == 2
    by_id = {r["id"]: r for r in results}
    assert by_id[1]["ok"] is False
    assert "engine error" in by_id[1]["error"]
    assert by_id[2]["ok"] is True


def test_tcp_without_port_returns_error():
    bad = {"id": 3, "host": "127.0.0.1", "type": "tcp", "timeout": 2.0}
    engine = MonitorEngine([bad])
    results = engine.run_once()
    assert results[0]["ok"] is False
    assert "port" in results[0]["error"].lower()


def test_unknown_type_returns_error():
    bad = {"id": 4, "host": "example.com", "type": "udp", "timeout": 2.0}
    engine = MonitorEngine([bad])
    results = engine.run_once()
    assert results[0]["ok"] is False
    assert "type" in results[0]["error"].lower()


# ---------- Параллельность ----------


def test_parallel_execution():
    call_times = []

    def slow_check(*a, **kw):
        call_times.append(time.perf_counter())
        time.sleep(0.2)
        return {"ok": True, "ms": 200.0, "error": None}

    targets = [
        {"id": i, "host": f"h{i}", "type": "icmp", "timeout": 2.0}
        for i in range(5)
    ]
    with patch("app.monitoring.engine.check_icmp", side_effect=slow_check):
        engine = MonitorEngine(targets, max_workers=5)
        engine.run_once()

    assert len(call_times) == 5
    spread = max(call_times) - min(call_times)
    assert spread < 0.15, (
        f"проверки не параллельны: разброс старта {spread:.3f}s "
        f"(последовательно было бы ~0.8s)"
    )


# ---------- get_last_results ----------


def test_get_last_results_empty_before_run(icmp_target):
    engine = MonitorEngine([icmp_target])
    assert engine.get_last_results() == []


def test_get_last_results_after_run(icmp_target):
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        engine = MonitorEngine([icmp_target])
        engine.run_once()
        last = engine.get_last_results()

    assert len(last) == 1
    assert last[0]["id"] == 1


def test_get_last_results_preserves_config_order():
    targets = [
        {"id": 3, "host": "a", "type": "icmp", "timeout": 2.0},
        {"id": 1, "host": "b", "type": "icmp", "timeout": 2.0},
        {"id": 2, "host": "c", "type": "icmp", "timeout": 2.0},
    ]
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 1.0, "error": None},
    ):
        engine = MonitorEngine(targets)
        engine.run_once()
        last = engine.get_last_results()

    # порядок как в конфиге, а НЕ по id
    assert [r["id"] for r in last] == [3, 1, 2]
# ---------- Уникальность ID ----------


def test_target_from_dict_without_id_raises():
    from app.monitoring.models import Target
    with pytest.raises(ValueError, match="id"):
        Target.from_dict({"host": "8.8.8.8", "type": "icmp"})


def test_target_from_dict_none_id_raises():
    from app.monitoring.models import Target
    with pytest.raises(ValueError, match="id"):
        Target.from_dict({"id": None, "host": "8.8.8.8", "type": "icmp"})


def test_duplicate_ids_raise():
    targets = [
        {"id": 1, "host": "a", "type": "icmp", "timeout": 2.0},
        {"id": 1, "host": "b", "type": "icmp", "timeout": 2.0},
    ]
    with pytest.raises(ValueError, match="Дублирующийся"):
        MonitorEngine(targets)


def test_target_with_none_id_in_engine_raises():
    from app.monitoring.models import Target
    with pytest.raises(ValueError, match="id"):
        MonitorEngine([Target(id=None, host="a", type="icmp")])


# ---------- Валидация max_workers ----------


def test_max_workers_bool_raises(icmp_target):
    with pytest.raises(ValueError, match="bool"):
        MonitorEngine([icmp_target], max_workers=True)


def test_max_workers_string_raises(icmp_target):
    with pytest.raises(TypeError, match="int"):
        MonitorEngine([icmp_target], max_workers="5")


def test_max_workers_none_raises(icmp_target):
    with pytest.raises(TypeError, match="int"):
        MonitorEngine([icmp_target], max_workers=None)


def test_max_workers_zero_raises(icmp_target):
    with pytest.raises(ValueError, match=">= 1"):
        MonitorEngine([icmp_target], max_workers=0)


def test_max_workers_negative_raises(icmp_target):
    with pytest.raises(ValueError, match=">= 1"):
        MonitorEngine([icmp_target], max_workers=-1)


# ---------- Защита внутреннего состояния ----------


def test_get_last_results_returns_copies(icmp_target):
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        engine = MonitorEngine([icmp_target])
        engine.run_once()

        last1 = engine.get_last_results()
        last1[0]["ok"] = False           # ломаем копию
        last1[0]["host"] = "hacked"

        last2 = engine.get_last_results()
        assert last2[0]["ok"] is True
        assert last2[0]["host"] == "8.8.8.8"


def test_run_once_result_modification_does_not_affect_history(icmp_target):
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        engine = MonitorEngine([icmp_target])
        results = engine.run_once()
        results[0]["ok"] = False          # ломаем возвращённый dict

        last = engine.get_last_results()
        assert last[0]["ok"] is True


# ---------- Порядок результатов в run_once ----------


def test_run_once_results_preserve_config_order():
    targets = [
        {"id": 3, "host": "a", "type": "icmp", "timeout": 2.0},
        {"id": 1, "host": "b", "type": "icmp", "timeout": 2.0},
        {"id": 2, "host": "c", "type": "icmp", "timeout": 2.0},
    ]
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 1.0, "error": None},
    ):
        engine = MonitorEngine(targets)
        results = engine.run_once()

    assert [r["id"] for r in results] == [3, 1, 2]
# ---------- Out-of-order run_once ----------


def test_stale_run_does_not_overwrite_history():
    """Опоздавший run_once не перезаписывает историю более нового."""
    engine = MonitorEngine([{"id": 1, "host": "h", "type": "icmp"}])

    # 1-й прогон: UP — история записана
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 1.0, "error": None},
    ):
        engine.run_once()
    assert engine._last_results[1]["ok"] is True
    assert engine._last_written_run == 1

    # Имитируем: уже прошёл новый прогон с run_id=3.
    # Наш (следующий) получит run_id=2 — опоздает.
    engine._run_counter = 1          # следующий run_once → my_run=2
    engine._last_written_run = 3     # «новый» уже записан

    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": False, "ms": None, "error": "down"},
    ):
        results = engine.run_once()

    # Возвращённый результат — «down», но история осталась «UP» (не перезаписана)
    assert results[0]["ok"] is False
    assert results[0]["status_changed"] is False
    assert engine._last_results[1]["ok"] is True
    assert engine._last_written_run == 3
import threading
from app.monitoring.engine import DuplicateIdError, MonitorEngine


def test_concurrent_add_targets_unique_ids():
    engine = MonitorEngine([])
    errors = []

    def add():
        try:
            engine.add_target(Target(id=None, host="h", type="icmp"))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=add) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert not errors, f"ошибки: {errors}"
    ids = [t.id for t in engine.targets]
    assert len(ids) == 10
    assert len(set(ids)) == 10, f"дубликаты: {ids}"


def test_concurrent_add_duplicate_raises_for_one():
    engine = MonitorEngine([])
    results = []

    def add():
        try:
            engine.add_target(Target(id=1, host="h", type="icmp"))
            results.append("ok")
        except DuplicateIdError:
            results.append("dup")

    threads = [threading.Thread(target=add) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert sorted(results) == ["dup", "ok"]
    assert len(engine.targets) == 1


def test_concurrent_run_and_remove_does_not_crash():
    from unittest.mock import patch
    engine = MonitorEngine([
        {"id": i, "host": f"h{i}", "type": "icmp"} for i in range(1, 6)
    ])
    errors = []

    def run():
        try:
            with patch(
                "app.monitoring.engine.check_icmp",
                return_value={"ok": True, "ms": 1.0, "error": None},
            ):
                for _ in range(5):
                    engine.run_once()
        except Exception as e:
            errors.append(e)

    def remove():
        try:
            for i in range(1, 6):
                engine.remove_target(i)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=remove)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"крэши: {errors}"

def test_result_has_all_fields(icmp_target):
    with patch(
        "app.monitoring.engine.check_icmp",
        return_value={"ok": True, "ms": 5.0, "error": None},
    ):
        engine = MonitorEngine([icmp_target])
        results = engine.run_once()

    expected = {
        "id", "host", "type", "ok", "ms", "error", "checked_at", "status_changed",
        "port", "timeout", "instance_id", "run_id", "stale",
    }
    assert set(results[0].keys()) == expected