"""Tests for the injection builders + Pass 1 grading (stubbed Claude call).

Run: python -m src.engine.test_pass1
"""
import json
import re
import sqlite3
import sys

from src.db import writes
from src.db.schema import init_db
from src.db.store import now_iso
from src.engine import injection, pass1
from src.engine.benchmark import seed_baseline


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    conn.execute("INSERT INTO goal_pages (id,title,category,scope,status) "
                 "VALUES ('g','Self-Care','NDIS','daily living and personal care','Active')")
    conn.execute(
        "INSERT INTO sub_targets (id,title,goal_id,scope_line,current_benchmark,benchmark_as_of,ndis,status,created_at) "
        "VALUES ('st_a','Dressing','g','putting on/removing clothing','needs help throughout','2026-01-01',1,'Active',?)",
        (now_iso(),))
    conn.execute(
        "INSERT INTO sub_targets (id,title,goal_id,scope_line,ndis,status,created_at) "
        "VALUES ('st_b','Sleep onset','g','settling without an adult',0,'Active',?)",  # no benchmark
        (now_iso(),))
    conn.execute("INSERT INTO providers (id,title,aliases,type) "
                 "VALUES ('p','Madelaine Tomlin','Maddy, M. Tomlin','OT')")
    conn.commit()
    return conn


def stub(prompt, *, model, max_tokens=8000, system=None):
    """Grades every observation ref in the prompt as 'Above'."""
    refs = re.findall(r"ref=(\S+)", prompt)
    return json.dumps([{"ref": r, "assessment": "Above",
                        "rationale": "unprompted vs 'needs help'", "confidence": "high"} for r in refs])


RESULTS = []
def check(name, cond):
    RESULTS.append(bool(cond)); print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    # --- injection builders ---
    conn = fresh()
    rl = injection.subtarget_routing_list(conn)
    check("routing list: id + scope present, benchmark text absent",
          "st_a" in rl and "putting on/removing clothing" in rl and "needs help throughout" not in rl)
    pl = injection.provider_list(conn)
    check("provider list: name + aliases + type", all(s in pl for s in ["Madelaine Tomlin", "Maddy", "OT"]))
    check("active strategies: empty-state note", "no active strategies" in injection.active_strategy_titles(conn))
    bm = injection.benchmarks_for(conn, ["st_a", "st_b"])
    check("benchmarks_for: benchmarked row shows text; un-benchmarked says Adjacent",
          "needs help throughout" in bm and "Adjacent" in bm)

    # --- Pass 1 grade_appointment ---
    conn = fresh()
    appt = writes.new_appointment(conn, appointment_date="2026-06-01", status="draft")
    writes.confirm_appointment(conn, appt)
    seed_baseline(conn, sub_target_id="st_a", benchmark_text="needs help throughout",
                  effective_date="2026-01-01", advance=True)
    f = writes.new_finding(conn, source_encounter_id=appt, source_fragment="dressed self")
    o1 = writes.new_observation_shell(conn, finding_id=f, sub_target_id="st_a",
                                      source_encounter_id=appt, date="2026-06-01",
                                      note="put shirt on unprompted")
    conn.commit()
    # shell is unassessed before Pass 1
    pre = conn.execute("SELECT assessment FROM observations WHERE id=?", (o1,)).fetchone()
    check("shell starts unassessed (NULL)", pre["assessment"] is None)

    pass1.grade_appointment(conn, appt, call=stub)
    row = conn.execute(
        "SELECT assessment, assessment_rationale, assessment_confidence, graded_against_benchmark_id, "
        "benchmark_as_of_at_obs FROM observations WHERE id=?", (o1,)).fetchone()
    check("Pass 1: graded Above", row["assessment"] == "Above")
    check("Pass 1: rationale + confidence frozen", bool(row["assessment_rationale"]) and row["assessment_confidence"] == "high")
    check("Pass 1: graded_against = governing baseline version", row["graded_against_benchmark_id"] is not None)
    check("Pass 1: benchmark_as_of_at_obs stamped", row["benchmark_as_of_at_obs"] == "2026-01-01")

    # --- assess() single unit (cascade path) ---
    obs_row = conn.execute("SELECT * FROM observations WHERE id=?", (o1,)).fetchone()
    check("assess(): single-obs grade", pass1.assess(obs_row, "needs help throughout", call=stub) == "Above")

    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} passed.")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
