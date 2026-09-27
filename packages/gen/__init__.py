"""Seeded fictional invoices, purchase orders and letters with word-level truth."""

import io
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageEnhance, ImageFilter
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from packages.core import ROOT, SEED, write_json

VENDORS = [
    {"name": "Northline Paper Co.", "currency": "USD", "code": "NLP"},
    {"name": "Morrow Studio Supply", "currency": "USD", "code": "MSS"},
    {"name": "Fieldwork Equipment", "currency": "EUR", "code": "FWE"},
    {"name": "Alder Office Goods", "currency": "GBP", "code": "AOG"},
]
PRODUCTS = ["Archival paper packs", "Desk organizers", "Shipping cartons", "Studio notebooks",
            "Task lamp assemblies", "Document sleeves", "Label rolls", "Cable organizers"]
WIDTH, HEIGHT = 612, 792


def make_document(index: int, split: str, seed: int = SEED) -> dict[str, Any]:
    rng = random.Random(seed + index)
    vendor = VENDORS[index % len(VENDORS)]
    kind = "purchase_order" if index % 3 == 2 else "invoice"
    rows: list[dict[str, Any]] = []
    for item in rng.sample(PRODUCTS, 3 + index % 3):
        qty, price = rng.randint(1, 9), rng.randint(650, 8750) / 100
        rows.append({"description": item, "quantity": qty, "unit_price": price, "amount": round(qty * price, 2)})
    subtotal = round(sum(r["amount"] for r in rows), 2)
    tax = round(subtotal * 0.08, 2)
    when = date(2026, 8, 3) + timedelta(days=index % 30)
    doc: dict[str, Any] = {
        "id": f"gen-{index:04d}", "type": kind, "vendor": vendor["name"],
        "number": f"{'PO' if kind == 'purchase_order' else 'INV'}-{26000 + index}",
        "date": when.isoformat(), "due_date": (when + timedelta(days=30)).isoformat(),
        "currency": vendor["currency"], "po_number": f"PO-{8800 + index}", "subtotal": subtotal,
        "tax": tax, "total": round(subtotal + tax, 2), "line_items": rows,
        "source": "generated", "split": split, "layout": index % 4, "defects": [],
        "expected_po_total": round(subtotal + tax, 2), "known_vendor": True,
        "vendor_master": [v["name"] for v in VENDORS],
        "vendor_currencies": {v["name"]: v["currency"] for v in VENDORS},
        "po_reference": {"number": f"PO-{8800 + index}", "total": round(subtotal + tax, 2)},
        "as_of": "2026-09-26",
        "created_at": f"2026-09-26T{8 + index % 10:02d}:{index % 60:02d}:00Z",
    }
    defect = index % 12
    if defect == 3:
        doc["total"] += 37.0
        doc["defects"] = ["arithmetic"]
    elif defect == 5:
        doc["vendor"], doc["known_vendor"] = "Unlisted Workshop", False
        doc["defects"] = ["vendor"]
    elif defect == 7:
        doc["po_number"] = "PO-UNKNOWN"
        doc["defects"] = ["purchase_order"]
    elif defect == 9:
        prior = make_document(index - 1, split, seed)
        for key in ("vendor", "number", "date", "due_date", "currency", "po_number", "subtotal", "tax", "total",
                    "line_items", "po_reference", "type", "expected_po_total"):
            doc[key] = prior[key]
        doc["duplicate_of"] = prior["id"]
        doc["defects"] = ["duplicate"]
    elif defect == 11:
        doc["due_date"] = (when - timedelta(days=7)).isoformat()
        doc["defects"] = ["dates"]
    return doc


def render_document(doc: dict[str, Any], output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    pdf_path = output / f"{doc['id']}.pdf"
    canvas = Canvas(str(pdf_path), pagesize=(WIDTH, HEIGHT), invariant=1)
    tokens: list[dict[str, Any]] = []
    layout = doc["layout"]
    font = ("Helvetica", "Times-Roman", "Courier", "Helvetica")[layout]
    accent = ("#245C63", "#344C70", "#795B42", "#4E5D3B")[layout]

    def text(value: Any, x: float, y: float, size: int = 10, label: str = "O", face: str | None = None) -> None:
        text_value = str(value)
        face = face or font
        canvas.setFont(face, size)
        canvas.setFillColor(HexColor("#24313A"))
        canvas.drawString(x, HEIGHT - y, text_value)
        current_x = x
        for word in text_value.split():
            width = stringWidth(word, face, size)
            tokens.append({"text": word, "box": [current_x / WIDTH, (y - size) / HEIGHT, width / WIDTH,
                                                   (size + 3) / HEIGHT], "confidence": 1.0, "label": label})
            current_x += width + stringWidth(" ", face, size)

    canvas.setFillColor(HexColor(accent))
    if layout == 0:
        canvas.rect(0, HEIGHT - 14, WIDTH, 14, fill=1, stroke=0)
    elif layout == 1:
        canvas.rect(35, HEIGHT - 110, 5, 72, fill=1, stroke=0)
    elif layout == 2:
        canvas.rect(35, HEIGHT - 45, 542, 2, fill=1, stroke=0)
    else:
        canvas.setFillColor(HexColor("#EFF2EB"))
        canvas.rect(0, HEIGHT - 132, WIDTH, 132, fill=1, stroke=0)
    vendor_x = 50 if layout != 1 else 265
    text(doc["vendor"], vendor_x, 72, 21, "vendor", "Helvetica-Bold")
    text("FICTIONAL SUPPLIER / DEMONSTRATION", vendor_x, 92, 8)
    text("PURCHASE ORDER" if doc["type"] == "purchase_order" else "INVOICE", 50, 151, 24, face="Helvetica-Bold")
    text("Number", 50, 186, 9)
    text(doc["number"], 142, 186, 11, "number")
    text("Date", 50, 211, 9)
    text(doc["date"], 142, 211, 11, "date")
    text("Due date", 342, 186, 9)
    text(doc["due_date"], 423, 186, 11, "due_date")
    text("PO reference", 342, 211, 9)
    text(doc["po_number"], 423, 211, 11, "po_number")
    text("Currency", 50, 236, 9)
    text(doc["currency"], 142, 236, 11, "currency")
    text("BILL TO", 50, 275, 8)
    text("Docket Demonstration Company", 50, 295, 12)
    text("Accounts payable / Net 30", 50, 313, 9)
    canvas.setFillColor(HexColor("#E9EFF2" if layout != 2 else "#F3EEE8"))
    canvas.rect(45, HEIGHT - 356, 525, 28, fill=1, stroke=0)
    for label, x in (("Description", 53), ("Qty", 325), ("Unit price", 385), ("Amount", 485)):
        text(label, x, 347, 10)
    y = 381
    for row in doc["line_items"]:
        if layout in (0, 3):
            canvas.setStrokeColor(HexColor("#D9E0E4"))
            canvas.line(45, HEIGHT - y - 10, 570, HEIGHT - y - 10)
        text(row["description"], 53, y, 10, "description")
        text(row["quantity"], 330, y, 10, "quantity")
        text(f"{row['unit_price']:.2f}", 392, y, 10, "unit_price")
        text(f"{row['amount']:.2f}", 493, y, 10, "amount")
        y += 34
    y += 20
    for label in ("subtotal", "tax", "total"):
        text(label.title(), 385, y, 13 if label == "total" else 10)
        text(f"{doc[label]:.2f}", 493, y, 13 if label == "total" else 10, label)
        y += 27
    text("Thank you for keeping the work moving.", 50, 727, 11)
    text("Demonstration document. No real transaction or customer data.", 50, 750, 8)
    canvas.save()
    pdf = pdfium.PdfDocument(str(pdf_path))
    image = pdf[0].render(scale=1.7).to_pil().convert("RGB")
    image.save(output / f"{doc['id']}.png", optimize=True)
    pdf.close()
    doc["tokens"] = tokens
    doc["image"] = f"/data/images/{doc['id']}.png"
    doc["image_path"] = str((output / f"{doc['id']}.png").relative_to(ROOT)).replace("\\", "/")
    doc["pdf_path"] = str(pdf_path.relative_to(ROOT)).replace("\\", "/")
    return doc


def degrade(image: Image.Image, kind: str, level: float, seed: int = SEED) -> Image.Image:
    image = image.convert("RGB")
    if level == 0:
        return image.copy()
    if kind == "skew":
        return image.rotate(level, resample=Image.Resampling.BICUBIC, fillcolor="white")
    if kind == "blur":
        return image.filter(ImageFilter.GaussianBlur(level))
    if kind == "noise":
        arr = np.asarray(image).astype(float)
        noisy = arr + np.random.default_rng(seed).normal(0, level, arr.shape)
        return Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8))
    if kind == "jpeg":
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=int(level))
        buf.seek(0)
        return Image.open(buf).convert("RGB")
    if kind == "downscale":
        size = (max(1, int(image.width * level)), max(1, int(image.height * level)))
        return image.resize(size, Image.Resampling.BILINEAR).resize(image.size, Image.Resampling.NEAREST)
    if kind == "photograph":
        # Affine perspective approximation plus a reproducible left-to-right lighting gradient.
        transformed = image.transform(image.size, Image.Transform.PERSPECTIVE,
                                      (1, level * .12, 0, level * .05, 1, 0, level * .00015, 0),
                                      resample=Image.Resampling.BICUBIC, fillcolor="white")
        arr = np.asarray(transformed).astype(float)
        shade = np.linspace(1, max(.3, 1 - .4 * level), image.width)[None, :, None]
        return Image.fromarray(np.clip(arr * shade, 0, 255).astype(np.uint8))
    if kind == "threshold":
        return ImageEnhance.Contrast(image).enhance(level).convert("L").point(lambda p: 255 if p > 170 else 0).convert("RGB")
    raise ValueError(f"Unknown degradation: {kind}")


def generate(count: int = 96, output: Path | None = None) -> list[dict[str, Any]]:
    output = output or ROOT / "data/generated"
    docs = []
    for index in range(count):
        split = "train" if index < count // 2 else ("validation" if index < count * 3 // 4 else "test")
        docs.append(render_document(make_document(index, split), output))
    write_json(ROOT / "data/vendors/master.json", VENDORS)
    write_json(ROOT / "data/generated/annotations.json", docs)
    return docs
