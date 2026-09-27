"""One transaction stores a review, its correction, and its audit event."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    create_engine,
    delete,
    event,
    inspect,
    select,
    text,
)
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
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
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


def initialize_schema(engine: Engine) -> None:
    """Add provenance columns without reclassifying older corrections as human."""
    Base.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("corrections")}
    for name in ("snapshot", "provenance"):
        if name not in columns:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE corrections ADD COLUMN {name} JSON NOT NULL DEFAULT '{{}}'"))


def accepted_corrections(session: Session) -> dict[str, Any]:
    """Export latest accepted review snapshots, never newer model predictions."""
    latest: dict[str, Correction] = {}
    for correction in session.scalars(select(Correction).order_by(Correction.id)):
        latest[correction.document_id] = correction
    records: list[dict[str, Any]] = []
    legacy = rejected = 0
    for correction in latest.values():
        if correction.decision != "accept":
            rejected += 1
            continue
        if not correction.snapshot or not correction.provenance:
            legacy += 1
            continue
        records.append({"document": correction.snapshot, "fields": correction.fields,
                        "line_items": correction.line_items if correction.provenance.get("line_items_reviewed") else None,
                        "decision": "accept", "provenance": {**correction.provenance,
                            "correction_id": correction.id, "document_id": correction.document_id,
                            "created_at": correction.created_at.isoformat()}})
    return {"schema_version": 1, "source": "docket_api", "exported_at": datetime.now(UTC).isoformat(),
            "count": len(records), "records": records, "records_sha256": correction_records_digest(records),
            "provenance_counts": dict(Counter(record["provenance"]["kind"] for record in records)),
            "excluded_latest_rejections": rejected, "excluded_legacy_without_provenance": legacy,
            "human_review_count_definition": "Client-declared human origin on accepted API reviews; identity is not verified."}


def correction_records_digest(records: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


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
