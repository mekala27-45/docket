import io
import json
import sys
import types
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from packages.api.app import create_app, normalize_upload
from packages.api.store import Audit, Base, Correction, Document, make_engine, purge_expired


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{(tmp_path / 'review.sqlite').as_posix()}"
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"documents": [{"id": "test-1", "source": "generated", "type": "invoice", "vendor": "Example Supplies", "po_number": "PO-1", "risk": 0.7, "extraction": {"fields": {"total": {"value": 10, "confidence": 0.6, "trace": []}}, "line_items": []}, "status": "needs_review"}]}))
    app = create_app(url, "test-token", seed)
    with TestClient(app) as client:
        yield client, app, url


def test_correction_is_committed(api):
    client, _, url = api
    response = client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"fields": {"total": 42.5}, "decision": "accept"})
    assert response.status_code == 200
    assert response.json()["committed"] is True
    independent_engine = make_engine(url)
    try:
        with Session(independent_engine) as session:
            correction = session.scalar(select(Correction))
            assert correction.fields["total"] == 42.5
            assert session.get(Document, "test-1").payload["status"] == "accepted"
            saved = session.get(Document, "test-1").payload
            assert saved["total"] == 42.5 and saved["risk"] == 0
            assert saved["extraction"]["fields"]["total"]["confidence"] is None
            assert saved["extraction"]["fields"]["total"]["model_confidence"] == 0.6
            assert session.get(Audit, response.json()["audit_id"]).action == "review"
    finally:
        independent_engine.dispose()


def test_audit_precedes_response(api):
    client, app, _ = api
    order = []

    @event.listens_for(app.state.engine, "commit")
    def committed(connection):
        order.append("commit")

    response = client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"fields": {"total": 21}, "decision": "accept"})
    order.append("response")
    assert response.status_code == 200
    assert order == ["commit", "response"]
    assert client.get("/v1/trace/test-1").json()["audit"][-1]["id"] == response.json()["audit_id"]


def test_failed_commit_cannot_acknowledge_review(api):
    client, app, _ = api

    def fail_commit(connection):
        raise RuntimeError("simulated persistence failure")

    event.listen(app.state.engine, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="persistence failure"):
        client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"fields": {"total": 999}, "decision": "accept"})
    event.remove(app.state.engine, "commit", fail_commit)
    with Session(app.state.engine) as session:
        assert session.scalar(select(Correction)) is None
        assert session.get(Document, "test-1").payload["status"] == "needs_review"


def test_writes_require_configured_token(api):
    client, _, _ = api
    for route in ["/v1/review/test-1", "/v1/retrain", "/v1/retention", "/v1/extract"]:
        response = client.post(route, json={"fields": {}, "decision": "accept"})
        assert response.status_code == 401
    response = client.post("/v1/review/test-1", headers={"Authorization": "Bearer incorrect"}, json={"decision": "accept"})
    assert response.status_code == 401


def test_unconfigured_writes_and_unknown_documents(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'disabled.sqlite'}", "", tmp_path / "missing.json")
    with TestClient(app) as client:
        assert client.post("/v1/retention").status_code == 503
        assert client.get("/v1/documents/missing").status_code == 404
        assert client.get("/health").json()["writes_enabled"] is False


def test_queue_sorted_by_risk(api):
    client, app, _ = api
    with Session(app.state.engine) as session, session.begin():
        session.add(Document(id="higher", payload={"id": "higher", "risk": 0.9}, source="generated"))
    assert client.get("/v1/queue").json()["documents"][0]["id"] == "higher"


def test_review_redacts_sensitive_reason_and_fields(api):
    client, app, _ = api
    response = client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"fields": {"vendor": "4111 1111 1111 1111"}, "reason": "account: 9876543210", "decision": "reject"})
    assert response.status_code == 200
    with Session(app.state.engine) as session:
        assert "4111" not in json.dumps(session.get(Document, "test-1").payload)
        assert "9876543210" not in json.dumps(session.scalar(select(Audit)).detail)


def test_retention_deletes_only_expired_uploads(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'retention.sqlite'}")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.add_all([Document(id="old", payload={}, source="upload", image=b"redacted", expires_at=now - timedelta(seconds=1)), Document(id="new", payload={}, source="upload", expires_at=now + timedelta(hours=1)), Document(id="seed", payload={}, source="generated", expires_at=now - timedelta(days=1))])
        session.flush()
        session.add(Correction(document_id="old", fields={"total": 10}, line_items=[], decision="accept"))
        session.add(Audit(document_id="old", action="review", detail={"reason": "user provided text"}))
    assert purge_expired(engine, now) == 1
    with Session(engine) as session:
        assert session.get(Document, "old") is None
        assert session.get(Document, "new") is not None
        assert session.get(Document, "seed") is not None
        assert session.scalar(select(Correction)) is None
        assert session.scalar(select(Audit).where(Audit.document_id == "old")) is None
    assert purge_expired(engine, now) == 0
    engine.dispose()


def test_upload_input_limits():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        normalize_upload(b"", "image/png")
    assert error.value.status_code == 413
    with pytest.raises(HTTPException):
        normalize_upload(b"not an image", "image/png")
    with pytest.raises(HTTPException):
        normalize_upload(b"<svg></svg>", "image/svg+xml")
    output = io.BytesIO()
    Image.new("RGB", (30, 30), "white").save(output, "PNG")
    assert normalize_upload(output.getvalue(), "image/png").startswith(b"\x89PNG")


def test_retrain_refuses_empty_corrections(api):
    client, _, _ = api
    assert client.post("/v1/retrain", headers={"Authorization": "Bearer test-token"}).status_code == 409


def test_upload_redaction_is_committed_before_response(api, monkeypatch):
    client, app, _ = api
    pipeline = types.ModuleType("packages.pipeline")
    output = io.BytesIO()
    Image.new("RGB", (300, 100), "white").save(output, "PNG")
    tokens = [{"text": "4111 1111 1111 1111", "box": [0.1, 0.2, 0.8, 0.4]}]

    def process_image(image_bytes, filename):
        assert filename == "upload.png"
        return {"id": "temporary", "tokens": tokens, "extraction": {"fields": {"number": {"value": "4111 1111 1111 1111"}}}, "_image_bytes": image_bytes}

    pipeline.process_image = process_image
    monkeypatch.setitem(sys.modules, "packages.pipeline", pipeline)
    response = client.post("/v1/documents", headers={"Authorization": "Bearer test-token"}, files={"file": ("untrusted-filename.png", output.getvalue(), "image/png")})
    assert response.status_code == 201
    document_id = response.json()["id"]
    assert document_id.startswith("upload-")
    with Session(app.state.engine) as session:
        stored = session.get(Document, document_id)
        assert "4111" not in json.dumps(stored.payload)
        assert "untrusted-filename" not in json.dumps(stored.payload)
        assert stored.expires_at is not None
        assert Image.open(io.BytesIO(stored.image)).getpixel((100, 40)) == (0, 0, 0)
    assert client.get(f"/v1/documents/{document_id}/image").status_code == 200
    assert client.get("/v1/documents/test-1/image").status_code == 404


def test_failed_redaction_never_persists_upload(api, monkeypatch):
    client, app, _ = api
    pipeline = types.ModuleType("packages.pipeline")
    pipeline.process_image = lambda image_bytes, filename: {"tokens": []}
    monkeypatch.setitem(sys.modules, "packages.pipeline", pipeline)
    image = io.BytesIO()
    Image.new("RGB", (30, 30), "white").save(image, "PNG")
    response = client.post("/v1/documents", headers={"Authorization": "Bearer test-token"}, files={"file": ("empty.png", image.getvalue(), "image/png")})
    assert response.status_code == 422
    with Session(app.state.engine) as session:
        assert len(list(session.scalars(select(Document)))) == 1


def test_retrain_uses_latest_accepted_corrections_and_commits_report(api, monkeypatch):
    from packages.api.store import ModelRun

    client, app, _ = api
    pipeline = types.ModuleType("packages.pipeline")
    calls = []

    def retrain(corrections):
        calls.append(corrections)
        return {"corrections_used": len(corrections), "split": "test", "before": {"value": 0.5}, "after": {"value": 0.6}, "model_path": "artifacts/isolated-model.pkl"}

    pipeline.retrain_from_corrections = retrain
    monkeypatch.setitem(sys.modules, "packages.pipeline", pipeline)
    for total in [41, 42]:
        client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"fields": {"total": total}, "decision": "accept"}).raise_for_status()
    response = client.post("/v1/retrain", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    assert len(calls) == 1 and len(calls[0]) == 1
    assert calls[0][0]["fields"]["total"] == 42
    with Session(app.state.engine) as session:
        assert session.get(ModelRun, response.json()["run_id"]).report["corrections_used"] == 1
    client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"decision": "reject"}).raise_for_status()
    assert client.post("/v1/retrain", headers={"Authorization": "Bearer test-token"}).status_code == 409


def test_extract_calls_pipeline_and_persists_sanitized_trace(api, monkeypatch):
    client, app, _ = api
    pipeline = types.ModuleType("packages.pipeline")

    def process_document(document, backend):
        assert backend == "rules"
        document["extraction"]["fields"]["total"]["trace"] = [{"detail": "account: 9876543210"}]
        return document

    pipeline.process_document = process_document
    monkeypatch.setitem(sys.modules, "packages.pipeline", pipeline)
    response = client.post("/v1/extract", headers={"Authorization": "Bearer test-token"}, json={"document_id": "test-1", "backend": "rules"})
    assert response.status_code == 200
    with Session(app.state.engine) as session:
        assert "9876543210" not in json.dumps(session.get(Document, "test-1").payload)


def test_pdf_upload_decoding_and_page_limit():
    from fastapi import HTTPException
    from reportlab.pdfgen import canvas

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(300, 400))
    pdf.drawString(20, 200, "Generated fixture")
    pdf.save()
    assert normalize_upload(output.getvalue(), "application/pdf").startswith(b"\x89PNG")
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    for _ in range(2):
        pdf.drawString(20, 200, "Generated fixture")
        pdf.showPage()
    pdf.save()
    with pytest.raises(HTTPException, match="single-page"):
        normalize_upload(output.getvalue(), "application/pdf")


def test_unknown_review_field_and_manual_retention(api):
    client, _, _ = api
    assert client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"fields": {"not_a_field": "value"}, "decision": "accept"}).status_code == 422
    assert client.post("/v1/review/missing", headers={"Authorization": "Bearer test-token"}, json={"decision": "accept"}).status_code == 404
    assert client.post("/v1/retention", headers={"Authorization": "Bearer test-token"}).json() == {"deleted": 0}


def test_retrain_reports_invalid_corrections_without_saving_model(api, monkeypatch):
    from packages.api.store import ModelRun

    client, app, _ = api
    pipeline = types.ModuleType("packages.pipeline")

    def reject_frozen_test(corrections):
        raise ValueError("Frozen test document")

    pipeline.retrain_from_corrections = reject_frozen_test
    monkeypatch.setitem(sys.modules, "packages.pipeline", pipeline)
    client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"fields": {"total": 42}, "decision": "accept"}).raise_for_status()
    response = client.post("/v1/retrain", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 422
    with Session(app.state.engine) as session:
        assert session.scalar(select(ModelRun)) is None


def test_review_checks_edited_vendor_against_independent_master(api):
    client, app, _ = api
    with Session(app.state.engine) as session, session.begin():
        stored = session.get(Document, "test-1")
        stored.reference = {"vendor_master": ["Example Supplies"], "po_reference": {"number": "PO-1"}}
    response = client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"fields": {"vendor": "Unlisted Vendor", "po_number": "WRONG-PO"}, "decision": "accept"})
    assert response.status_code == 200
    rules = {rule["id"]: rule for rule in response.json()["document"]["rules"]}
    assert rules["vendor"]["status"] == "fail"
    assert rules["purchase_order"]["status"] == "fail"
    assert "vendor_master" not in client.get("/v1/documents/test-1").json()


def test_upload_never_rolls_raw_multipart_file_to_disk(api, monkeypatch):
    import tempfile

    import starlette.formparsers

    client, _, _ = api
    pipeline = types.ModuleType("packages.pipeline")
    pipeline.process_image = lambda pixels, filename: {"tokens": [{"text": "safe", "box": [0.1, 0.1, 0.1, 0.1]}]}
    monkeypatch.setitem(sys.modules, "packages.pipeline", pipeline)
    created = []
    original = tempfile.SpooledTemporaryFile

    def capture(*args, **kwargs):
        file = original(*args, **kwargs)
        created.append(file)
        return file

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", capture)
    output = io.BytesIO()
    Image.effect_noise((1000, 1000), 100).convert("RGB").save(output, "PNG")
    assert len(output.getvalue()) > 1024 * 1024
    response = client.post("/v1/documents", headers={"Authorization": "Bearer test-token"}, files={"file": ("large.png", output.getvalue(), "image/png")})
    assert response.status_code == 201
    assert created and all(not file._rolled for file in created)


def test_upload_request_has_hard_limit(api):
    from packages.api.app import MAX_REQUEST

    client, _, _ = api
    response = client.post("/v1/documents", content=b"x" * (MAX_REQUEST + 1), headers={"Authorization": "Bearer test-token", "Content-Type": "multipart/form-data; boundary=test"})
    assert response.status_code == 413


def test_review_normalizes_browser_monetary_strings_and_blank_values(api):
    client, _, _ = api
    response = client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"fields": {"total": "123.45", "tax": ""}, "decision": "accept"})
    assert response.status_code == 200
    document = response.json()["document"]
    assert document["total"] == 123.45 and document["tax"] is None
    assert document["extraction"]["fields"]["total"]["value"] == 123.45
    assert client.post("/v1/review/test-1", headers={"Authorization": "Bearer test-token"}, json={"fields": {"total": "not an amount"}, "decision": "accept"}).status_code == 422
