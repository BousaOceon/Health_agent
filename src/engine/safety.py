"""Safety-critical alert (design §6.2 / §11) — fires at PROCESSING time, not at
confirmation. Keys off the capture-time `severity_screen='Safety'` set by the
extractor (a language screen, independent of any benchmark grade), so deferring
assessment never mutes it.

The notifier is pluggable: the default logs METADATA ONLY (no clinical content
in logs — a project convention). A real email notifier wires in at Phase 4.
"""
import logging

log = logging.getLogger(__name__)


def _default_notify(conn, appointment_id, row, message):
    # metadata only — never the note text/clinical content in logs
    log.warning("SAFETY screen tripped: appointment=%s observation=%s sub_target=%s date=%s",
                appointment_id, row["id"], row["sub_target_id"], row["date"])


def screen_appointment_for_safety(conn, appointment_id, *, notify=None) -> list[dict]:
    """Return (and dispatch) any Safety-screened findings on this appointment.

    Fires on severity_screen='Safety' regardless of the sub-target's standing
    severity ('screened, not silent') — a new airway concern on an un-seeded
    medical area still escalates."""
    rows = conn.execute(
        """SELECT o.id, o.sub_target_id, o.note, o.date, o.severity_screen,
                  s.title AS sub_target_title, s.severity AS sub_target_severity
           FROM observations o JOIN sub_targets s ON o.sub_target_id = s.id
           WHERE o.source_encounter_id = ? AND o.severity_screen = 'Safety'
             AND o.status = 'active'""",
        (appointment_id,),
    ).fetchall()
    notify = notify or _default_notify
    alerts = []
    for r in rows:
        message = (f"SAFETY ALERT - {r['sub_target_title']} ({r['date']}): {r['note']} "
                   f"[appointment {appointment_id}]")
        alerts.append({"observation_id": r["id"], "sub_target_id": r["sub_target_id"],
                       "sub_target_title": r["sub_target_title"], "date": r["date"],
                       "message": message})
        notify(conn, appointment_id, r, message)
    return alerts
