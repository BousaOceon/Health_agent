"""Content routing, OCR, and Claude API extraction."""
import logging
import shutil
from datetime import date
from pathlib import Path

import pdfplumber
import pytesseract
from bs4 import BeautifulSoup
from docx import Document
from PIL import Image

from src.config import settings

log = logging.getLogger(__name__)

# Use tesseract from PATH (Linux/Pi). Fall back to the Windows install
# location only when it is not on PATH (local Windows dev before the Pi).
if shutil.which("tesseract") is None:
    _win_tesseract = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    if Path(_win_tesseract).exists():
        pytesseract.pytesseract.tesseract_cmd = _win_tesseract


# ---------------------------------------------------------------------------
# Content extractors
# ---------------------------------------------------------------------------

def extract_native_pdf(path: Path) -> str:
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return "\n".join(text_parts)


def extract_scanned_pdf(path: Path) -> str:
    from pdf2image import convert_from_path
    images = convert_from_path(str(path))
    return "\n".join(pytesseract.image_to_string(_preprocess(img)) for img in images)


def extract_image(path: Path) -> str:
    img = Image.open(path)
    return pytesseract.image_to_string(_preprocess(img))


def extract_docx(path: Path) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_email_body(html_or_text: str) -> str:
    soup = BeautifulSoup(html_or_text, "lxml")
    return soup.get_text(separator="\n").strip()


def _preprocess(img: Image.Image) -> Image.Image:
    return img.convert("L")


def prepare_content(source_type: str, path: Path = None, raw_text: str = None) -> str:
    """Route source to appropriate extractor, return labelled text block."""
    if source_type == "native_pdf":
        body = extract_native_pdf(path)
        return f"ATTACHMENT ({path.name}):\n{body}"
    elif source_type == "scanned_pdf":
        body = extract_scanned_pdf(path)
        return f"ATTACHMENT ({path.name}):\n{body}"
    elif source_type == "image":
        body = extract_image(path)
        return f"ATTACHMENT ({path.name}):\n{body}"
    elif source_type == "docx":
        body = extract_docx(path)
        return f"ATTACHMENT ({path.name}):\n{body}"
    elif source_type == "email_body":
        body = extract_email_body(raw_text)
        return f"EMAIL BODY:\n{body}"
    else:
        raise ValueError(f"Unknown source_type: {source_type}")


# ---------------------------------------------------------------------------
# Extraction
# Prompt lives in settings.yaml (extraction_prompt key). Injection uses
# ###PLACEHOLDER### substitution — never .format() or f-strings, because
# the prompt body contains JSON braces.
# ---------------------------------------------------------------------------

def extract_report(content: str, *, routing_list: str = "", provider_list_text: str = "",
                   active_strategy_titles: str = "", call=None) -> dict:
    """Send prepared content to Claude Sonnet for structured extraction (UNASSESSED shells).

    Injection (Phase 1d): the sub-target routing list (title + scope, NO benchmarks),
    the provider list, and active strategy titles. `call` is the claude seam (mockable).
    Returns the full extracted dict (appointment / findings / observations /
    strategy_observations / actions / self_review).
    """
    from src import claude

    today = date.today().isoformat()
    prompt = (settings["extraction_prompt"]
              .replace("###EXTRACTION_CONTEXT###", settings.get("extraction_context", ""))
              .replace("###PROVIDER_LIST###", provider_list_text or "(no providers on file)")
              .replace("###TODAY###", today)
              .replace("###SUBTARGET_ROUTING_LIST###", routing_list or "(no sub-targets)")
              .replace("###ACTIVE_STRATEGY_TITLES###", active_strategy_titles or "(no active strategies)")
              .replace("###REPORT_TEXT###", content))

    call = call or claude.call
    text = call(prompt, model=claude.SONNET, max_tokens=16000)
    return claude.parse_json(text)


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.extract <path_to_file>")
        sys.exit(1)
    p = Path(sys.argv[1])
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        content = prepare_content("native_pdf", path=p)
    elif suffix in (".jpg", ".jpeg", ".png"):
        content = prepare_content("image", path=p)
    elif suffix == ".docx":
        content = prepare_content("docx", path=p)
    else:
        content = prepare_content("email_body", raw_text=p.read_text(encoding="utf-8"))

    print("--- PREPARED CONTENT (first 500 chars) ---")
    print(content[:500])

    from src.db.store import connect
    from src.engine import injection
    conn = connect()
    print("\n--- EXTRACTION RESULT ---")
    result = extract_report(
        content,
        routing_list=injection.subtarget_routing_list(conn),
        provider_list_text=injection.provider_list(conn),
        active_strategy_titles=injection.active_strategy_titles(conn),
    )
    conn.close()
    print(json.dumps(result, indent=2))
