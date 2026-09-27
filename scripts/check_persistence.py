"""Start an API process, upload/review, and verify from another fresh process."""

from __future__ import annotations

import io
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.api.store import Audit, Correction, Document, make_engine


def verify_database(url: str, document_id: str, audit_id: int) -> None:
    engine = make_engine(url)
    try:
        with Session(engine) as session:
            stored = session.get(Document, document_id)
            assert stored is not None and stored.payload["status"] == "accepted"
            correction = session.scalar(select(Correction).where(Correction.document_id == document_id))
            assert correction is not None and correction.fields["total"] == 123.45
            audit = session.get(Audit, audit_id)
            assert audit is not None and audit.action == "review" and audit.document_id == document_id
            assert stored.image and stored.source == "upload"
    finally:
        engine.dispose()
    print(json.dumps({"independent_process": True, "correction_committed": True, "audit_committed": True}))


def run() -> None:
    token = secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory(prefix="docket-persistence-") as directory:
        temporary = Path(directory)
        database_url = "sqlite:///" + (temporary / "check.sqlite3").as_posix()
        seed = temporary / "seed.json"
        seed.write_text('{"documents": []}', encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = {**os.environ, "DATABASE_URL": database_url, "DOCKET_WRITE_TOKEN": token, "DOCKET_SEED_PATH": str(seed)}
        with (temporary / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "packages.api.app:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=environment, stdout=log, stderr=log)
            try:
                address = f"http://127.0.0.1:{port}"
                with httpx.Client(base_url=address, timeout=90) as client:
                    deadline = time.monotonic() + 30
                    while True:
                        if server.poll() is not None:
                            raise RuntimeError("API exited before the persistence check")
                        try:
                            if client.get("/health").is_success:
                                break
                        except httpx.ConnectError:
                            pass
                        if time.monotonic() > deadline:
                            raise TimeoutError("API health did not become ready")
                        time.sleep(0.2)
                    image = Image.new("RGB", (1000, 800), "white")
                    drawing = ImageDraw.Draw(image)
                    for index, line in enumerate(["INVOICE", "Vendor: Example Supplies", "Invoice: INV-246", "Date: 2026-09-20", "Due date: 2026-09-26", "Currency: USD", "Subtotal: 100.00", "Tax: 8.00", "Total: 108.00"]):
                        drawing.text((70, 60 + 65 * index), line, fill="black", font_size=32)
                    buffer = io.BytesIO()
                    image.save(buffer, "PNG")
                    uploaded = client.post("/v1/documents", headers={"Authorization": f"Bearer {token}"}, files={"file": ("generated.png", buffer.getvalue(), "image/png")})
                    uploaded.raise_for_status()
                    document_id = uploaded.json()["id"]
                    reviewed = client.post(f"/v1/review/{document_id}", headers={"Authorization": f"Bearer {token}"}, json={"fields": {"total": 123.45}, "decision": "accept", "reason": "Generated integration fixture"})
                    reviewed.raise_for_status()
                    audit_id = reviewed.json()["audit_id"]
                    subprocess.run([sys.executable, str(Path(__file__).resolve()), "--verify", database_url, document_id, str(audit_id)], cwd=ROOT, check=True, timeout=30)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=10)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        verify_database(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    else:
        run()
