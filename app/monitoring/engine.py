"""Движок Network Monitor: параллельная проверка списка target'ов.

Движок НЕ знает о БД и SQLAlchemy. Персистентность — отдельный слой
Repository, который будет вызываться из API/routes, а не из движка.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.monitoring.icmp import check_icmp
from app.monitoring.models import CheckResult, Target
from app.monitoring.tcp import check_tcp


class DuplicateIdError(ValueError):
    """ID устройства уже существует."""


class MonitorEngine:

    def __init__(self, targets: list, max_workers: int = 5):
        if isinstance(max_workers, bool):
            raise ValueError("max_workers не может быть bool")
        if not isinstance(max_workers, int):
            raise TypeError(
                f"max_workers должен быть int, получено {type(max_workers).__name__}"
            )
        if max_workers < 1:
            raise ValueError(f"max_workers должен быть >= 1, получено {max_workers}")

        self.targets = [
            t if isinstance(t, Target) else Target.from_dict(t)
            for t in targets
        ]

        seen = set()
        for t in self.targets:
            if t.id is None:
                raise ValueError("target без id: id обязателен")
            if t.id in seen:
                raise DuplicateIdError(f"Дублирующийся id={t.id} в targets")
            seen.add(t.id)

        self.max_workers = max_workers
        self._last_results: dict = {}
        self._lock = threading.RLock()
        self._run_counter = 0
        self._last_written_run = 0

    def _check_one(self, target: Target, run_id: int) -> dict:
        checked_at = datetime.now(timezone.utc)
        try:
            if target.type == "icmp":
                raw = check_icmp(target.host, timeout=target.timeout)
            elif target.type == "tcp":
                if target.port is None:
                    raise ValueError(
                        f"target {target.id}: для type='tcp' обязателен port"
                    )
                raw = check_tcp(target.host, target.port, timeout=target.timeout)
            else:
                raise ValueError(
                    f"target {target.id}: неизвестный type={target.type!r}"
                )
            ok = bool(raw.get("ok", False))
            ms = raw.get("ms")
            error = raw.get("error")
        except Exception as exc:
            ok = False
            ms = None
            error = f"engine error: {exc}"

        result = CheckResult(
            id=target.id,
            host=target.host,
            type=target.type,
            ok=ok,
            ms=ms,
            error=error,
            checked_at=checked_at,
            status_changed=False,
        ).to_dict()
        result["port"] = target.port
        result["timeout"] = target.timeout
        result["instance_id"] = target.instance_id
        result["run_id"] = run_id
        result["stale"] = False
        return result
    def run_once(self) -> list[dict]:
        with self._lock:
            self._run_counter += 1
            my_run = self._run_counter
            snapshot = list(self.targets)

        results_by_id: dict = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(self._check_one, t, my_run) for t in snapshot]
            for fut in as_completed(futures):
                r = fut.result()
                results_by_id[r["id"]] = r

        results = [results_by_id[t.id] for t in snapshot if t.id in results_by_id]

        with self._lock:
            is_stale = my_run < self._last_written_run
            current_by_id = {t.id: t for t in self.targets}

            for r in results:
                r["stale"] = is_stale
                if is_stale:
                    r["status_changed"] = False
                    continue
                cur = current_by_id.get(r["id"])
                if cur is None:
                    continue
                if cur.instance_id and cur.instance_id != r.get("instance_id"):
                    r["stale"] = True
                    r["status_changed"] = False
                    continue
                prev = self._last_results.get(r["id"])
                r["status_changed"] = (prev["ok"] != r["ok"]) if prev else False
                self._last_results[r["id"]] = dict(r)

            if not is_stale:
                self._last_written_run = my_run

        return results
    def get_last_results(self) -> list[dict]:
        """Копии истории в порядке targets, под lock."""
        with self._lock:
            out = []
            for t in self.targets:
                r = self._last_results.get(t.id)
                if r is not None:
                    out.append(dict(r))
            return out

    def set_targets(self, targets: list) -> None:
        """Атомарно заменяет список, сохраняя историю по оставшимся id."""
        with self._lock:
            new_targets = [
                t if isinstance(t, Target) else Target.from_dict(t)
                for t in targets
            ]
            seen = set()
            for t in new_targets:
                if t.id is None:
                    raise ValueError("target без id: id обязателен")
                if t.id in seen:
                    raise DuplicateIdError(f"Дублирующийся id={t.id} в targets")
                seen.add(t.id)

            self.targets = new_targets
            current_ids = {t.id for t in new_targets}
            self._last_results = {
                k: v for k, v in self._last_results.items() if k in current_ids
            }

    def add_target(self, target: Target) -> Target:
        with self._lock:
            existing_ids = {t.id for t in self.targets}
            if target.id is None:
                target = Target(
                    id=max(existing_ids, default=0) + 1,
                    host=target.host, type=target.type,
                    port=target.port, timeout=target.timeout,
                    instance_id=target.instance_id or uuid.uuid4().hex,
                )
            elif not target.instance_id:
                target = Target(
                    id=target.id, host=target.host, type=target.type,
                    port=target.port, timeout=target.timeout,
                    instance_id=uuid.uuid4().hex,
                )
            if target.id in existing_ids:
                raise DuplicateIdError(f"id={target.id} уже существует")
            self.targets.append(target)
            return target
    def remove_target(self, target_id: int) -> bool:
        """Атомарно: поиск + удаление + чистка истории — одна операция под lock."""
        with self._lock:
            for i, t in enumerate(self.targets):
                if t.id == target_id:
                    del self.targets[i]
                    self._last_results.pop(target_id, None)
                    return True
            return False
    def save_fresh(self, results: list[dict], saver) -> int:
        """Атомарно: фильтрует fresh + сохраняет через `saver` — под одним RLock.

        Закрывает окно между filter_fresh() и save_results(): другой run_once
        не может записать новый run между проверкой и сохранением.
        """
        with self._lock:
            fresh = [
                r for r in results
                if not r.get("stale") and r.get("run_id", 0) >= self._last_written_run
            ]
            if not fresh:
                return 0
            return saver(fresh)
    def filter_fresh(self, results: list[dict]) -> list[dict]:
        """Отбрасывает stale-результаты под lock — закрывает окно между run_once и save."""
        with self._lock:
            return [
                r for r in results
                if not r.get("stale") and r.get("run_id", 0) >= self._last_written_run
            ]