"""Content routing, OCR, and Claude API extraction."""
import email
import logging
import shutil
import tempfile
from datetime import date
from email import policy
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
# Native-vs-scanned PDF auto-detection (OCR density check, design §18)
# ---------------------------------------------------------------------------

def extract_pdf_auto(path: Path, *, min_chars_per_page: int = 50) -> tuple[str, str]:
    """Try native text; if density is too low (a scanned/image PDF), fall back to
    OCR. Returns (text, source) where source is 'native-pdf' or 'scanned-image'."""
    path = Path(path)
    text = extract_native_pdf(path)
    try:
        with pdfplumber.open(str(path)) as pdf:
            n_pages = len(pdf.pages)
    except Exception:
        n_pages = 1
    if n_pages and len(text.strip()) < min_chars_per_page * n_pages:
        try:
            ocr = extract_scanned_pdf(path)
            if len(ocr.strip()) > len(text.strip()):
                return ocr, "scanned-image"
        except Exception as e:
            log.warning("OCR fallback failed for %s: %s", path.name, e)
    return text, "native-pdf"


# ---------------------------------------------------------------------------
# .eml email files (one .eml = one encounter; quoted chain is in the body)
# ---------------------------------------------------------------------------

def _eml_text_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            cd = str(part.get("Content-Disposition") or "")
            if part.get_content_type() == "text/plain" and "attachment" not in cd:
                try:
                    return part.get_content()
                except Exception:
                    pass
        for part in msg.walk():
            cd = str(part.get("Content-Disposition") or "")
            if part.get_content_type() == "text/html" and "attachment" not in cd:
                try:
                    return extract_email_body(part.get_content())
                except Exception:
                    pass
        return ""
    try:
        return (extract_email_body(msg.get_content())
                if msg.get_content_type() == "text/html" else msg.get_content())
    except Exception:
        return ""


def _eml_attachments(msg) -> list[tuple]:
    """Extract text from PDF / docx / image attachments. Returns (name, text, source)."""
    out = []
    for part in msg.walk():
        cd = str(part.get("Content-Disposition") or "")
        filename = part.get_filename()
        if "attachment" not in cd and not filename:
            continue
        if part.get_content_type() in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        suffix = Path(filename).suffix.lower() if filename else ""
        text, source, tmp = None, None, None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
                tf.write(payload)
                tmp = Path(tf.name)
            if suffix == ".pdf":
                text, source = extract_pdf_auto(tmp)
            elif suffix == ".docx":
                text, source = extract_docx(tmp), "docx"
            elif suffix in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
                text, source = extract_image(tmp), "scanned-image"
        except Exception as e:
            log.warning("attachment extract failed (%s): %s", filename, e)
        finally:
            if tmp:
                tmp.unlink(missing_ok=True)
        if text and text.strip():
            out.append((filename or f"attachment{suffix}", text, source or "attachment"))
    return out


def extract_eml(path: Path) -> tuple[str, list[str]]:
    """Parse a .eml into labelled thread text + content_sources list."""
    path = Path(path)
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    header = (f"EMAIL\nFrom: {msg.get('From', '')}\nDate: {msg.get('Date', '')}\n"
              f"Subject: {msg.get('Subject', '')}\n\n{_eml_text_body(msg)}")
    parts, sources = [header], ["email-thread"]
    for name, text, source in _eml_attachments(msg):
        parts.append(f"\nATTACHMENT ({name}):\n{text}")
        sources.append(source)
    return "\n".join(parts), sources


SUPPORTED_SUFFIXES = {".pdf", ".docx", ".eml", ".jpg", ".jpeg", ".png",
                      ".tif", ".tiff", ".txt", ".html", ".htm"}


def prepare_file(path: Path) -> tuple[str, list[str]]:
    """Route a file to the right extractor. Returns (labelled content, content_sources)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        content, source = extract_pdf_auto(path)
        return f"ATTACHMENT ({path.name}):\n{content}", [source]
    if suffix in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
        return f"ATTACHMENT ({path.name}):\n{extract_image(path)}", ["scanned-image"]
    if suffix == ".docx":
        return f"ATTACHMENT ({path.name}):\n{extract_docx(path)}", ["docx"]
    if suffix == ".eml":
        return extract_eml(path)
    if suffix in (".txt", ".html", ".htm"):
        return (f"EMAIL BODY:\n{extract_email_body(path.read_text(encoding='utf-8', errors='ignore'))}",
                ["email-body"])
    raise ValueError(f"unsupported file type: {suffix}")


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
