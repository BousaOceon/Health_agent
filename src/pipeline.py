"""The entry-flow pipeline (Phase 1d): ingest -> draft, confirm -> Pass 1 -> Pass 2.

ingest_content : extract (Sonnet) -> persist UNASSESSED shells as a draft.
confirm_report : flip to confirmed -> Pass 1 grades (Haiku) -> Pass 2 reconciles
                 the touched sub-targets -> benchmark-change candidates appear on
                 the dashboard for review. Nothing auto-applies.

`call` is the claude seam (mockable). Approving a candidate is a separate step
(src.engine.apply.apply_candidate), surfaced through the dashboard.
"""
from src.db import writes
from src.engine import injection, pass1, pass2, persist
from src.engine import summarize as summ
from src.extract import extract_report


def ingest_content(conn, content: str, *, backfill=0, gmail_link=None,
                   source_email=None, call=None) -> tuple[str, dict]:
    """Extract `content` and persist it as a draft. Returns (appointment_id, extracted)."""
    extracted = extract_report(
        content,
        routing_list=injection.subtarget_routing_list(conn),
        provider_list_text=injection.provider_list(conn),
        active_strategy_titles=injection.active_strategy_titles(conn),
        call=call)
    appointment_id = persist.persist_extraction(
        conn, extracted, backfill=backfill, gmail_link=gmail_link, source_email=source_email)
    return appointment_id, extracted


def confirm_report(conn, appointment_id: str, *, call=None, summarize=None, backfill=0) -> dict:
    """Confirm a draft: Pass 1 grades the shells, Pass 2 reconciles touched sub-targets."""
    writes.confirm_appointment(conn, appointment_id)
    conn.commit()

    grades = pass1.grade_appointment(conn, appointment_id, call=call)
    if summarize is None:
        summarize = summ.make_summarizer(conn, call=call)

    touched = [r["sub_target_id"] for r in conn.execute(
        "SELECT DISTINCT sub_target_id FROM observations "
        "WHERE source_encounter_id=? AND status='active'", (appointment_id,)).fetchall()]
    candidates = []
    for sid in touched:
        candidates += pass2.reconcile(conn, sid, summarize, backfill=backfill, commit=False)
    conn.commit()
    return {"grades": grades, "candidates": candidates, "touched": touched}
