"""Dashboard routes: status + Candidates review (approve now applies via the engine)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.dashboard import queries
from src.db.store import connect
from src.engine import apply, pass1
from src.engine.summarize import make_summarizer

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    conn = connect()
    try:
        return render_template("index.html", counts=queries.status_counts(conn))
    finally:
        conn.close()


@bp.route("/candidates")
def candidates():
    conn = connect()
    try:
        groups = queries.pending_candidates_by_subtarget(conn)
        counts = queries.status_counts(conn)
        return render_template("candidates.html", groups=groups, counts=counts)
    finally:
        conn.close()


@bp.route("/candidates/<candidate_id>/decide", methods=["POST"])
def decide(candidate_id):
    decision = request.form.get("decision", "")
    reason_class = request.form.get("reason_class") or None
    note = request.form.get("note") or None
    # Single-user home-network deployment for now; auth wiring is deferred (admin = Matt).
    conn = connect()
    try:
        cand = queries.get_candidate(conn, candidate_id)
        if not cand:
            flash(f"Candidate {candidate_id} not found.", "error")
        elif cand["status"] != "pending":
            flash(f"Candidate already {cand['status']}.", "error")
        elif decision == "approved":
            try:
                # approve + apply the change (benchmark-change is fast; corrections cascade).
                apply.apply_candidate(conn, candidate_id, assess=pass1.assess,
                                      summarize=make_summarizer(conn), decided_by="Matt",
                                      reason_class=reason_class, note=note)
                flash("Candidate approved and applied.", "ok")
            except Exception as e:
                flash(f"Could not apply candidate: {e}", "error")
        elif decision == "rejected":
            apply.reject_candidate(conn, candidate_id, decided_by="Matt",
                                   reject_reason_class=reason_class, note=note)
            flash("Candidate rejected.", "ok")
        else:
            flash("Unknown decision.", "error")
    finally:
        conn.close()
    return redirect(url_for("dashboard.candidates"))
