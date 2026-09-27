import io
import json
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
