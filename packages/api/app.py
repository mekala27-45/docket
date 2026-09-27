"""Token-gated API. Raw uploads remain in memory and are never logged or stored."""

from __future__ import annotations

import asyncio
import copy
import hmac
import io
import json
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from packages.api.store import Audit, Base, Correction, Document, ModelRun, make_engine, purge_expired
from packages.redact import redact_image, redact_payload
from packages.rules import validate_document

MAX_UPLOAD = 10 * 1024 * 1024
MAX_PIXELS = 25_000_000
ALLOWED_FIELDS = {"vendor", "number", "date", "due_date", "currency", "subtotal", "tax", "total", "po_number"}
ROOT = Path(__file__).resolve().parents[2]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: dict[str, str | float | int | None] = Field(default_factory=dict, max_length=20)
    line_items: list[dict[str, Any]] | None = Field(default=None, max_length=200)
    decision: Literal["accept", "reject"]
    reason: str = Field(default="", max_length=1000)


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str = Field(max_length=128)
    backend: Literal["rules", "tokens"] = "rules"


def normalize_upload(raw: bytes, content_type: str | None) -> bytes:
    """Strictly decode one supported page and return metadata-free PNG in memory."""
    if not raw or len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Upload must contain between 1 byte and 10 MiB")
    if raw.startswith(b"%PDF-"):
        import pypdfium2 as pdfium

        try:
            pdf = pdfium.PdfDocument(raw)
            try:
                if len(pdf) != 1:
                    raise HTTPException(422, "This demo accepts single-page PDFs")
                page = pdf[0]
                width, height = page.get_size()
                if width * height * 4 > MAX_PIXELS:
                    raise HTTPException(413, "Rendered PDF exceeds the pixel limit")
                bitmap = page.render(scale=2)
                canvas = bitmap.to_pil().convert("RGB")
                bitmap.close()
                page.close()
            finally:
                pdf.close()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(422, "PDF cannot be decoded") from exc
    else:
        if content_type not in {"image/png", "image/jpeg", "image/webp", "application/octet-stream", None}:
            raise HTTPException(415, "Use PNG, JPEG, WebP, or a single-page PDF")
        try:
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise HTTPException(415, "Unsupported image encoding")
                if source.width * source.height > MAX_PIXELS or getattr(source, "n_frames", 1) != 1:
                    raise HTTPException(413, "Image exceeds the pixel limit or contains multiple frames")
                canvas = source.convert("RGB")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise HTTPException(422, "Image cannot be decoded") from exc
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def create_app(database_url: str | None = None, write_token: str | None = None, seed_path: Path | None = None) -> FastAPI:
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", "sqlite:///./docket.sqlite3"))
    configured_token = write_token if write_token is not None else os.environ.get("DOCKET_WRITE_TOKEN", "")
    seed_file = seed_path if seed_path is not None else Path(os.environ.get("DOCKET_SEED_PATH", str(ROOT / "web/public/data/demo.json")))

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        if seed_file.exists():
            bundle = json.loads(seed_file.read_text(encoding="utf-8"))
            with Session(engine) as session, session.begin():
                for payload in bundle.get("documents", []):
                    if session.get(Document, payload["id"]) is None:
                        safe, _ = redact_payload(payload)
                        session.add(Document(id=safe["id"], payload=safe, source=safe.get("source", "generated")))
        purge_expired(engine)
        async def retention_loop() -> None:
            while True:
                await asyncio.sleep(60)
                await run_in_threadpool(purge_expired, engine)

        retention_task = asyncio.create_task(retention_loop())
        try:
            yield
        finally:
            retention_task.cancel()
            with suppress(asyncio.CancelledError):
                await retention_task
            engine.dispose()

    app = FastAPI(title="docket", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    retrain_lock = asyncio.Lock()
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if not configured_token:
            raise HTTPException(503, "Writes are disabled until DOCKET_WRITE_TOKEN is configured")
        supplied = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
        if not hmac.compare_digest(supplied.encode(), configured_token.encode()):
            raise HTTPException(401, "A valid write token is required")

    def fetch(session: Session, document_id: str) -> Document:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(404, "Document not found")
        return document

    @app.get("/health")
    def health() -> dict[str, Any]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "storage": engine.dialect.name, "writes_enabled": bool(configured_token), "demo": True}

    @app.get("/v1/queue")
    def queue() -> dict[str, Any]:
        with Session(engine) as session:
            documents = list(session.scalars(select(Document)))
            documents.sort(key=lambda doc: (-float(doc.payload.get("risk", 1)), doc.created_at, doc.id))
            return {"documents": [doc.payload for doc in documents], "count": len(documents)}

    @app.get("/v1/documents/{document_id}")
    def document(document_id: str) -> dict[str, Any]:
        with Session(engine) as session:
            return fetch(session, document_id).payload

    @app.get("/v1/documents/{document_id}/image")
    def document_image(document_id: str) -> Response:
        with Session(engine) as session:
            stored = fetch(session, document_id)
            if stored.image is None:
                raise HTTPException(404, "Seed images are served by the static demonstration site")
            return Response(stored.image, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.get("/v1/trace/{document_id}")
    def trace(document_id: str) -> dict[str, Any]:
        with Session(engine) as session:
            payload = fetch(session, document_id).payload
            extraction = payload.get("extraction", payload)
            events = list(session.scalars(select(Audit).where(Audit.document_id == document_id).order_by(Audit.id)))
            return {"id": document_id, "fields": extraction.get("fields", {}), "audit": [{"id": event.id, "action": event.action, "detail": event.detail, "created_at": event.created_at.isoformat()} for event in events]}

    @app.post("/v1/review/{document_id}", dependencies=[Depends(authorize)])
    def review(document_id: str, request: ReviewRequest) -> dict[str, Any]:
        if not set(request.fields).issubset(ALLOWED_FIELDS):
            raise HTTPException(422, "Unknown review field")
        safe, redaction = redact_payload(request.model_dump())
        with Session(engine) as session, session.begin():
            stored = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
            if stored is None:
                raise HTTPException(404, "Document not found")
            payload = copy.deepcopy(stored.payload)
            extraction = payload.setdefault("extraction", {"fields": copy.deepcopy(payload.get("fields", {})), "line_items": payload.get("line_items", [])})
            fields = extraction.setdefault("fields", {})
            for name, value in safe["fields"].items():
                previous = fields.get(name, {})
                fields[name] = {**previous, "value": value, "reviewed": True, "trace": [*previous.get("trace", []), {"step": "human_review", "detail": "A reviewer supplied this value."}]}
            rows = safe["line_items"] if safe["line_items"] is not None else extraction.get("line_items", [])
            extraction["line_items"] = rows
            known = [row.payload for row in session.scalars(select(Document))]
            payload["rules"] = validate_document(payload, fields, rows, known_documents=known)
            payload["status"] = "accepted" if request.decision == "accept" else "rejected"
            payload["reviewed_at"] = datetime.now(UTC).isoformat()
            correction = Correction(document_id=document_id, fields={key: value.get("value") for key, value in fields.items()}, line_items=rows, decision=request.decision)
            event = Audit(document_id=document_id, action="review", detail={"decision": request.decision, "changed_fields": list(safe["fields"]), "reason": safe["reason"], "redaction": redaction})
            session.add_all([correction, event])
            session.flush()
            payload["audit_id"] = event.id
            stored.payload = payload
            audit_id = event.id
        # The transaction context has committed before control can reach this response.
        return {"document": payload, "audit_id": audit_id, "committed": True}

    @app.post("/v1/documents", dependencies=[Depends(authorize)], status_code=201)
    async def upload(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        raw = await file.read(MAX_UPLOAD + 1)
        await file.close()
        png = await run_in_threadpool(normalize_upload, raw, file.content_type)
        from packages.pipeline import process_image

        try:
            item = await run_in_threadpool(process_image, png, "upload.png")
            image_bytes = item.pop("_image_bytes", png)
            redacted, tokens, report = await run_in_threadpool(redact_image, image_bytes, item.get("tokens", []))
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(422, "OCR or redaction could not safely process this page") from exc
        item["tokens"] = tokens
        item, text_report = redact_payload(item)
        document_id = "upload-" + uuid.uuid4().hex
        now = datetime.now(UTC)
        item.update(id=document_id, source="upload", image=f"/v1/documents/{document_id}/image", created_at=now.isoformat(), retention_hours=24, redaction={**report, **text_report})
        # Uploaded suppliers and purchase orders have no verified master record.
        # Human review is required until a caller supplies that missing evidence.
        extraction = item.get("extraction", item)
        item["rules"] = validate_document(item, extraction.get("fields", {}), extraction.get("line_items", []))
        item["status"] = "needs_review"
        item["risk"] = max(float(item.get("risk", 1)), 0.8)
        with Session(engine) as session, session.begin():
            session.add(Document(id=document_id, payload=item, image=redacted, source="upload", expires_at=now + timedelta(hours=24)))
            session.add(Audit(document_id=document_id, action="upload", detail={"redaction": item["redaction"], "retention_hours": 24}))
        return item

    @app.post("/v1/extract", dependencies=[Depends(authorize)])
    async def extract(request: ExtractRequest) -> dict[str, Any]:
        with Session(engine) as session:
            original = copy.deepcopy(fetch(session, request.document_id).payload)
        from packages.pipeline import process_document

        result = await run_in_threadpool(process_document, original, request.backend)
        result, _ = redact_payload(result)
        with Session(engine) as session, session.begin():
            stored = fetch(session, request.document_id)
            stored.payload = result
            session.add(Audit(document_id=request.document_id, action="extract", detail={"backend": request.backend}))
        return result

    @app.post("/v1/retrain", dependencies=[Depends(authorize)])
    async def retrain() -> dict[str, Any]:
        with Session(engine) as session:
            latest: dict[str, Correction] = {}
            for correction in session.scalars(select(Correction).order_by(Correction.id)):
                latest[correction.document_id] = correction
            corrections = [{"document": copy.deepcopy(fetch(session, item.document_id).payload), "fields": item.fields, "line_items": item.line_items} for item in latest.values() if item.decision == "accept"]
        if not corrections:
            raise HTTPException(409, "Accept at least one correction before retraining")
        from packages.pipeline import retrain_from_corrections

        async with retrain_lock:
            report = await run_in_threadpool(retrain_from_corrections, corrections)
        report, _ = redact_payload(report)
        with Session(engine) as session, session.begin():
            record = ModelRun(report=report)
            session.add(record)
            session.add(Audit(action="retrain", detail={"corrections_used": report.get("corrections_used"), "split": report.get("split")}))
            session.flush()
            run_id = record.id
        return {"run_id": run_id, **report, "committed": True}

    @app.post("/v1/retention", dependencies=[Depends(authorize)])
    def retention() -> dict[str, int]:
        return {"deleted": purge_expired(engine)}

    return app


app = create_app()
