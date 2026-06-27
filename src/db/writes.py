"""Outcome-layer write helpers (Phase 1d engine write path).

Typed inserts over the SQLite store for the entry flow:
appointment draft -> findings -> observation shells -> (confirm) -> Pass 1
grades -> Pass 2 candidates. Keeps SQL out of the engine modules.
"""
import json
import sqlite3

from src.db.store import insert, new_id, now_iso


# ---------------------------------------------------------------------------
# Evidence layer
# ---------------------------------------------------------------------------

def new_appointment(conn: sqlite3.Connection, *, title=None, appointment_date=None,
                    meeting_type=None, type=None, report_received_date=None,
                    source_email=None, gmail_link=None, backfill=0,
                    sub_targets_touched=None, content_sources=None,
                    status="draft") -> str:
    aid = new_id("appt")
    insert(conn, "appointments", {
        "id": aid, "title": title, "appointment_date": appointment_date,
        "meeting_type": meeting_type, "type": type,
        "report_received_date": report_received_date, "source_email": source_email,
        "gmail_link": gmail_link, "backfill": backfill, "status": status,
        "sub_targets_touched": json.dumps(sub_targets_touched or []),
        "content_sources": json.dumps(content_sources or []),
    })
    return aid


def confirm_appointment(conn: sqlite3.Connection, appointment_id: str) -> None:
    """Flip a draft to confirmed. Pass 1 + Pass 2 run after this (gate-tight)."""
    conn.execute("UPDATE appointments SET status = 'confirmed' WHERE id = ? AND status = 'draft'",
                 (appointment_id,))


def set_appointment_flags(conn: sqlite3.Connection, appointment_id: str, self_review: dict) -> None:
    conn.execute("UPDATE appointments SET flags = ? WHERE id = ?",
                 (json.dumps(self_review), appointment_id))


# ---------------------------------------------------------------------------
# Benchmark lane: findings -> observation shells -> graded
# ---------------------------------------------------------------------------

def new_finding(conn: sqlite3.Connection, *, source_encounter_id, source_fragment,
                title=None, fan_out_rationale=None, fan_out_confidence=None) -> str:
    fid = new_id("find")
    insert(conn, "findings", {
        "id": fid, "source_encounter_id": source_encounter_id,
        "source_fragment": source_fragment, "title": title,
        "fan_out_rationale": fan_out_rationale, "fan_out_confidence": fan_out_confidence,
    })
    return fid


def new_observation_shell(conn: sqlite3.Connection, *, finding_id, sub_target_id,
                          source_encounter_id, date, author="Provider",
                          source="Appointment Report", goal_id=None,
                          source_provider_id=None, note=None, milestone=0,
                          severity_screen=None) -> str:
    """An UNASSESSED observation (assessment NULL) — extraction's output. Pass 1 grades it."""
    oid = new_id("obs")
    insert(conn, "observations", {
        "id": oid, "finding_id": finding_id, "sub_target_id": sub_target_id,
        "goal_id": goal_id, "source_encounter_id": source_encounter_id,
        "source_provider_id": source_provider_id, "author": author, "source": source,
        "date": date, "note": note, "milestone": milestone,
        "severity_screen": severity_screen,
    })
    return oid


def set_assessment(conn: sqlite3.Connection, observation_id: str, *, assessment,
                   rationale=None, confidence=None, benchmark_as_of_at_obs=None,
                   graded_against_benchmark_id=None, superseded=False) -> None:
    """Pass 1 / cascade write: set the derived grade. Rationale frozen on first set."""
    conn.execute(
        """UPDATE observations SET assessment = ?, assessment_rationale =
             COALESCE(assessment_rationale, ?), assessment_confidence = ?,
             benchmark_as_of_at_obs = ?, graded_against_benchmark_id = ?,
             assessment_superseded = ?
           WHERE id = ?""",
        (assessment, rationale, confidence, benchmark_as_of_at_obs,
         graded_against_benchmark_id, 1 if superseded else 0, observation_id),
    )


# ---------------------------------------------------------------------------
# Strategy lane
# ---------------------------------------------------------------------------

def new_strategy(conn: sqlite3.Connection, *, title, sub_target_id, status="Active",
                 definition=None, introduced=None, last_referenced=None,
                 introduced_by=None, source_encounter_id=None) -> str:
    sid = new_id("strat")
    insert(conn, "strategies", {
        "id": sid, "title": title, "sub_target_id": sub_target_id, "status": status,
        "definition": definition, "introduced": introduced,
        "last_referenced": last_referenced or introduced,
        "introduced_by": introduced_by, "source_encounter_id": source_encounter_id,
    })
    return sid


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

def new_candidate(conn: sqlite3.Connection, *, change_class, origin, reason,
                  change_type=None, target_subtarget_id=None, target_observation_id=None,
                  target_strategy_id=None, target_strategy_obs_id=None, from_value=None,
                  to_value=None, confidence=None, source_finding_ids=None,
                  source_observation_ids=None, triggering_rule=None, backfill=0) -> str:
    cid = new_id("cand")
    insert(conn, "candidates", {
        "id": cid, "change_class": change_class, "change_type": change_type,
        "origin": origin, "reason": reason,
        "target_subtarget_id": target_subtarget_id,
        "target_observation_id": target_observation_id,
        "target_strategy_id": target_strategy_id,
        "target_strategy_obs_id": target_strategy_obs_id,
        "from_value": from_value, "to_value": to_value, "confidence": confidence,
        "source_finding_ids": json.dumps(source_finding_ids) if source_finding_ids else None,
        "source_observation_ids": json.dumps(source_observation_ids) if source_observation_ids else None,
        "triggering_rule": triggering_rule, "status": "pending", "backfill": backfill,
        "created_at": now_iso(),
    })
    return cid


def pending_benchmark_candidate_exists(conn: sqlite3.Connection, sub_target_id: str) -> bool:
    row = conn.execute(
        """SELECT 1 FROM candidates
           WHERE target_subtarget_id = ? AND status = 'pending'
             AND change_class IN ('benchmark-change','benchmark-revert')
           LIMIT 1""",
        (sub_target_id,),
    ).fetchone()
    return row is not None
