"""Persist an extraction result as a DRAFT (the entry-flow write path).

Writes the appointment (draft), findings, UNASSESSED observation shells,
strategy-observation shells, and actions. Nothing is graded here — Pass 1 runs
at confirmation. Provider names resolve through the SQLite matcher; an
observation pointing at an unknown sub-target falls back to the Unclassified pen
(capture-broadly: never drop the fact).
"""
from src.db import writes
from src.db.providers import find_or_create_provider
from src.db.store import insert, new_id, today_iso

_PEN = "st_pen_unclassified"
_MED_PEN = "st_pen_medical_watch"


def _goal_of(conn, sub_target_id):
    r = conn.execute("SELECT goal_id FROM sub_targets WHERE id=?", (sub_target_id,)).fetchone()
    return r["goal_id"] if r else None


def _valid_st(conn, sid):
    return bool(sid and conn.execute("SELECT 1 FROM sub_targets WHERE id=?", (sid,)).fetchone())


def _resolve_st(conn, sid):
    return sid if _valid_st(conn, sid) else _PEN


def persist_extraction(conn, extracted: dict, *, backfill=0, gmail_link=None,
                       source_email=None, source_ref=None, content_sources=None,
                       commit=True) -> str:
    appt = extracted.get("appointment", {}) or {}
    appointment_id = writes.new_appointment(
        conn, title=appt.get("title"), appointment_date=appt.get("appointment_date"),
        meeting_type=appt.get("meeting_type"), type=appt.get("appointment_type"),
        report_received_date=appt.get("report_received_date"), source_email=source_email,
        gmail_link=gmail_link, source_ref=source_ref, backfill=backfill,
        sub_targets_touched=appt.get("sub_targets_touched"),
        # file-derived content_sources (the actual source) override the model's guess
        content_sources=content_sources if content_sources is not None else appt.get("content_sources"),
        status="draft")
    if appt.get("summary"):
        conn.execute("UPDATE appointments SET summary=? WHERE id=?", (appt["summary"], appointment_id))
    if extracted.get("self_review"):
        writes.set_appointment_flags(conn, appointment_id, extracted["self_review"])

    # all attendees -> appointment_providers (authoritative multi-relation).
    # Combined-name strings are split before matching (never one junk record).
    from src.db.providers import split_combined, looks_like_combined
    for name in appt.get("providers", []) or []:
        names = split_combined(name) if looks_like_combined(name) else [name]
        for n in names:
            pid = find_or_create_provider(conn, n)
            if pid:
                conn.execute(
                    "INSERT OR IGNORE INTO appointment_providers (appointment_id, provider_id) VALUES (?,?)",
                    (appointment_id, pid))

    # findings -> id map (observations reference the local 'ref')
    ref_to_id = {}
    for f in extracted.get("findings", []) or []:
        fid = writes.new_finding(
            conn, source_encounter_id=appointment_id, source_fragment=f.get("source_fragment", ""),
            title=f.get("title"), fan_out_rationale=f.get("fan_out_rationale"),
            fan_out_confidence=f.get("fan_out_confidence"))
        ref_to_id[f.get("ref")] = fid

    default_date = appt.get("appointment_date")

    # observation shells (assessment NULL)
    for o in extracted.get("observations", []) or []:
        sid = _resolve_st(conn, o.get("sub_target_id"))
        fid = ref_to_id.get(o.get("finding_ref"))
        if fid is None:  # finding missing -> minimal finding so provenance holds
            fid = writes.new_finding(conn, source_encounter_id=appointment_id,
                                     source_fragment=o.get("note", ""))
        prov = (find_or_create_provider(conn, o["source_provider_name"])
                if o.get("author") == "Provider" and o.get("source_provider_name") else None)
        sev = o.get("severity_screen") if o.get("severity_screen") in ("None", "Watch", "Safety") else None
        writes.new_observation_shell(
            conn, finding_id=fid, sub_target_id=sid, source_encounter_id=appointment_id,
            date=o.get("date") or default_date, author=o.get("author", "Provider"),
            source=o.get("source", "Appointment Report"), goal_id=_goal_of(conn, sid),
            source_provider_id=prov, note=o.get("note"),
            milestone=1 if o.get("milestone") else 0, severity_screen=sev)

    # strategy-observation shells (status_read NULL — set later by the set-diff)
    for s in extracted.get("strategy_observations", []) or []:
        sid = _resolve_st(conn, s.get("sub_target_id"))
        fid = ref_to_id.get(s.get("finding_ref"))
        prov = (find_or_create_provider(conn, s["source_provider_name"])
                if s.get("author") == "Provider" and s.get("source_provider_name") else None)
        note = s.get("note", "")
        if s.get("status_language"):
            note = f"[{s['status_language']}] {note}"
        insert(conn, "strategy_observations", {
            "id": new_id("sobs"), "finding_id": fid, "sub_target_id": sid,
            "source_encounter_id": appointment_id, "source_provider_id": prov,
            "author": s.get("author", "Provider"), "date": s.get("date") or default_date,
            "note": note})

    # actions (Needs Triage during backfill; Open otherwise)
    for a in extracted.get("actions", []) or []:
        sid = a.get("sub_target_id")
        sid = sid if _valid_st(conn, sid) else None
        prov = find_or_create_provider(conn, a["provider_name"]) if a.get("provider_name") else None
        insert(conn, "health_actions", {
            "id": new_id("act"), "title": a.get("title", ""), "source_appointment_id": appointment_id,
            "provider_id": prov, "sub_target_id": sid, "assigned_to": a.get("assigned_to"),
            "category": a.get("category"), "priority": a.get("priority"),
            "status": "Needs Triage" if backfill else "Open", "due_date": a.get("due_date"),
            "opened_date": today_iso(), "notes": a.get("notes")})

    if commit:
        conn.commit()
    return appointment_id
