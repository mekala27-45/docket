"""One transaction stores a review, its correction, and its audit event."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, LargeBinary, String, create_engine, delete, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    reference: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="generated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Correction(Base):
    __tablename__ = "corrections"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    fields: Mapped[dict[str, Any]] = mapped_column(JSON)
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


def make_engine(url: str) -> Engine:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}, pool_pre_ping=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection: Any, _: Any) -> None:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
    return engine


def purge_expired(engine: Engine, now: datetime | None = None) -> int:
    """Delete expired upload pixels, extracted text, corrections, and audit text."""
    with Session(engine) as session, session.begin():
        ids = list(session.scalars(select(Document.id).where(Document.source == "upload", Document.expires_at <= (now or datetime.now(UTC)))))
        if not ids:
            return 0
        session.execute(delete(Correction).where(Correction.document_id.in_(ids)))
        session.execute(delete(Audit).where(Audit.document_id.in_(ids)))
        session.execute(delete(Document).where(Document.id.in_(ids)))
        session.add(Audit(action="retention", detail={"expired_uploads_deleted": len(ids)}))
    return len(ids)
