"""Tests for the data-load driver + the new content handlers (.eml, file routing,
dedup/resumability, oldest-first confirm). Stubbed Claude; real file I/O in a temp dir.

Run: python -m src.engine.test_dataload
"""
import json
import re
import sqlite3
import sys
import tempfile
from email.message import EmailMessage
from pathlib import Path

from src import dataload
from src.db.schema import init_db
from src.db.store import now_iso
from src.engine.benchmark import seed_baseline
from src.extract import extract_eml, prepare_file


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    conn.execute("INSERT INTO goal_pages (id,title,category,status) VALUES ('g','G','NDIS','Active')")
    conn.execute("INSERT INTO sub_targets (id,title,goal_id,scope_line,current_benchmark,benchmark_as_of,ndis,status,created_at) "
                 "VALUES ('st1','Dressing','g','dressing','needs help','2025-01-01',1,'Active',?)", (now_iso(),))
    # the Unclassified pen must exist for the capture-broadly fallback
    conn.execute("INSERT INTO sub_targets (id,title,goal_id,ndis,status,created_at) "
                 "VALUES ('st_pen_unclassified','Other/Unclassified','g',0,'Active',?)", (now_iso(),))
    conn.commit()
    seed_baseline(conn, sub_target_id="st1", benchmark_text="needs help",
                  effective_date="2025-01-01", advance=True)
    return conn


def stub(prompt, *, model, max_tokens=8000, system=None):
    if prompt.startswith("You are extracting structured health data"):
        m = re.search(r"APPT_DATE=(\d{4}-\d{2}-\d{2})", prompt)
        d = m.group(1) if m else None
        ext = {
            "appointment": {"title": f"OT - {d}", "provider_name": "", "providers": [],
                            "appointment_date": d, "report_received_date": "2026-06-27",
                            "meeting_type": "Individual", "appointment_type": "Appointment",
                            "summary": "OT session.", "content_sources": [], "sub_targets_touched": ["st1"]},
            "findings": [{"ref": "F1", "source_fragment": "dressed", "title": "dress",
                          "fan_out_rationale": "", "fan_out_confidence": "high"}],
            "observations": [{"finding_ref": "F1", "sub_target_id": "st1", "author": "Provider",
                              "source": "Appointment Report", "date": d, "note": "dressed with help",
                              "milestone": False}],
            "strategy_observations": [], "actions": [],
            "self_review": {"corrections_made": [], "flags_for_review": [],
                            "extraction_confidence": "high", "corrections_count": 0, "flags_count": 0}}
        return json.dumps(ext)
    if prompt.startswith("You are grading already-extracted observations"):
        refs = re.findall(r"ref=(\S+)", prompt)
        return json.dumps([{"ref": r, "assessment": "At", "rationale": "at benchmark", "confidence": "high"} for r in refs])
    if prompt.startswith("You are updating the current benchmark"):
        return "updated benchmark"
    raise RuntimeError("unexpected prompt")


RESULTS = []
def check(name, cond):
    RESULTS.append(bool(cond)); print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    # --- .eml parsing ---
    with tempfile.TemporaryDirectory() as td:
        eml = Path(td) / "chain.eml"
        m = EmailMessage()
        m["From"] = "clinic@example.com"; m["To"] = "matt@example.com"
        m["Subject"] = "OT report"; m["Date"] = "Fri, 01 Aug 2025 10:00:00 +1000"
        m.set_content("Tom dressed well today. APPT_DATE=2025-08-01.")
        eml.write_bytes(m.as_bytes())
        text, sources = extract_eml(eml)
        check(".eml: header + body extracted", "clinic@example.com" in text and "Tom dressed well" in text)
        check(".eml: source is email-thread", sources == ["email-thread"])

        txt = Path(td) / "note.txt"
        txt.write_text("Plain note. APPT_DATE=2025-07-01.")
        content, src = prepare_file(txt)
        check("prepare_file: .txt -> email-body", src == ["email-body"] and "Plain note" in content)
        check("prepare_file: unsupported type rejected",
              _raises(lambda: prepare_file(Path(td) / "x.zip")))

    # --- data-load: extract folder, dedup, oldest-first confirm ---
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "a.txt").write_text("Report A. APPT_DATE=2025-09-01.")
        (Path(td) / "b.txt").write_text("Report B. APPT_DATE=2025-08-01.")  # earlier
        conn = fresh()

        r1 = dataload.extract_folder(conn, td, call=stub)
        check("extract_folder: 2 ingested as drafts", len(r1["ingested"]) == 2 and not r1["errors"])
        drafts = conn.execute("SELECT COUNT(*) FROM appointments WHERE backfill=1 AND status='draft'").fetchone()[0]
        check("extract_folder: drafts carry source_ref", drafts == 2)
        check("extract_folder: no dates-to-confirm (dates found)", dataload.dates_to_confirm(conn) == [])

        # resumable / dedup: re-run skips both
        r2 = dataload.extract_folder(conn, td, call=stub)
        check("extract_folder: re-run skips already-ingested", len(r2["skipped"]) == 2 and not r2["ingested"])

        # confirm oldest-first
        order = dataload.confirm_oldest_first(conn, call=stub)
        check("confirm_oldest_first: dates ascending", [o["date"] for o in order] == ["2025-08-01", "2025-09-01"])
        confirmed = conn.execute("SELECT COUNT(*) FROM appointments WHERE backfill=1 AND status='confirmed'").fetchone()[0]
        check("confirm_oldest_first: both confirmed", confirmed == 2)
        graded = conn.execute("SELECT COUNT(*) FROM observations WHERE assessment='At'").fetchone()[0]
        check("confirm_oldest_first: observations graded", graded == 2)

    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} passed.")
    return 0 if passed == len(RESULTS) else 1


def _raises(fn):
    try:
        fn(); return False
    except Exception:
        return True


if __name__ == "__main__":
    sys.exit(main())
