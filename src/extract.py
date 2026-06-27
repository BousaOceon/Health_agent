"""Content routing, OCR, and Claude API extraction."""
import json
import logging
import shutil
from datetime import date
from pathlib import Path

import anthropic
import pdfplumber
import pytesseract
from bs4 import BeautifulSoup
from docx import Document
from PIL import Image

from src.config import ANTHROPIC_API_KEY, settings

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

def extract_report(content: str, goals_with_benchmarks: str = "", provider_list_text: str = "") -> dict:
    """Send prepared content to Claude Sonnet for structured extraction.

    Args:
        content: Prepared labelled text from prepare_content().
        goals_with_benchmarks: Formatted text from fetch_goals_with_benchmarks_text().
        provider_list_text: Formatted text from fetch_provider_list_text().

    Returns the full extracted dict including self_review.
    """
    today = date.today().isoformat()
    prompt_template = settings["extraction_prompt"]
    extraction_context = settings.get("extraction_context", "")

    if not goals_with_benchmarks:
        goals_with_benchmarks = "(No NDIS goals provided — leave goals_addressed and goal_link empty, return empty goal_progress_notes array)"
    if not provider_list_text:
        provider_list_text = "(No provider list available)"

    prompt = (prompt_template
              .replace("###EXTRACTION_CONTEXT###", extraction_context)
              .replace("###PROVIDER_LIST###", provider_list_text)
              .replace("###TODAY###", today)
              .replace("###GOALS_WITH_BENCHMARKS###", goals_with_benchmarks)
              .replace("###REPORT_TEXT###", content))

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


if __name__ == "__main__":
    import sys
    from src.notion_writer import fetch_ndis_goals, fetch_goals_with_benchmarks_text, fetch_provider_list_text

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

    goals_map = fetch_ndis_goals()
    print(f"\n--- NDIS GOALS ({len(goals_map)} loaded) ---")
    for name in goals_map:
        print(f"  {name}")

    goals_with_benchmarks = fetch_goals_with_benchmarks_text(goals_map)
    provider_list = fetch_provider_list_text()

    print("\n--- EXTRACTION RESULT ---")
    result = extract_report(content, goals_with_benchmarks, provider_list)
    print(json.dumps(result, indent=2))
