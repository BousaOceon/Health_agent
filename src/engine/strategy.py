"""Strategy lane (design §7) — the set-diff that maintains the component inventory.

Every strategy mention was captured at extraction as a strategy_observation shell
(component_id NULL, status_read NULL), exactly as observation shells are unassessed.
At confirmation the set-diff runs: resolve each mention to an existing component
for that sub-target (entity resolution — a Haiku `match`, injected for testing),
set status_read, bump the staleness clock, and raise strategy-diff candidates only
where a component actually changes. Effectiveness is STATED-only, never inferred.
"""
import re

from src.db.store import new_id, now_iso
from src.db.writes import new_candidate

# extraction status_language -> reconciled status_read
_STATUS_MAP = {
    "proposing-new": "New-proposed",
    "continuing": "Still-active",
    "working-stated": "Working-stated",
    "not-working-stated": "Not-working-stated",
    "stopping": "Discontinued-stated",
}


def write_strategy_change(conn, *, component_id, sub_target_id, change_type, to_value,
                          from_value=None, reason=None, effective_date, source_encounter_id=None,
                          confirmed_by="Matt-approved", candidate_id=None) -> str:
    log_id = new_id("scl")
    title = f"{component_id or sub_target_id} - {change_type} - {effective_date}"
    conn.execute(
        """INSERT INTO strategy_change_log
           (id,title,component_id,sub_target_id,change_type,from_value,to_value,reason,
            effective_date,source_encounter_id,confirmed_by,candidate_id,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (log_id, title, component_id, sub_target_id, change_type, from_value, to_value, reason,
         effective_date, source_encounter_id, confirmed_by, candidate_id, now_iso()),
    )
    return log_id


def _status_language(note: str) -> str:
    m = re.match(r"^\[([^\]]+)\]", note or "")
    return m.group(1) if m else "continuing"


def _default_match(note, components):
    """No-LLM fallback: substring match of a component title in the mention note."""
    low = (note or "").lower()
    for c in components:
        if c["title"] and c["title"].lower() in low:
            return c["id"]
    return None


def setdiff(conn, appointment_id, match=None, *, commit=True) -> list[str]:
    """Reconcile this appointment's strategy mentions against the inventory.

    `match(note, components) -> component_id | None` is the entity-resolution step
    (Haiku in production, injectable for tests). Returns created candidate ids.
    """
    match = match or _default_match
    shells = conn.execute(
        """SELECT * FROM strategy_observations
           WHERE source_encounter_id = ? AND status_read IS NULL AND status = 'active'
           ORDER BY date""",
        (appointment_id,),
    ).fetchall()

    created = []
    for sh in shells:
        sub_target_id = sh["sub_target_id"]
        components = conn.execute(
            "SELECT id, title, definition FROM strategies WHERE sub_target_id = ? AND status = 'Active'",
            (sub_target_id,),
        ).fetchall()
        lang = _status_language(sh["note"])
        status_read = _STATUS_MAP.get(lang, "Still-active")
        matched = match(sh["note"], components) if components else None

        if matched:
            conn.execute(
                "UPDATE strategy_observations SET component_id = ?, status_read = ? WHERE id = ?",
                (matched, status_read, sh["id"]))
            conn.execute("UPDATE strategies SET last_referenced = ? WHERE id = ?",
                         (sh["date"], matched))  # staleness clock — bump on EVERY mention
            if status_read in ("Working-stated", "Not-working-stated") and sh["note"]:
                conn.execute(
                    "UPDATE strategies SET effectiveness_context = ? WHERE id = ?",
                    (sh["note"], matched))  # STATED-only
            if status_read == "Discontinued-stated":
                created.append(new_candidate(
                    conn, change_class="strategy-diff", change_type="Discontinued",
                    origin="system", target_strategy_id=matched, target_strategy_obs_id=sh["id"],
                    reason=f"Provider stated discontinuation: {sh['note']}", confidence="medium"))
        else:
            # not present -> propose a new component
            if lang == "proposing-new":
                status_read = "New-proposed"
            conn.execute("UPDATE strategy_observations SET status_read = ? WHERE id = ?",
                         (status_read, sh["id"]))
            created.append(new_candidate(
                conn, change_class="strategy-diff", change_type="Added", origin="system",
                target_subtarget_id=sub_target_id, target_strategy_obs_id=sh["id"],
                to_value=sh["note"], reason=f"New tactic mentioned: {sh['note']}", confidence="medium"))

    if commit:
        conn.commit()
    return created


def make_matcher(call=None):
    """Haiku entity-resolution matcher: mention -> existing component id, or None.
    Tiny pool per sub-target, so a bounded classification."""
    from src import claude

    def match(note, components):
        if not components:
            return None
        call_fn = call or claude.call
        listing = "\n".join(f"{i}: {c['title']}" for i, c in enumerate(components))
        prompt = (
            "A strategy/tactic was mentioned in a therapy note. Match it to ONE existing "
            "component below, or say NONE if it is a different/new tactic. Reply with only "
            "the number, or NONE.\n\n"
            f"MENTION: {note}\n\nEXISTING COMPONENTS:\n{listing}\n\nAnswer:")
        ans = call_fn(prompt, model=claude.HAIKU, max_tokens=10).strip().upper()
        m = re.search(r"\d+", ans)
        if "NONE" in ans or not m:
            return None
        idx = int(m.group())
        return components[idx]["id"] if 0 <= idx < len(components) else None

    return match
