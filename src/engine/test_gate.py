"""Tests for the gate: apply_candidate, the benchmark log, and the cascade.

Deterministic — an injected assess() stub stands in for the Pass-1 Haiku call.
Run: python -m src.engine.test_gate
"""
import sqlite3
import sys

from src.db import writes
from src.db.schema import init_db
from src.db.store import now_iso
from src.engine import apply, pass2
from src.engine.benchmark import governing_benchmark_version, seed_baseline, write_benchmark_change


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    conn.execute("INSERT INTO goal_pages (id,title,category,status) VALUES ('g','G','NDIS','Active')")
    conn.execute("INSERT INTO goal_pages (id,title,category,status) VALUES ('g2','G2','Other','Active')")
    conn.commit()
    return conn


def add_subtarget(conn, sid, *, benchmark="B0", as_of="2026-01-01", status="Active"):
    conn.execute(
        "INSERT INTO sub_targets (id,title,goal_id,ndis,status,current_benchmark,benchmark_as_of,created_at) "
        "VALUES (?,?,?,1,?,?,?,?)",
        (sid, sid, "g", status, benchmark if benchmark else None, as_of, now_iso()),
    )
    conn.commit()


def add_obs(conn, sid, grades_dates, *, graded_against=None):
    appt = writes.new_appointment(conn, appointment_date="2026-06-01", status="draft")
    writes.confirm_appointment(conn, appt)
    ids = []
    for grade, d in grades_dates:
        fid = writes.new_finding(conn, source_encounter_id=appt, source_fragment="f")
        oid = writes.new_observation_shell(conn, finding_id=fid, sub_target_id=sid,
                                           source_encounter_id=appt, date=d, note=f"{grade}@{d}")
        writes.set_assessment(conn, oid, assessment=grade, confidence="high",
                              graded_against_benchmark_id=graded_against)
        ids.append(oid)
    conn.commit()
    return ids


class Assessor:
    """Stub Pass-1: grades Above if benchmark text mentions 'corrected', else At. Counts calls."""
    def __init__(self):
        self.calls = 0
    def __call__(self, obs_row, benchmark_text):
        self.calls += 1
        return "Above" if benchmark_text and "corrected" in benchmark_text else "At"


RESULTS = []
def check(name, cond):
    RESULTS.append(bool(cond))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    # 1. governing_benchmark_version picks the right entry by date
    conn = fresh(); add_subtarget(conn, "s1")
    seed_baseline(conn, sub_target_id="s1", benchmark_text="B0", effective_date="2025-06-01")
    write_benchmark_change(conn, sub_target_id="s1", change_type="Progression",
                           to_value="B1", effective_date="2026-03-01"); conn.commit()
    g_old = governing_benchmark_version(conn, "s1", "2025-12-01")
    g_new = governing_benchmark_version(conn, "s1", "2026-04-01")
    check("governing version: old date -> Baseline", g_old["to_value"] == "B0")
    check("governing version: new date -> Progression", g_new["to_value"] == "B1")

    # 2. forward benchmark-change apply: writes log, advances benchmark, idempotent after
    conn = fresh(); add_subtarget(conn, "s2", as_of="2026-01-01")
    add_obs(conn, "s2", [("Above", "2026-03-01"), ("Above", "2026-04-01")])
    cid = pass2.reconcile(conn, "s2")[0]
    conn.execute("UPDATE candidates SET to_value='B1-new' WHERE id=?", (cid,)); conn.commit()
    res = apply.apply_candidate(conn, cid)
    st = conn.execute("SELECT current_benchmark, benchmark_as_of FROM sub_targets WHERE id='s2'").fetchone()
    log = conn.execute("SELECT change_type, to_value FROM benchmark_change_log WHERE id=?", (res["log_id"],)).fetchone()
    cand = conn.execute("SELECT status, resulting_log_id FROM candidates WHERE id=?", (cid,)).fetchone()
    check("apply: benchmark advanced to B1-new @ 2026-04-01",
          st["current_benchmark"] == "B1-new" and st["benchmark_as_of"] == "2026-04-01")
    check("apply: Progression log entry written", log["change_type"] == "Progression")
    check("apply: candidate approved + log linked",
          cand["status"] == "approved" and cand["resulting_log_id"] == res["log_id"])
    check("apply: idempotent after advance (no new candidate)", pass2.reconcile(conn, "s2") == [])

    # 3. benchmark-correction cascades: re-grades downstream obs via assess(), audits, re-proposes
    conn = fresh(); add_subtarget(conn, "s3", benchmark="B0", as_of="2026-01-01")
    L0 = seed_baseline(conn, sub_target_id="s3", benchmark_text="B0", effective_date="2026-01-01", advance=True)
    o = add_obs(conn, "s3", [("At", "2026-03-01"), ("At", "2026-04-01")], graded_against=L0)
    corr = writes.new_candidate(conn, change_class="benchmark-correction", change_type="Correction",
                                origin="manual", target_subtarget_id="s3",
                                from_value="B0", to_value="B0-corrected (was wrong)",
                                reason="benchmark was wrong", source_observation_ids=o)
    conn.commit()
    # apply correction: effective date = the corrected version's date (2026-01-01),
    # so the Correction entry governs both obs and re-grades them.
    asr = Assessor()
    res = apply.apply_candidate(conn, corr, assess=asr)
    regraded = res["cascade"]["regraded"]
    audits = conn.execute("SELECT COUNT(*) FROM recompute_audit").fetchone()[0]
    sup = conn.execute("SELECT COUNT(*) FROM observations WHERE sub_target_id='s3' AND assessment_superseded=1").fetchone()[0]
    check("correction: both obs re-graded At->Above", len(regraded) == 2 and asr.calls == 2)
    check("correction: recompute_audit has 2 rows", audits == 2)
    check("correction: superseded flag set on 2 obs", sup == 2)
    check("correction: cascade re-proposed a progression", len(res["cascade"]["new_candidates"]) == 1)

    # 4. version-gated idempotency: re-running the cascade makes ZERO assess() calls
    from src.engine import cascade as cascade_mod
    before = asr.calls
    cascade_mod.cascade(conn, "s3", "correction", asr)
    check("version-gated: re-run cascade -> no assess() calls", asr.calls == before)

    # 5. assessment-correction: in-place grade fix, no log entry, cascades
    conn = fresh(); add_subtarget(conn, "s5", benchmark="B0", as_of="2026-01-01")
    L = seed_baseline(conn, sub_target_id="s5", benchmark_text="B0", effective_date="2026-01-01", advance=True)
    o = add_obs(conn, "s5", [("At", "2026-03-01")], graded_against=L)
    ac = writes.new_candidate(conn, change_class="assessment-correction", origin="manual",
                              target_subtarget_id="s5", target_observation_id=o[0],
                              to_value="Above", reason="should be Above")
    conn.commit()
    logs_before = conn.execute("SELECT COUNT(*) FROM benchmark_change_log").fetchone()[0]
    apply.apply_candidate(conn, ac, assess=Assessor())
    grade = conn.execute("SELECT assessment, assessment_superseded FROM observations WHERE id=?", (o[0],)).fetchone()
    logs_after = conn.execute("SELECT COUNT(*) FROM benchmark_change_log").fetchone()[0]
    check("assessment-correction: in-place grade -> Above + superseded",
          grade["assessment"] == "Above" and grade["assessment_superseded"] == 1)
    check("assessment-correction: writes NO change-log entry", logs_after == logs_before)

    # 6. spin-out re-points the goal and denormalised obs goal
    conn = fresh(); add_subtarget(conn, "s6")
    o = add_obs(conn, "s6", [("At", "2026-03-01")])
    conn.execute("UPDATE observations SET goal_id='g' WHERE sub_target_id='s6'"); conn.commit()
    so = writes.new_candidate(conn, change_class="spin-out", origin="manual",
                              target_subtarget_id="s6", to_value="g2", reason="spin out to g2")
    conn.commit()
    apply.apply_candidate(conn, so)
    st = conn.execute("SELECT goal_id FROM sub_targets WHERE id='s6'").fetchone()
    og = conn.execute("SELECT goal_id FROM observations WHERE sub_target_id='s6'").fetchone()
    check("spin-out: sub-target + obs re-pointed to g2", st["goal_id"] == "g2" and og["goal_id"] == "g2")

    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} passed.")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
