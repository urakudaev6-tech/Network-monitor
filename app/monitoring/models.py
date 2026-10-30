"""Модели данных для движка Network Monitor."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


TargetType = Literal["icmp", "tcp"]


@dataclass
class Target:
    id: int | None
    host: str
    type: str
    port: int | None = None
    timeout: float = 2.0
    instance_id: str = ""          # ← UUID экземпляра, меняется при пересоздании

    @classmethod
    def from_dict(cls, data: dict) -> "Target":
        if "id" not in data or data["id"] is None:
            raise ValueError("target без id: id обязателен и не может быть None")
        return cls(
            id=data["id"],
            host=data.get("host", ""),
            type=data.get("type", ""),
            port=data.get("port"),
            timeout=data.get("timeout", 2.0),
            instance_id=data.get("instance_id", ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "host": self.host,
            "type": self.type,
            "port": self.port,
            "timeout": self.timeout,
            "instance_id": self.instance_id,
        }


@dataclass
class CheckResult:
    id: int | None
    host: str
    type: str
    ok: bool
    ms: float | None
    error: str | None
    checked_at: datetime
    status_changed: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "host": self.host,
            "type": self.type,
            "ok": self.ok,
            "ms": self.ms,
            "error": self.error,
            "checked_at": self.checked_at.isoformat(),
            "status_changed": self.status_changed,
        }