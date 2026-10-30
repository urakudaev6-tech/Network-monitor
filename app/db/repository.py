"""Repository layer: единственное место, где живёт SQLAlchemy-логика.

Возвращает ORM-объекты (для внутреннего использования) или dict'ы — но никогда
не отдаёт ORM в HTTP-ответах напрямую (это делает API-слой).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CheckResultORM, TargetORM


class TargetRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, host: str, type_: str, port: int | None,
               timeout: float, id_: int | None = None) -> TargetORM:
        import uuid
        try:
            kwargs = {
                "host": host, "type": type_, "port": port,
                "timeout": timeout,
                "instance_id": uuid.uuid4().hex,
            }
            if id_ is not None:
                kwargs["id"] = id_
            orm = TargetORM(**kwargs)
            self.session.add(orm)
            self.session.commit()
            self.session.refresh(orm)
            return orm
        except Exception:
            self.session.rollback()
            raise

    def get_by_id(self, target_id: int) -> TargetORM | None:
        return self.session.get(TargetORM, target_id)

    def get_all(self) -> list[TargetORM]:
        return list(self.session.execute(select(TargetORM).order_by(TargetORM.id)).scalars())

    def delete(self, target_id: int) -> bool:
        try:
            orm = self.session.get(TargetORM, target_id)
            if orm is None:
                return False
            self.session.delete(orm)
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            raise


class CheckResultRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_results(self, results: list[dict]) -> int:
        """Сохраняет результаты одного прогона ОДНОЙ транзакцией."""
        if not results:
            return 0
        try:
            rows = []
            for r in results:
                checked_at = r["checked_at"]
                if isinstance(checked_at, str):
                    checked_at = datetime.fromisoformat(checked_at)
                rows.append(CheckResultORM(
                    target_id=r["id"],
                    ok=bool(r["ok"]),
                    ms=r.get("ms"),
                    error=r.get("error"),
                    checked_at=checked_at,
                    status_changed=bool(r.get("status_changed", False)),
                ))
            self.session.add_all(rows)
            self.session.commit()
            return len(rows)
        except Exception:
            self.session.rollback()
            raise

    def get_by_target(self, target_id: int, limit: int = 100) -> list[CheckResultORM]:
        q = (
            select(CheckResultORM)
            .where(CheckResultORM.target_id == target_id)
            .order_by(CheckResultORM.checked_at.desc(), CheckResultORM.id.desc())
            .limit(limit)
        )
        return list(self.session.execute(q).scalars())

    def get_latest(self, target_id: int) -> CheckResultORM | None:
        q = (
            select(CheckResultORM)
            .where(CheckResultORM.target_id == target_id)
            .order_by(CheckResultORM.checked_at.desc(), CheckResultORM.id.desc())
            .limit(1)
        )
        return self.session.execute(q).scalars().first()