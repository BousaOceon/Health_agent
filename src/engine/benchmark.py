"""Benchmark change-log operations — the append-only history + the live state.

A benchmark "version" is a benchmark_change_log row. The governing version for
an observation is the latest log entry whose effective_date <= the obs date —
this is the C10 cascade version key (observations.graded_against_benchmark_id).

write_benchmark_change appends a log entry AND advances the sub-target's live
benchmark; seed_baseline writes the start anchor (FSSP) at the 1d data load.
"""
from src.db.store import new_id, now_iso


def governing_benchmark_version(conn, sub_target_id: str, on_date: str):
    """The change-log entry in force for `on_date` (latest effective_date <= on_date).

    Tie-break by insertion order (rowid DESC) so a later Correction sharing an
    effective_date supersedes the value it corrects, even within the same second."""
    return conn.execute(
        """SELECT * FROM benchmark_change_log
           WHERE sub_target_id = ? AND effective_date <= ?
           ORDER BY effective_date DESC, created_at DESC, rowid DESC LIMIT 1""",
        (sub_target_id, on_date),
    ).fetchone()


def latest_benchmark_version(conn, sub_target_id: str):
    return conn.execute(
        """SELECT * FROM benchmark_change_log WHERE sub_target_id = ?
           ORDER BY effective_date DESC, created_at DESC, rowid DESC LIMIT 1""",
        (sub_target_id,),
    ).fetchone()


def write_benchmark_change(conn, *, sub_target_id, change_type, to_value,
                           effective_date, from_value=None, triggering_observation_ids=None,
                           confirmed_by="Matt-approved", candidate_id=None,
                           advance=True) -> str:
    """Append a benchmark_change_log entry; optionally advance the live benchmark.

    `advance` updates sub_targets.current_benchmark + benchmark_as_of (skip for a
    pure historical Baseline that sits *below* an already-set live benchmark)."""
    import json
    log_id = new_id("bcl")
    title = f"{sub_target_id} - {change_type} - {effective_date}"
    conn.execute(
        """INSERT INTO benchmark_change_log
           (id,title,sub_target_id,change_type,from_value,to_value,effective_date,
            triggering_observation_ids,confirmed_by,candidate_id,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (log_id, title, sub_target_id, change_type, from_value, to_value, effective_date,
         json.dumps(triggering_observation_ids or []), confirmed_by, candidate_id, now_iso()),
    )
    if advance:
        conn.execute(
            "UPDATE sub_targets SET current_benchmark = ?, benchmark_as_of = ? WHERE id = ?",
            (to_value, effective_date, sub_target_id),
        )
    return log_id


def seed_baseline(conn, *, sub_target_id, benchmark_text, effective_date,
                  advance=False) -> str:
    """Write the FSSP start-anchor Baseline (1d data load). advance=False by default
    because the 13/06 live benchmark already sits above it on the sub-target row."""
    return write_benchmark_change(
        conn, sub_target_id=sub_target_id, change_type="Baseline",
        to_value=benchmark_text, effective_date=effective_date,
        confirmed_by="Matt-approved", advance=advance,
    )
