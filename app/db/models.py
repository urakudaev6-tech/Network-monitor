"""ORM-модели: targets и check_results."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class TargetORM(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[str] = mapped_column(
        String(32), nullable=False,
        default=lambda: __import__("uuid").uuid4().hex,
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    results: Mapped[list["CheckResultORM"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CheckResultORM(Base):
    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("targets.id", ondelete="CASCADE"),
        nullable=False,

    )
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    target: Mapped[TargetORM] = relationship(back_populates="results")

    __table_args__ = (
        Index("ix_check_results_target_checked", "target_id", "checked_at"),
    )

class NetworkScanORM(Base):
    __tablename__ = "network_scans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subnet: Mapped[str] = mapped_column(String(43), nullable=False, index=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    detected: Mapped[int] = mapped_column(Integer, nullable=False)
    not_detected: Mapped[int] = mapped_column(Integer, nullable=False)
    devices: Mapped[list["NetworkScanDeviceORM"]] = relationship(back_populates="scan", cascade="all, delete-orphan", passive_deletes=True)
    events: Mapped[list["NetworkEventORM"]] = relationship(back_populates="scan", cascade="all, delete-orphan", passive_deletes=True)


class NetworkScanDeviceORM(Base):
    __tablename__ = "network_scan_devices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(Integer, ForeignKey("network_scans.id", ondelete="CASCADE"), nullable=False)
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mac: Mapped[str | None] = mapped_column(String(32))
    hostname: Mapped[str | None] = mapped_column(String(255))
    latency_ms: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    scan: Mapped[NetworkScanORM] = relationship(back_populates="devices")
    __table_args__ = (Index("ix_scan_device_scan_ip", "scan_id", "ip", unique=True),)


class NetworkEventORM(Base):
    __tablename__ = "network_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(Integer, ForeignKey("network_scans.id", ondelete="CASCADE"), nullable=False)
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(255))
    new_value: Mapped[str | None] = mapped_column(String(255))
    scan: Mapped[NetworkScanORM] = relationship(back_populates="events")
    __table_args__ = (Index("ix_network_event_scan", "scan_id"),)

class DeviceInventoryORM(Base):
    """Inventory entry for an observed subnet/IP; MAC is evidence, not a guaranteed unique ID."""
    __tablename__ = "device_inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subnet: Mapped[str] = mapped_column(String(43), nullable=False)
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="other")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mac: Mapped[str | None] = mapped_column(String(32))
    hostname: Mapped[str | None] = mapped_column(String(255))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_scan_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detected_last_scan: Mapped[bool] = mapped_column(Boolean, nullable=False)
    __table_args__ = (Index("ix_inventory_subnet_ip", "subnet", "ip", unique=True),)
