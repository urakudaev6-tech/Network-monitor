"""Тесты Repository layer: CRUD + история + каскад + транзакции."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import CheckResultORM


# ---------- TargetRepository ----------


def test_create_target(target_repo):
    orm = target_repo.create("8.8.8.8", "icmp", None, 2.0)
    assert orm.id is not None
    assert orm.host == "8.8.8.8"
    assert orm.created_at is not None


def test_get_by_id(target_repo):
    orm = target_repo.create("8.8.8.8", "icmp", None, 2.0)
    found = target_repo.get_by_id(orm.id)
    assert found is not None
    assert found.id == orm.id


def test_get_by_id_missing(target_repo):
    assert target_repo.get_by_id(9999) is None


def test_get_all_ordered_by_id(target_repo):
    target_repo.create("a", "icmp", None, 2.0)
    target_repo.create("b", "icmp", None, 2.0)
    target_repo.create("c", "icmp", None, 2.0)
    ids = [t.id for t in target_repo.get_all()]
    assert ids == sorted(ids)


def test_delete_target(target_repo):
    orm = target_repo.create("8.8.8.8", "icmp", None, 2.0)
    assert target_repo.delete(orm.id) is True
    assert target_repo.get_by_id(orm.id) is None


def test_delete_missing(target_repo):
    assert target_repo.delete(9999) is False


# ---------- CheckResultRepository ----------


def _mk_result(target_id: int, ok: bool = True, ms: float | None = 5.0,
               error: str | None = None, changed: bool = False,
               checked_at: datetime | None = None) -> dict:
    return {
        "id": target_id,
        "ok": ok,
        "ms": ms,
        "error": error,
        "checked_at": (checked_at or datetime.now(timezone.utc)).isoformat(),
        "status_changed": changed,
    }


def test_save_results_one_transaction(target_repo, result_repo):
    t = target_repo.create("8.8.8.8", "icmp", None, 2.0)
    n = result_repo.save_results([
        _mk_result(t.id, ok=True),
        _mk_result(t.id, ok=False, ms=None, error="timeout", changed=True),
    ])
    assert n == 2
    history = result_repo.get_by_target(t.id)
    assert len(history) == 2


def test_save_empty_results_noop(result_repo):
    assert result_repo.save_results([]) == 0


def test_get_by_target_newest_first(target_repo, result_repo):
    t = target_repo.create("8.8.8.8", "icmp", None, 2.0)
    t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
    result_repo.save_results([
        _mk_result(t.id, ok=True, checked_at=t1),
        _mk_result(t.id, ok=False, checked_at=t2),
    ])
    history = result_repo.get_by_target(t.id)
    assert history[0].checked_at > history[1].checked_at


def test_get_by_target_limit(target_repo, result_repo):
    t = target_repo.create("8.8.8.8", "icmp", None, 2.0)
    for i in range(5):
        result_repo.save_results([_mk_result(t.id, ok=True)])
    assert len(result_repo.get_by_target(t.id, limit=3)) == 3


def test_get_latest(target_repo, result_repo):
    t = target_repo.create("8.8.8.8", "icmp", None, 2.0)
    t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
    result_repo.save_results([
        _mk_result(t.id, ok=True, checked_at=t1),
        _mk_result(t.id, ok=False, checked_at=t2),
    ])
    latest = result_repo.get_latest(t.id)
    assert latest is not None
    assert latest.ok is False


# ---------- Каскадное удаление ----------


def test_cascade_delete_results(target_repo, result_repo, db_session):
    t = target_repo.create("8.8.8.8", "icmp", None, 2.0)
    result_repo.save_results([_mk_result(t.id, ok=True)])
    result_repo.save_results([_mk_result(t.id, ok=False)])

    assert db_session.query(CheckResultORM).filter_by(target_id=t.id).count() == 2
    target_repo.delete(t.id)
    # после удаления target'а — результатов тоже нет
    assert db_session.query(CheckResultORM).filter_by(target_id=t.id).count() == 0


# ---------- Транзакции ----------


def test_save_results_rollback_on_error(target_repo, result_repo, db_session):
    """Если в батче есть битая строка — вся транзакция откатывается."""
    t = target_repo.create("8.8.8.8", "icmp", None, 2.0)

    bad = _mk_result(t.id, ok=True)
    bad["checked_at"] = "not-a-date"    # datetime.fromisoformat упадёт

    with pytest.raises(ValueError):
        result_repo.save_results([_mk_result(t.id, ok=True), bad])

    # ничего не сохранилось
    assert db_session.query(CheckResultORM).filter_by(target_id=t.id).count() == 0


def test_save_results_fk_violation_rolls_back(target_repo, result_repo, db_session):
    """target_id, которого нет в targets — IntegrityError, вся транзакция откатывается."""
    t = target_repo.create("8.8.8.8", "icmp", None, 2.0)

    with pytest.raises(IntegrityError):
        result_repo.save_results([
            _mk_result(t.id, ok=True),
            _mk_result(99999, ok=True),     # нет такого target
        ])

    # даже валидная строка откатилась
    assert db_session.query(CheckResultORM).filter_by(target_id=t.id).count() == 0