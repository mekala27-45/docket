"""Real OCR and gold-word adapters; preprocessing never reads labels."""
import io
import os
import time
from typing import Any

from PIL import Image, ImageOps
import pytesseract


def preprocess(image: Image.Image, binarize: bool = False) -> Image.Image:
    converted = ImageOps.exif_transpose(image).convert("RGB")
    if converted.width < 900:
        factor = 900 / converted.width
        converted = converted.resize((900, int(converted.height * factor)), Image.Resampling.LANCZOS)
    if binarize:
        converted = converted.convert("L").point(lambda p: 255 if p >= 170 else 0).convert("RGB")
    return converted


def recognize(image: Image.Image, *, binarize: bool = False) -> dict[str, Any]:
    command = os.getenv("TESSERACT_CMD")
    if command:
        pytesseract.pytesseract.tesseract_cmd = command
    processed = preprocess(image, binarize)
    start = time.perf_counter()
    data = pytesseract.image_to_data(processed, config="--psm 6", output_type=pytesseract.Output.DICT,
                                     timeout=40)
    tokens = []
    for index, word in enumerate(data["text"]):
        if not word.strip():
            continue
        tokens.append({"text": word.strip(), "box": [data["left"][index] / processed.width,
                       data["top"][index] / processed.height, data["width"][index] / processed.width,
                       data["height"][index] / processed.height],
                       "confidence": max(0, min(1, float(data["conf"][index]) / 100)),
                       "line": f"{data['block_num'][index]}:{data['par_num'][index]}:{data['line_num'][index]}"})
    return {"tokens": tokens, "engine": "tesseract", "version": str(pytesseract.get_tesseract_version()),
            "elapsed_ms": (time.perf_counter() - start) * 1000,
            "preprocessing": "EXIF orientation; RGB; upscale width below 900px; "
                             + ("threshold 170; " if binarize else "no threshold; ") + "PSM 6; eng"}


def gold_words(document: dict[str, Any]) -> dict[str, Any]:
    # Labels are explicitly stripped; extraction is never allowed the benchmark answer.
    return {"engine": "gold", "version": "annotations", "elapsed_ms": 0,
            "preprocessing": "none; semantic labels stripped",
            "tokens": [{"text": t["text"], "box": t["box"], "confidence": 1.0}
                       for t in document.get("tokens", [])]}


def image_from_bytes(data: bytes, filename: str) -> Image.Image:
    if filename.lower().endswith(".pdf") or data.startswith(b"%PDF"):
        import pypdfium2 as pdfium
        document = pdfium.PdfDocument(data)
        if len(document) != 1:
            raise ValueError("This demonstration accepts single-page PDFs only")
        rendered: Image.Image = document[0].render(scale=1.7).to_pil().convert("RGB")
        document.close()
        return rendered
    image = Image.open(io.BytesIO(data))
    if image.width * image.height > 25_000_000:
        raise ValueError("Image exceeds 25 megapixels")
    return ImageOps.exif_transpose(image).convert("RGB")
