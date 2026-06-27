"""The one cascade (design §4) — version-gated recompute + Pass 2 delta.

Fired by a CORRECTION or a confirmed-report RETRACTION (never by mere new data).
A normal forward benchmark-change does NOT cascade (it *is* the Pass 2 output).

Step 1 is version-gated (C10): assess() is the Pass-1 Haiku call, NOT pure
logic, so re-grading an observation on identical inputs could flip a grade and
break idempotency. Re-grade ONLY when the governing benchmark *version*
(graded_against_benchmark_id) has moved. The `assess` callable is injected
(Haiku in production, a deterministic stub in tests) so this module is testable.
"""
from src.db.store import new_id, now_iso
from src.engine import pass2
from src.engine.benchmark import governing_benchmark_version


def _record_recompute_audit(conn, obs_id, old, new, trigger, candidate_id):
    conn.execute(
        """INSERT INTO recompute_audit
           (id,observation_id,old_grade,new_grade,trigger,triggering_candidate_id,created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (new_id("rca"), obs_id, old, new, trigger, candidate_id, now_iso()),
    )


def cascade(conn, sub_target_id, trigger, assess, *, candidate_id=None,
            summarize=None, backfill=0, commit=True) -> dict:
    """Recompute grades whose benchmark version moved, then re-run Pass 2 delta.

    assess(obs_row, benchmark_text) -> grade. trigger in
    {'correction','report-retraction','data-load-advance'}.
    """
    regraded = []
    obs_rows = pass2.confirmed_active_observations(conn, sub_target_id)
    for obs in obs_rows:
        governing = governing_benchmark_version(conn, sub_target_id, obs["date"])
        if governing is None:
            continue  # no benchmark version in force yet (pre-baseline)
        if governing["id"] == obs["graded_against_benchmark_id"]:
            continue  # unchanged version -> keep grade, NO assess() call (idempotent)

        old = obs["assessment"]
        new = assess(obs, governing["to_value"])
        conn.execute(
            "UPDATE observations SET graded_against_benchmark_id = ?, benchmark_as_of_at_obs = ? WHERE id = ?",
            (governing["id"], governing["effective_date"], obs["id"]),
        )
        if new != old:
            conn.execute(
                "UPDATE observations SET assessment = ?, assessment_superseded = 1 WHERE id = ?",
                (new, obs["id"]),
            )
            if not backfill:
                _record_recompute_audit(conn, obs["id"], old, new, trigger, candidate_id)
            regraded.append({"obs": obs["id"], "old": old, "new": new})

    # step 2/3: re-run Pass 2 over THIS sub-target; emit delta candidates idempotently
    created = pass2.reconcile(conn, sub_target_id, summarize, backfill=backfill, commit=False)
    if commit:
        conn.commit()
    return {"regraded": regraded, "new_candidates": created}
