"""End-to-end entry-flow test: ingest -> draft -> confirm -> Pass 1 -> Pass 2 ->
candidate -> apply. All three Claude call types are stubbed.

Run: python -m src.engine.test_entry_flow
"""
import json
import re
import sqlite3
import sys

from src.db import writes
from src.db.schema import init_db
from src.db.store import now_iso
from src.engine import apply, pass2
from src.engine.benchmark import seed_baseline
from src.pipeline import confirm_report, ingest_content

EXTRACTION = {
    "appointment": {
        "title": "Madelaine Tomlin - 2026-06-01", "provider_name": "Madelaine Tomlin",
        "providers": ["Madelaine Tomlin"], "appointment_date": "2026-06-01",
        "report_received_date": "2026-06-27", "meeting_type": "Individual",
        "appointment_type": "Appointment", "summary": "OT session on dressing and climbing.",
        "content_sources": ["native-pdf"], "sub_targets_touched": ["st_dressing", "st_climbing"]},
    "findings": [{"ref": "F1", "source_fragment": "climbed the ramp beside a peer and put his shirt on",
                  "title": "ramp + shirt", "fan_out_rationale": "two direct subjects", "fan_out_confidence": "high"}],
    "observations": [
        {"finding_ref": "F1", "sub_target_id": "st_dressing", "author": "Provider",
         "source": "Appointment Report", "source_provider_name": "Madelaine Tomlin",
         "date": "2026-06-01", "note": "put his shirt on unprompted", "milestone": False},
        {"finding_ref": "F1", "sub_target_id": "st_climbing", "author": "Provider",
         "source": "Appointment Report", "source_provider_name": "Maddy",
         "date": "2026-06-01", "note": "climbed the ramp beside a peer", "milestone": False}],
    "strategy_observations": [
        {"finding_ref": None, "sub_target_id": "st_dressing", "author": "Provider",
         "source_provider_name": "Madelaine Tomlin", "date": "2026-06-01",
         "note": "keep using the visual dressing sequence", "status_language": "continuing"}],
    "actions": [
        {"title": "Buy a visual dressing sequence card", "provider_name": "Madelaine Tomlin",
         "assigned_to": "Family", "category": "OT", "priority": "Medium", "due_date": None,
         "sub_target_id": "st_dressing", "notes": ""}],
    "self_review": {"corrections_made": [], "flags_for_review": [], "extraction_confidence": "high",
                    "corrections_count": 0, "flags_count": 0},
}


def stub(prompt, *, model, max_tokens=8000, system=None):
    if prompt.startswith("You are extracting structured health data"):
        return json.dumps(EXTRACTION)
    if prompt.startswith("You are grading already-extracted observations"):
        refs = re.findall(r"ref=(\S+)", prompt)
        return json.dumps([{"ref": r, "assessment": "Above",
                            "rationale": "unprompted vs benchmark", "confidence": "high"} for r in refs])
    if prompt.startswith("You are updating the current benchmark"):
        return "Now completes upper-body dressing unprompted across settings."
    raise RuntimeError("unexpected prompt to stub")


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    conn.execute("INSERT INTO goal_pages (id,title,category,scope,status) "
                 "VALUES ('g','Self-Care','NDIS','daily living','Active')")
    for sid, title, bench in [("st_dressing", "Dressing", "needs help with upper body"),
                              ("st_climbing", "Climbing", "climbs with a hand held")]:
        conn.execute(
            "INSERT INTO sub_targets (id,title,goal_id,scope_line,current_benchmark,benchmark_as_of,ndis,status,created_at) "
            "VALUES (?,?,?,?,?,?,1,'Active',?)",
            (sid, title, "g", title.lower(), bench, "2026-01-01", now_iso()))
    conn.execute("INSERT INTO providers (id,title,aliases,type) "
                 "VALUES ('p','Madelaine Tomlin','Maddy, M. Tomlin','OT')")
    conn.commit()
    seed_baseline(conn, sub_target_id="st_dressing", benchmark_text="needs help with upper body",
                  effective_date="2026-01-01", advance=True)
    seed_baseline(conn, sub_target_id="st_climbing", benchmark_text="climbs with a hand held",
                  effective_date="2026-01-01", advance=True)
    return conn


def seed_prior_above(conn, sub_target_id, date_):
    """A prior confirmed 'Above' so a second one tips Pass 2 into a progression."""
    appt = writes.new_appointment(conn, appointment_date=date_, status="draft")
    writes.confirm_appointment(conn, appt)
    f = writes.new_finding(conn, source_encounter_id=appt, source_fragment="earlier win")
    o = writes.new_observation_shell(conn, finding_id=f, sub_target_id=sub_target_id,
                                     source_encounter_id=appt, date=date_, note="did it unprompted (earlier)")
    from src.engine.benchmark import governing_benchmark_version
    gv = governing_benchmark_version(conn, sub_target_id, date_)
    writes.set_assessment(conn, o, assessment="Above", confidence="high",
                          graded_against_benchmark_id=gv["id"] if gv else None)
    conn.commit()


RESULTS = []
def check(name, cond):
    RESULTS.append(bool(cond)); print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    conn = fresh()
    seed_prior_above(conn, "st_dressing", "2026-03-01")

    # --- ingest -> draft ---
    appt_id, extracted = ingest_content(conn, "raw OT report text", call=stub)
    a = conn.execute("SELECT status, summary FROM appointments WHERE id=?", (appt_id,)).fetchone()
    n_obs = conn.execute("SELECT COUNT(*) FROM observations WHERE source_encounter_id=? AND assessment IS NULL", (appt_id,)).fetchone()[0]
    n_act = conn.execute("SELECT status FROM health_actions WHERE source_appointment_id=?", (appt_id,)).fetchone()
    n_strat = conn.execute("SELECT COUNT(*) FROM strategy_observations WHERE source_encounter_id=?", (appt_id,)).fetchone()[0]
    provs = conn.execute("SELECT COUNT(*) FROM appointment_providers WHERE appointment_id=?", (appt_id,)).fetchone()[0]
    flags = conn.execute("SELECT flags FROM appointments WHERE id=?", (appt_id,)).fetchone()["flags"]
    check("ingest: appointment is draft", a["status"] == "draft")
    check("ingest: 2 unassessed observation shells", n_obs == 2)
    check("ingest: action persisted Open", n_act["status"] == "Open")
    check("ingest: strategy observation persisted", n_strat == 1)
    check("ingest: provider linked (incl. 'Maddy' alias resolved)", provs == 1)
    check("ingest: self_review written to flags", bool(flags))

    # --- confirm -> Pass 1 -> Pass 2 ---
    result = confirm_report(conn, appt_id, call=stub)
    a = conn.execute("SELECT status FROM appointments WHERE id=?", (appt_id,)).fetchone()
    graded = conn.execute("SELECT COUNT(*) FROM observations WHERE source_encounter_id=? AND assessment='Above'", (appt_id,)).fetchone()[0]
    check("confirm: appointment confirmed", a["status"] == "confirmed")
    check("confirm: both new obs graded Above", graded == 2)
    check("confirm: touched both sub-targets", set(result["touched"]) == {"st_dressing", "st_climbing"})

    # st_dressing now has 2 Above (prior + new) -> 1 progression candidate with proposed text;
    # st_climbing has 1 Above -> none.
    check("Pass 2: exactly one candidate raised", len(result["candidates"]) == 1)
    cid = result["candidates"][0]
    cand = conn.execute("SELECT change_class, change_type, target_subtarget_id, to_value FROM candidates WHERE id=?", (cid,)).fetchone()
    check("Pass 2: candidate is a Progression on st_dressing", cand["change_type"] == "Progression" and cand["target_subtarget_id"] == "st_dressing")
    check("Pass 2: summarizer filled the proposed benchmark text", "unprompted" in (cand["to_value"] or ""))

    # --- apply the candidate -> benchmark advances ---
    apply.apply_candidate(conn, cid)
    st = conn.execute("SELECT current_benchmark, benchmark_as_of FROM sub_targets WHERE id='st_dressing'").fetchone()
    check("apply: benchmark advanced to the proposed text", "unprompted" in st["current_benchmark"])
    check("apply: idempotent after advance", pass2.reconcile(conn, "st_dressing", lambda *a: (None, "x")) == [])

    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} passed.")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
