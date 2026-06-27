"""Dashboard routes (Phase 1c: status + Candidates review)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.dashboard import queries
from src.db.store import connect

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
    reason_class = request.form.get("reason_class", "")
    note = request.form.get("note", "")
    # Single-user home-network deployment for now; auth wiring is deferred (admin = Matt).
    conn = connect()
    try:
        cand = queries.get_candidate(conn, candidate_id)
        if not cand:
            flash(f"Candidate {candidate_id} not found.", "error")
        elif cand["status"] != "pending":
            flash(f"Candidate already {cand['status']}.", "error")
        else:
            queries.decide_candidate(conn, candidate_id, decision, "Matt", reason_class, note)
            flash(f"Candidate {decision}. (Change application runs in the Phase 1d engine.)", "ok")
    finally:
        conn.close()
    return redirect(url_for("dashboard.candidates"))
