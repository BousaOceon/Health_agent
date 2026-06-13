"""
Manual end-to-end pipeline test.
Usage: python -m src.test_pipeline <path_to_report_file> [gmail_link]

Runs: extract content → fetch NDIS goals → Claude extraction → Notion write → move to processed/
"""
import sys
import json
import shutil
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

INBOX = Path(__file__).parent.parent / "inbox"
PROCESSED = Path(__file__).parent.parent / "processed"


def run(file_path: Path, gmail_link: str = ""):
    from src.extract import prepare_content, extract_report
    from src.notion_writer import (
        fetch_ndis_goals, fetch_goals_with_benchmarks_text, fetch_provider_list_text,
        appointment_exists, create_appointment, create_health_actions,
        create_goal_progress_notes, append_raw_notes_to_page,
    )

    # 1. Prepare content
    log.info("Extracting content from %s", file_path.name)
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        content = prepare_content("native_pdf", path=file_path)
    elif suffix in (".jpg", ".jpeg", ".png"):
        content = prepare_content("image", path=file_path)
    elif suffix == ".docx":
        content = prepare_content("docx", path=file_path)
    else:
        content = prepare_content("email_body", raw_text=file_path.read_text(encoding="utf-8"))

    print("\n--- PREPARED CONTENT (first 500 chars) ---")
    print(content[:500])

    # 2. Fetch NDIS goals, benchmarks, and provider list for extraction prompt
    goals_map = fetch_ndis_goals()
    log.info("Loaded %d NDIS goals: %s", len(goals_map), list(goals_map.keys()))
    goals_with_benchmarks = fetch_goals_with_benchmarks_text(goals_map)
    provider_list = fetch_provider_list_text()

    # 3. Claude extraction
    log.info("Sending to Claude for extraction...")
    extracted = extract_report(content, goals_with_benchmarks, provider_list)
    print("\n--- EXTRACTED DATA ---")
    print(json.dumps(extracted, indent=2))

    appt = extracted.get("appointment", {})
    log.info("Appointment date: %r | Provider: %r", appt.get("appointment_date"), appt.get("provider_name"))
    if not appt.get("appointment_date"):
        log.error("Extraction missing appointment_date. Aborting.")
        return
    if not appt.get("provider_name"):
        log.warning("provider_name is empty — will create appointment without provider relation.")

    # 4. Deduplication check
    if appointment_exists(appt["appointment_date"], gmail_link):
        log.warning("Appointment already exists in Notion – skipping write.")
        return

    # 5. Write to Notion
    log.info("Writing to Notion...")
    appt_id = create_appointment(extracted, goals_map, gmail_link=gmail_link)
    append_raw_notes_to_page(appt_id, content)
    action_ids = create_health_actions(extracted, appt_id, goals_map)
    note_ids = create_goal_progress_notes(extracted, appt_id, goals_map)
    log.info("Appointment: %s | Actions: %d | Notes: %d", appt_id, len(action_ids), len(note_ids))

    # 6. Move to processed
    dest = PROCESSED / file_path.name
    try:
        shutil.move(str(file_path), str(dest))
        log.info("Moved to processed/: %s", dest.name)
    except PermissionError:
        log.warning("Could not move file — it may be open in another program. Move manually: %s → processed/", file_path.name)

    print("\n--- DONE ---")
    print(f"Appointment: https://notion.so/{appt_id.replace('-', '')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = Path(sys.argv[1])
    link = sys.argv[2] if len(sys.argv) > 2 else ""
    if not path.exists():
        log.error("File not found: %s", path)
        sys.exit(1)
    run(path, link)
