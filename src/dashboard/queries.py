"""Read/write helpers backing the dashboard pages.

Candidate review is the day-one surface. In Phase 1c approve/reject record the
*decision* (lifecycle + typed reason) only — applying the change (the mutation
+ the one-cascade/three-triggers engine) is wired in Phase 1d. The handlers
deliberately do not mutate benchmarks/strategies yet.
"""
import json

from src.db.store import now_iso


def status_counts(conn) -> dict:
    def c(table, where="", params=()):
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return conn.execute(sql, params).fetchone()[0]

    return {
        "goal_pages": c("goal_pages"),
        "sub_targets": c("sub_targets"),
        "sub_targets_benchmarked": c("sub_targets", "current_benchmark IS NOT NULL"),
        "sub_targets_adjacent": c("sub_targets", "status = 'Adjacent-watch'"),
        "providers": c("providers"),
        "observations": c("observations"),
        "candidates_pending": c("candidates", "status = 'pending'"),
        "candidates_total": c("candidates"),
        "benchmark_log": c("benchmark_change_log"),
    }


def pending_candidates_by_subtarget(conn) -> list[dict]:
    """Pending candidates grouped by their target sub-target (the review layout)."""
    rows = conn.execute(
        """
        SELECT c.*, s.title AS subtarget_title, g.title AS goal_title
        FROM candidates c
        LEFT JOIN sub_targets s ON c.target_subtarget_id = s.id
        LEFT JOIN goal_pages  g ON s.goal_id = g.id
        WHERE c.status = 'pending'
        ORDER BY g.title, s.title, c.created_at
        """
    ).fetchall()

    groups: dict[str, dict] = {}
    for r in rows:
        key = r["target_subtarget_id"] or "_ungrouped"
        if key not in groups:
            groups[key] = {
                "subtarget_id": r["target_subtarget_id"],
                "subtarget_title": r["subtarget_title"] or "(no sub-target)",
                "goal_title": r["goal_title"] or "",
                "candidates": [],
            }
        groups[key]["candidates"].append(dict(r))
    return list(groups.values())


def get_candidate(conn, candidate_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    return dict(r) if r else None


def decide_candidate(conn, candidate_id: str, decision: str, decided_by: str,
                     reason_class: str = "", note: str = "") -> None:
    """Record an approve/reject decision on a candidate (lifecycle only — 1c).

    decision: 'approved' | 'rejected'. reason_class maps to correction_reason_class
    (approve) or reject_reason_class (reject). The mutation + cascade are Phase 1d.
    """
    if decision not in ("approved", "rejected"):
        raise ValueError(f"bad decision: {decision}")

    fields = {
        "status": decision,
        "decided_by": decided_by,
        "decided_at": now_iso(),
        "decision_note": note or None,
    }
    if decision == "approved" and reason_class:
        fields["correction_reason_class"] = reason_class
    if decision == "rejected" and reason_class:
        fields["reject_reason_class"] = reason_class

    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE candidates SET {sets} WHERE id = ?",
        list(fields.values()) + [candidate_id],
    )
    conn.commit()
    # NOTE (Phase 1d): on approve, apply the mutation and run cascade()/Pass 2 here.


def insert_demo_candidate(conn) -> str:
    """Insert one pending demo candidate so the empty day-one page can be exercised.
    Not part of seeding — a manual helper for verifying the review UI."""
    from src.db.store import new_id
    cid = new_id("cand")
    conn.execute(
        """INSERT INTO candidates
           (id, change_class, origin, target_subtarget_id, from_value, to_value,
            reason, confidence, status, created_at)
           VALUES (?, 'benchmark-change', 'system', 'st_dressing', ?, ?, ?, 'medium', 'pending', ?)""",
        (cid,
         "Partial participation with setup and physical help...",
         "Independently pulls socks up and steps into pants with setup only...",
         "DEMO: 2 'Above' observations on Dressing since 2026-06; proposes a Progression. "
         "(Synthetic — verifies the review UI; real candidates arrive with the Phase 1d engine.)",
         now_iso()),
    )
    conn.commit()
    return cid
