"""Unit tests for Pass 2 reconciliation (pure logic; in-memory DB, no LLM).

Run: python -m src.engine.test_pass2
"""
import sqlite3
import sys

from src.db import writes
from src.db.schema import init_db
from src.db.store import now_iso
from src.engine import pass2


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    conn.execute("INSERT INTO goal_pages (id,title,category,status) VALUES ('g','G','NDIS','Active')")
    conn.commit()
    return conn


def add_subtarget(conn, sid, *, benchmark="baseline", as_of="2026-01-01"):
    conn.execute(
        "INSERT INTO sub_targets (id,title,goal_id,ndis,status,current_benchmark,benchmark_as_of,created_at) "
        "VALUES (?,?,?,1,'Active',?,?,?)",
        (sid, sid, "g", benchmark, as_of, now_iso()),
    )
    conn.commit()


def add_obs(conn, sid, grades_dates, *, confirmed=True, invalidated=False):
    """grades_dates: list of (assessment, date). One appointment for the batch."""
    appt = writes.new_appointment(conn, appointment_date="2026-06-01", status="draft")
    if confirmed:
        writes.confirm_appointment(conn, appt)
    for grade, d in grades_dates:
        fid = writes.new_finding(conn, source_encounter_id=appt, source_fragment="f")
        oid = writes.new_observation_shell(conn, finding_id=fid, sub_target_id=sid,
                                           source_encounter_id=appt, date=d, note=f"{grade}@{d}")
        writes.set_assessment(conn, oid, assessment=grade, confidence="high")
        if invalidated:
            conn.execute("UPDATE observations SET status='invalidated' WHERE id=?", (oid,))
    conn.commit()
    return appt


RESULTS = []


def check(name, cond):
    RESULTS.append((name, bool(cond)))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    # 1. Progression: 2x Above after as_of -> 1 candidate
    conn = fresh(); add_subtarget(conn, "st1")
    add_obs(conn, "st1", [("Above", "2026-03-01"), ("Above", "2026-04-01")])
    c = pass2.reconcile(conn, "st1")
    check("progression: 2x Above -> 1 candidate", len(c) == 1)
    row = conn.execute("SELECT change_class, triggering_rule FROM candidates WHERE id=?", (c[0],)).fetchone()
    check("progression: candidate is benchmark-change", row["change_class"] == "benchmark-change")

    # 2. Single Above is a fluke -> no candidate
    conn = fresh(); add_subtarget(conn, "st2")
    add_obs(conn, "st2", [("Above", "2026-03-01")])
    check("single Above -> no candidate", pass2.reconcile(conn, "st2") == [])

    # 3. Gate-tightness: draft + invalidated Above don't count
    conn = fresh(); add_subtarget(conn, "st3")
    add_obs(conn, "st3", [("Above", "2026-03-01")], confirmed=True)
    add_obs(conn, "st3", [("Above", "2026-04-01")], confirmed=False)            # draft
    add_obs(conn, "st3", [("Above", "2026-05-01")], confirmed=True, invalidated=True)
    check("gate-tight: only 1 confirmed-active Above -> no progression",
          pass2.reconcile(conn, "st3") == [])

    # 4. Idempotency: re-running with a pending candidate raises nothing
    conn = fresh(); add_subtarget(conn, "st4")
    add_obs(conn, "st4", [("Above", "2026-03-01"), ("Above", "2026-04-01")])
    first = pass2.reconcile(conn, "st4")
    second = pass2.reconcile(conn, "st4")
    check("idempotent: 1st raises, 2nd raises nothing", len(first) == 1 and second == [])

    # 5. Idempotency via benchmark advance: approving (advance as_of) stops re-proposal
    conn = fresh(); add_subtarget(conn, "st5", as_of="2026-01-01")
    add_obs(conn, "st5", [("Above", "2026-03-01"), ("Above", "2026-04-01")])
    pass2.reconcile(conn, "st5")
    # simulate approval: advance benchmark_as_of past the triggering obs + close the candidate
    conn.execute("UPDATE sub_targets SET benchmark_as_of='2026-04-01' WHERE id='st5'")
    conn.execute("UPDATE candidates SET status='approved' WHERE target_subtarget_id='st5'")
    conn.commit()
    check("post-approval: advanced benchmark -> nothing re-proposed", pass2.reconcile(conn, "st5") == [])

    # 6. Regression: 2x Lower -> candidate
    conn = fresh(); add_subtarget(conn, "st6")
    add_obs(conn, "st6", [("Lower", "2026-03-01"), ("Lower", "2026-04-01")])
    c = pass2.reconcile(conn, "st6")
    check("regression: 2x Lower -> 1 candidate", len(c) == 1)

    # 7. Addition: 2x Gap -> candidate
    conn = fresh(); add_subtarget(conn, "st7")
    add_obs(conn, "st7", [("Gap", "2026-03-01"), ("Gap", "2026-04-01")])
    check("addition: 2x Gap -> 1 candidate", len(pass2.reconcile(conn, "st7")) == 1)

    # 8. At-benchmark observations are inert
    conn = fresh(); add_subtarget(conn, "st8")
    add_obs(conn, "st8", [("At", "2026-03-01"), ("At", "2026-04-01"), ("At", "2026-05-01")])
    check("3x At -> no candidate (inert denominator)", pass2.reconcile(conn, "st8") == [])

    # 9. Un-benchmarked Active row -> skipped
    conn = fresh()
    conn.execute("INSERT INTO sub_targets (id,title,goal_id,ndis,status,created_at) "
                 "VALUES ('st9','st9','g',0,'Active',?)", (now_iso(),))
    conn.commit()
    add_obs(conn, "st9", [("Above", "2026-03-01"), ("Above", "2026-04-01")])
    pic = pass2.aggregate(conn, "st9")
    check("un-benchmarked: skipped, no candidate",
          pic["skipped"] == "un-benchmarked" and pass2.reconcile(conn, "st9") == [])

    # 10. Observations on/before as_of are already reflected -> not re-proposed
    conn = fresh(); add_subtarget(conn, "st10", as_of="2026-06-01")
    add_obs(conn, "st10", [("Above", "2026-03-01"), ("Above", "2026-04-01")])  # both before as_of
    check("pre-as_of Above already reflected -> no candidate", pass2.reconcile(conn, "st10") == [])

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} passed.")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
