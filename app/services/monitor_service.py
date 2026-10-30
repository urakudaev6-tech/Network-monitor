"""Сервисный слой: связывает MonitorEngine (сеть) и Repository (БД).

Правила:
- Транзакция БД НЕ держится во время сетевых проверок.
- Новая сессия на каждую операцию — не передаём session между потоками.
- Сохранение результатов одного запуска — одна транзакция (в repo.save_results).
- add/delete синхронизируют engine и DB под service._lock.
- run_monitoring: engine.run_once() (сеть, без lock) → repo.save_results (под lock).
- Если save_results падает — пробрасываем наружу, клиент получает 503, а не ложь.
"""

import threading

from sqlalchemy.exc import IntegrityError

from app.db.repository import CheckResultRepository, TargetRepository
from app.monitoring.engine import DuplicateIdError, MonitorEngine
from app.monitoring.models import Target


class MonitorService:

    def __init__(self, engine: MonitorEngine, session_factory):
        self.engine = engine
        self.session_factory = session_factory
        self._lock = threading.RLock()

    # ---------- Загрузка из БД ----------

    def load_from_db(self) -> int:
        import uuid
        with self.session_factory() as session:
            tr = TargetRepository(session)
            orms = tr.get_all()
            engine_targets = []
            for t in orms:
                if not t.instance_id:
                    t.instance_id = uuid.uuid4().hex
                engine_targets.append(Target(
                    id=t.id, host=t.host, type=t.type,
                    port=t.port, timeout=t.timeout,
                    instance_id=t.instance_id,
                ))
            session.commit()
        self.engine.set_targets(engine_targets)
        return len(engine_targets)

    # ---------- Чтение ----------

    def list_targets(self) -> list[dict]:
        with self.session_factory() as session:
            orms = TargetRepository(session).get_all()
            return [
                {"id": t.id, "host": t.host, "type": t.type,
                 "port": t.port, "timeout": t.timeout}
                for t in orms
            ]

    def get_target(self, target_id: int) -> dict | None:
        with self.session_factory() as session:
            t = TargetRepository(session).get_by_id(target_id)
            if t is None:
                return None
            return {"id": t.id, "host": t.host, "type": t.type,
                    "port": t.port, "timeout": t.timeout}

    def get_history(self, target_id: int, limit: int = 100) -> list[dict] | None:
        """История проверок target'а. None — если target не существует."""
        with self.session_factory() as session:
            tr = TargetRepository(session)
            if tr.get_by_id(target_id) is None:
                return None
            rr = CheckResultRepository(session)
            rows = rr.get_by_target(target_id, limit=limit)
            return [
                {
                    "id": r.id,
                    "target_id": r.target_id,
                    "ok": r.ok,
                    "ms": r.ms,
                    "error": r.error,
                    "checked_at": r.checked_at.isoformat(),
                    "status_changed": r.status_changed,
                }
                for r in rows
            ]

    def get_last_results(self) -> list[dict]:
        """Последние результаты из in-memory engine (для /monitor/results)."""
        return self.engine.get_last_results()

    # ---------- Запись ----------

    def add_target(self, host: str, type_: str, port: int | None,
                   timeout: float, id_: int | None = None) -> dict:
        with self._lock:
            try:
                with self.session_factory() as session:
                    orm = TargetRepository(session).create(
                        host=host, type_=type_, port=port,
                        timeout=timeout, id_=id_,
                    )
                    new_id = orm.id
                    new_instance_id = orm.instance_id
            except IntegrityError as e:
                raise DuplicateIdError(f"id уже существует: {e}") from e
            except Exception as e:
                raise RuntimeError(f"db error: {e}") from e

            try:
                self.engine.add_target(Target(
                    id=new_id, host=host, type=type_,
                    port=port, timeout=timeout,
                    instance_id=new_instance_id,
                ))
            except Exception:
                with self.session_factory() as session:
                    TargetRepository(session).delete(new_id)
                raise

            return {"id": new_id, "host": host, "type": type_,
                    "port": port, "timeout": timeout,
                    "instance_id": new_instance_id}
    def delete_target(self, target_id: int) -> bool:
        with self._lock:
            with self.session_factory() as session:
                deleted = TargetRepository(session).delete(target_id)
            if not deleted:
                return False
            self.engine.remove_target(target_id)
            return True
    def run_monitoring(self) -> list[dict]:
        results = self.engine.run_once()
        if not results:
            return results

        def _persist(fresh: list[dict]) -> int:
            with self.session_factory() as session:
                current = {t.id: t for t in TargetRepository(session).get_all()}
                filtered = []
                for r in fresh:
                    cur = current.get(r["id"])
                    if cur is None:
                        continue
                    if r.get("instance_id") and cur.instance_id != r["instance_id"]:
                        continue
                    if (
                        cur.host != r["host"]
                        or cur.type != r["type"]
                        or cur.port != r.get("port")
                        or cur.timeout != r.get("timeout")
                    ):
                        continue
                    filtered.append(r)
                if filtered:
                    CheckResultRepository(session).save_results(filtered)
                return len(filtered)

        try:
            self.engine.save_fresh(results, _persist)
        except Exception as e:
            raise RuntimeError(f"failed to persist results: {e}") from e

        return results