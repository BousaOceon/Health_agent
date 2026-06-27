"""Build the ###PLACEHOLDER### injection strings from the SQLite store.

Extraction (Sonnet) gets: routing list (title + scope, NO benchmarks),
provider list, active strategy titles. Pass 1 (Haiku) gets: the benchmarks for
the touched sub-targets only. Replaces notion_writer's fetch_* helpers.
"""
import json


def subtarget_routing_list(conn) -> str:
    """(id) Title [Goal] -- scope_line, for every routable sub-target. NO benchmarks."""
    rows = conn.execute(
        """SELECT s.id, s.title, s.scope_line, g.title AS goal
           FROM sub_targets s JOIN goal_pages g ON s.goal_id = g.id
           WHERE s.status IN ('Active','Adjacent-watch')
           ORDER BY g.category, g.title, s.title"""
    ).fetchall()
    lines = []
    for r in rows:
        scope = (r["scope_line"] or "").strip()
        lines.append(f"- ({r['id']}) {r['title']} [{r['goal']}]" + (f" -- {scope}" if scope else ""))
    return "\n".join(lines)


def provider_list(conn) -> str:
    """canonical name | Aliases: ... | Type: ..."""
    rows = conn.execute("SELECT title, aliases, type FROM providers ORDER BY title").fetchall()
    lines = []
    for r in rows:
        parts = [r["title"]]
        if r["aliases"]:
            parts.append(f"Aliases: {r['aliases']}")
        if r["type"]:
            parts.append(f"Type: {r['type']}")
        lines.append(" | ".join(parts))
    return "\n".join(lines) or "(no providers on file)"


def active_strategy_titles(conn) -> str:
    """Thin list: 'Tactic title -> sub-target title' for Active components only."""
    rows = conn.execute(
        """SELECT st.title AS tactic, s.title AS sub_target
           FROM strategies st JOIN sub_targets s ON st.sub_target_id = s.id
           WHERE st.status = 'Active' ORDER BY s.title, st.title"""
    ).fetchall()
    if not rows:
        return "(no active strategies on file yet)"
    return "\n".join(f"- {r['tactic']} -> {r['sub_target']}" for r in rows)


def benchmarks_for(conn, sub_target_ids: list[str]) -> str:
    """Pass-1 injection: current benchmark + as-of + goal scope for the touched
    sub-targets that actually have a benchmark. Un-benchmarked ones are noted so
    the grader knows to return Adjacent."""
    if not sub_target_ids:
        return "(no sub-targets)"
    q = ",".join("?" for _ in sub_target_ids)
    rows = conn.execute(
        f"""SELECT s.id, s.title, s.current_benchmark, s.benchmark_as_of, s.status,
                   g.title AS goal, g.scope AS goal_scope
            FROM sub_targets s JOIN goal_pages g ON s.goal_id = g.id
            WHERE s.id IN ({q}) ORDER BY g.title, s.title""",
        sub_target_ids,
    ).fetchall()
    blocks = []
    for r in rows:
        if r["current_benchmark"]:
            blocks.append(
                f"=== ({r['id']}) {r['title']} [{r['goal']}] ===\n"
                f"Goal scope: {r['goal_scope']}\n"
                f"Current benchmark (as of {r['benchmark_as_of']}): {r['current_benchmark']}"
            )
        else:
            blocks.append(
                f"=== ({r['id']}) {r['title']} [{r['goal']}] ===\n"
                f"No benchmark (status: {r['status']}). Grade observations here as Adjacent (assessment N/A)."
            )
    return "\n\n".join(blocks)
