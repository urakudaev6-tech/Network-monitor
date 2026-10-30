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
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    instance_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
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
        index=True,
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