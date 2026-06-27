"""Tests for the strategy lane (set-diff + apply) and the safety screen.
Deterministic — the substring matcher stands in for the Haiku entity resolver.

Run: python -m src.engine.test_strategy
"""
import sqlite3
import sys

from src.db import writes
from src.db.schema import init_db
from src.db.store import new_id, now_iso
from src.engine import apply, safety, strategy


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    conn.execute("INSERT INTO goal_pages (id,title,category,status) VALUES ('g','G','NDIS','Active')")
    conn.execute("INSERT INTO sub_targets (id,title,goal_id,ndis,status,severity,created_at) "
                 "VALUES ('st1','Dressing','g',1,'Active',NULL,?)", (now_iso(),))
    conn.execute("INSERT INTO sub_targets (id,title,goal_id,ndis,status,severity,created_at) "
                 "VALUES ('med','Dysphagia','g',0,'Active','Safety-critical',?)", (now_iso(),))
    conn.commit()
    return conn


def add_appt(conn):
    appt = writes.new_appointment(conn, appointment_date="2026-06-01", status="draft")
    writes.confirm_appointment(conn, appt)
    conn.commit()
    return appt


def add_strategy_obs(conn, appt, sub_target, note, date="2026-06-01"):
    sid = new_id("sobs")
    conn.execute("INSERT INTO strategy_observations (id,sub_target_id,source_encounter_id,author,date,note) "
                 "VALUES (?,?,?,'Provider',?,?)", (sid, sub_target, appt, date, note))
    conn.commit()
    return sid


RESULTS = []
def check(name, cond):
    RESULTS.append(bool(cond)); print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    # 1. new tactic -> Added candidate -> apply creates component + log + links the shell
    conn = fresh(); appt = add_appt(conn)
    sobs = add_strategy_obs(conn, appt, "st1", "[proposing-new] try a chewy tool for regulation")
    cands = strategy.setdiff(conn, appt)  # default substring matcher; no components -> new
    check("setdiff: new tactic -> 1 Added candidate", len(cands) == 1)
    cand = conn.execute("SELECT change_class, change_type FROM candidates WHERE id=?", (cands[0],)).fetchone()
    check("setdiff: candidate is strategy-diff/Added", cand["change_class"] == "strategy-diff" and cand["change_type"] == "Added")
    apply.apply_candidate(conn, cands[0])
    comp = conn.execute("SELECT id,status,definition FROM strategies WHERE sub_target_id='st1'").fetchone()
    log = conn.execute("SELECT change_type FROM strategy_change_log").fetchone()
    linked = conn.execute("SELECT component_id FROM strategy_observations WHERE id=?", (sobs,)).fetchone()
    check("apply Added: component created Active", comp and comp["status"] == "Active")
    check("apply Added: strategy_change_log Added entry", log["change_type"] == "Added")
    check("apply Added: shell linked to new component", linked["component_id"] == comp["id"])

    # 2. continuing mention matching an existing component -> Still-active, bump clock, no candidate
    conn = fresh(); appt = add_appt(conn)
    comp_id = writes.new_strategy(conn, title="Visual schedule", sub_target_id="st1",
                                  introduced="2026-01-01", last_referenced="2026-01-01")
    conn.commit()
    sobs = add_strategy_obs(conn, appt, "st1", "[continuing] keep using the Visual schedule", date="2026-06-01")
    cands = strategy.setdiff(conn, appt)
    sh = conn.execute("SELECT component_id, status_read FROM strategy_observations WHERE id=?", (sobs,)).fetchone()
    lr = conn.execute("SELECT last_referenced FROM strategies WHERE id=?", (comp_id,)).fetchone()["last_referenced"]
    check("setdiff: continuing match -> no candidate", cands == [])
    check("setdiff: shell -> Still-active + linked", sh["status_read"] == "Still-active" and sh["component_id"] == comp_id)
    check("setdiff: staleness clock bumped to mention date", lr == "2026-06-01")

    # 3. stopping mention -> Discontinued candidate -> apply retires the component
    conn = fresh(); appt = add_appt(conn)
    comp_id = writes.new_strategy(conn, title="Timer", sub_target_id="st1", introduced="2026-01-01")
    conn.commit()
    add_strategy_obs(conn, appt, "st1", "[stopping] stopped the Timer, it did not help")
    cands = strategy.setdiff(conn, appt)
    apply.apply_candidate(conn, cands[0])
    comp = conn.execute("SELECT status FROM strategies WHERE id=?", (comp_id,)).fetchone()
    log = conn.execute("SELECT change_type FROM strategy_change_log WHERE component_id=?", (comp_id,)).fetchone()
    check("setdiff/apply: stopping -> component retired", comp["status"].startswith("Inactive") and log["change_type"] == "Discontinued")

    # 4. strategy-status-correction: in-place status_read fix, NO log
    conn = fresh(); appt = add_appt(conn)
    sobs = add_strategy_obs(conn, appt, "st1", "[continuing] x")
    conn.execute("UPDATE strategy_observations SET status_read='Still-active' WHERE id=?", (sobs,)); conn.commit()
    corr = writes.new_candidate(conn, change_class="strategy-status-correction", origin="manual",
                                target_strategy_obs_id=sobs, to_value="Not-working-stated",
                                reason="was actually reported not working")
    conn.commit()
    logs_before = conn.execute("SELECT COUNT(*) FROM strategy_change_log").fetchone()[0]
    apply.apply_candidate(conn, corr)
    sh = conn.execute("SELECT status_read, status_superseded FROM strategy_observations WHERE id=?", (sobs,)).fetchone()
    logs_after = conn.execute("SELECT COUNT(*) FROM strategy_change_log").fetchone()[0]
    check("status-correction: status_read fixed in place + superseded",
          sh["status_read"] == "Not-working-stated" and sh["status_superseded"] == 1)
    check("status-correction: writes NO log entry", logs_after == logs_before)

    # 5. safety screen fires on a Safety-screened observation
    conn = fresh(); appt = add_appt(conn)
    f = writes.new_finding(conn, source_encounter_id=appt, source_fragment="coughing on fluids")
    writes.new_observation_shell(conn, finding_id=f, sub_target_id="med", source_encounter_id=appt,
                                 date="2026-06-01", note="coughed repeatedly on thin fluids", severity_screen="Safety")
    writes.new_observation_shell(conn, finding_id=f, sub_target_id="st1", source_encounter_id=appt,
                                 date="2026-06-01", note="dressed with help", severity_screen=None)
    conn.commit()
    fired = []
    alerts = safety.screen_appointment_for_safety(conn, appt, notify=lambda *a: fired.append(1))
    check("safety: exactly one Safety alert raised", len(alerts) == 1 and len(fired) == 1)
    check("safety: alert names the medical sub-target", alerts[0]["sub_target_title"] == "Dysphagia")

    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} passed.")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
