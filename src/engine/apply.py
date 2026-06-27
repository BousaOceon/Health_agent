"""Apply an approved candidate — the gate's mutation handler (design §2, schema §4).

On approval: record the decision, apply the typed mutation, write the change-log
entry where a benchmark/strategy actually moves, run the cascade where the change
vocabulary requires it, and back-link the resulting log entry. The two in-place
corrections write NO log entry (the approved candidate row is their audit).

A normal forward benchmark-change does NOT cascade (it is the Pass 2 output).
Corrections DO cascade. assess() (Pass-1 Haiku) is injected for the cascade.
"""
import json

from src.db.store import now_iso
from src.db.writes import new_strategy
from src.engine import cascade as cascade_mod
from src.engine.benchmark import write_benchmark_change
from src.engine.strategy import write_strategy_change


def _strategy_obs_date(conn, sobs_id):
    if not sobs_id:
        return None
    r = conn.execute("SELECT date FROM strategy_observations WHERE id=?", (sobs_id,)).fetchone()
    return r["date"] if r else None


def _obs_dates(conn, obs_ids):
    if not obs_ids:
        return []
    q = ",".join("?" for _ in obs_ids)
    rows = conn.execute(f"SELECT date FROM observations WHERE id IN ({q})", obs_ids).fetchall()
    return [r["date"] for r in rows]


def _finalise(conn, candidate_id, *, decided_by, reason_class, note,
              log_table=None, log_id=None):
    conn.execute(
        """UPDATE candidates SET status='approved', decided_by=?, decided_at=?,
             correction_reason_class=COALESCE(?, correction_reason_class),
             decision_note=?, resulting_log_table=?, resulting_log_id=?
           WHERE id=?""",
        (decided_by, now_iso(), reason_class, note, log_table, log_id, candidate_id),
    )


def apply_candidate(conn, candidate_id, *, assess=None, decided_by="Matt",
                    reason_class=None, note=None, summarize=None, backfill=0,
                    commit=True) -> dict:
    """Approve + apply a candidate. Returns a result dict (log id / cascade outcome)."""
    c = conn.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
    if c is None:
        raise ValueError(f"no such candidate: {candidate_id}")
    if c["status"] != "pending":
        raise ValueError(f"candidate {candidate_id} is {c['status']}, not pending")

    cls = c["change_class"]
    sub_target_id = c["target_subtarget_id"]
    obs_ids = json.loads(c["source_observation_ids"]) if c["source_observation_ids"] else []
    result = {"candidate_id": candidate_id, "change_class": cls}

    if cls == "strategy-diff":
        change_type = c["change_type"] or "Added"
        eff = _strategy_obs_date(conn, c["target_strategy_obs_id"]) or c["created_at"][:10]
        if change_type == "Added":
            comp_id = new_strategy(conn, title=(c["to_value"] or "Untitled tactic")[:120],
                                   sub_target_id=c["target_subtarget_id"], status="Active",
                                   definition=c["to_value"], introduced=eff, last_referenced=eff)
            if c["target_strategy_obs_id"]:
                conn.execute("UPDATE strategy_observations SET component_id=? WHERE id=?",
                             (comp_id, c["target_strategy_obs_id"]))
            log_id = write_strategy_change(conn, component_id=comp_id, sub_target_id=c["target_subtarget_id"],
                                           change_type="Added", to_value=c["to_value"], reason=c["reason"],
                                           effective_date=eff, candidate_id=candidate_id)
        else:
            comp = conn.execute("SELECT sub_target_id, definition FROM strategies WHERE id=?",
                                (c["target_strategy_id"],)).fetchone()
            sub = comp["sub_target_id"] if comp else c["target_subtarget_id"]
            from_val = comp["definition"] if comp else None
            if change_type == "Adjusted":
                conn.execute("UPDATE strategies SET definition=? WHERE id=?",
                             (c["to_value"], c["target_strategy_id"]))
            elif change_type == "Discontinued":
                conn.execute("UPDATE strategies SET status='Inactive-superseded', outcome_note=? WHERE id=?",
                             (c["reason"], c["target_strategy_id"]))
            elif change_type == "Achieved":
                conn.execute("UPDATE strategies SET status='Achieved', outcome_note=? WHERE id=?",
                             (c["reason"], c["target_strategy_id"]))
            log_id = write_strategy_change(conn, component_id=c["target_strategy_id"], sub_target_id=sub,
                                           change_type=change_type, from_value=from_val, to_value=c["to_value"],
                                           reason=c["reason"], effective_date=eff, candidate_id=candidate_id)
        _finalise(conn, candidate_id, decided_by=decided_by, reason_class=reason_class, note=note,
                  log_table="strategy_change_log", log_id=log_id)
        result["log_id"] = log_id

    elif cls == "strategy-status-correction":
        # in-place fix of a strategy observation's status_read; NO log (candidate is the audit)
        conn.execute("UPDATE strategy_observations SET status_read=?, status_superseded=1 WHERE id=?",
                     (c["to_value"], c["target_strategy_obs_id"]))
        _finalise(conn, candidate_id, decided_by=decided_by, reason_class=reason_class, note=note)

    elif cls in ("benchmark-change", "benchmark-correction", "benchmark-revert"):
        if not c["to_value"]:
            raise ValueError(f"{cls} candidate {candidate_id} has no to_value (benchmark text)")
        change_type = c["change_type"] or ("Correction" if cls == "benchmark-correction"
                                           else "Revert" if cls == "benchmark-revert" else "Progression")
        if cls == "benchmark-correction":
            # a correction supersedes the version it replaces -> take that version's
            # effective date, so it governs the same observations the wrong value did.
            st = conn.execute("SELECT benchmark_as_of FROM sub_targets WHERE id=?",
                              (sub_target_id,)).fetchone()
            effective_date = st["benchmark_as_of"]
        else:
            dates = _obs_dates(conn, obs_ids)
            effective_date = max(dates) if dates else c["created_at"][:10]
        log_id = write_benchmark_change(
            conn, sub_target_id=sub_target_id, change_type=change_type,
            from_value=c["from_value"], to_value=c["to_value"],
            effective_date=effective_date, triggering_observation_ids=obs_ids,
            candidate_id=candidate_id, advance=True,
        )
        _finalise(conn, candidate_id, decided_by=decided_by, reason_class=reason_class,
                  note=note, log_table="benchmark_change_log", log_id=log_id)
        result["log_id"] = log_id
        if cls == "benchmark-correction":  # only corrections cascade
            if assess is None:
                raise ValueError("benchmark-correction needs an assess() callable for the cascade")
            result["cascade"] = cascade_mod.cascade(
                conn, sub_target_id, "correction", assess,
                candidate_id=candidate_id, summarize=summarize, backfill=backfill, commit=False)

    elif cls == "assessment-correction":
        if assess is None:
            raise ValueError("assessment-correction needs an assess() callable for the cascade")
        # in-place grade fix on the target observation; NO log entry
        conn.execute(
            "UPDATE observations SET assessment=?, assessment_superseded=1 WHERE id=?",
            (c["to_value"], c["target_observation_id"]),
        )
        _finalise(conn, candidate_id, decided_by=decided_by, reason_class=reason_class, note=note)
        result["cascade"] = cascade_mod.cascade(
            conn, sub_target_id, "correction", assess,
            candidate_id=candidate_id, summarize=summarize, backfill=backfill, commit=False)

    elif cls == "adjacent-promotion":
        # promote Adjacent-watch -> Active and seed the first benchmark as a Baseline
        if not c["to_value"]:
            raise ValueError("adjacent-promotion needs a seed benchmark (to_value)")
        dates = _obs_dates(conn, obs_ids)
        effective_date = max(dates) if dates else c["created_at"][:10]
        conn.execute("UPDATE sub_targets SET status='Active' WHERE id=?", (sub_target_id,))
        log_id = write_benchmark_change(
            conn, sub_target_id=sub_target_id, change_type="Baseline",
            to_value=c["to_value"], effective_date=effective_date,
            candidate_id=candidate_id, advance=True)
        _finalise(conn, candidate_id, decided_by=decided_by, reason_class=reason_class,
                  note=note, log_table="benchmark_change_log", log_id=log_id)
        result["log_id"] = log_id

    elif cls == "spin-out":
        # re-point the sub-target's goal; history travels on the relation (no log)
        conn.execute("UPDATE sub_targets SET goal_id=? WHERE id=?", (c["to_value"], sub_target_id))
        conn.execute("UPDATE observations SET goal_id=? WHERE sub_target_id=?",
                     (c["to_value"], sub_target_id))
        _finalise(conn, candidate_id, decided_by=decided_by, reason_class=reason_class, note=note)

    else:
        raise ValueError(f"unknown change_class: {cls}")

    if commit:
        conn.commit()
    return result


def reject_candidate(conn, candidate_id, *, decided_by="Matt", reject_reason_class=None,
                     note=None, commit=True) -> None:
    c = conn.execute("SELECT status FROM candidates WHERE id=?", (candidate_id,)).fetchone()
    if c is None:
        raise ValueError(f"no such candidate: {candidate_id}")
    if c["status"] != "pending":
        raise ValueError(f"candidate {candidate_id} is {c['status']}, not pending")
    conn.execute(
        """UPDATE candidates SET status='rejected', decided_by=?, decided_at=?,
             reject_reason_class=?, decision_note=? WHERE id=?""",
        (decided_by, now_iso(), reject_reason_class, note, candidate_id),
    )
    if commit:
        conn.commit()
