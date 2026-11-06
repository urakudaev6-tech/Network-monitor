"""Pydantic-схемы для API."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TargetCreate(BaseModel):
    """Тело POST /targets. id опционален — если не передан, генерируется."""

    id: int | None = Field(default=None, ge=1)
    host: str = Field(min_length=1)
    type: Literal["icmp", "tcp"]
    port: int | None = Field(default=None, ge=1, le=65535)
    timeout: float = Field(default=2.0, gt=0, allow_inf_nan=False)

    @field_validator("host")
    @classmethod
    def _host_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("host не может быть пустым или из пробелов")
        return stripped

    @model_validator(mode="after")
    def _check_tcp_port(self):
        if self.type == "tcp" and self.port is None:
            raise ValueError("для type='tcp' обязателен port")
        return self


class TargetResponse(BaseModel):
    id: int
    host: str
    type: str
    port: int | None
    timeout: float


class MonitorResultResponse(BaseModel):
    id: int
    host: str
    type: str
    ok: bool
    ms: float | None
    error: str | None
    checked_at: str
    status_changed: bool
class CheckResultResponse(BaseModel):
    id: int                     # check_result.id
    target_id: int
    ok: bool
    ms: float | None
    error: str | None
    checked_at: str
    status_changed: bool

class ScanRequest(BaseModel):
    subnet: str = Field(min_length=3, max_length=43)
    timeout: float = Field(default=0.8, ge=0.2, le=5.0, allow_inf_nan=False)
    workers: int = Field(default=32, ge=1, le=64)
    retries: int = Field(default=1, ge=0, le=2)


class ScanDevice(BaseModel):
    ip: str
    detected: bool
    mac: str | None
    hostname: str | None
    latency_ms: float | None
    error: str | None


class ScanResponse(BaseModel):
    subnet: str
    scanned_at: str
    total: int
    detected: int
    not_detected: int
    devices: list[ScanDevice]
    warning: str


class DeviceUpdate(BaseModel):
    label: str = Field(default="", max_length=100)
    category: Literal["pc", "server", "printer", "router", "phone", "iot", "other"] = "other"
    notes: str = Field(default="", max_length=2000)
