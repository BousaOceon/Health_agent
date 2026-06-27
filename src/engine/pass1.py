"""Pass 1 — per-observation assessment (Haiku, at confirmation).

Grades unassessed observation shells against the current benchmark for their
sub-target, as of the observation's date. assess() is the atomic unit the
cascade also calls on recompute (first-assessment and re-assessment are one
code path). The Claude call goes through src.claude.call, so tests inject a stub.
"""
from src import claude
from src.config import settings
from src.db import writes
from src.engine import injection
from src.engine.benchmark import governing_benchmark_version


def _grade(observations_payload: str, benchmarks_text: str, appointment_date: str,
           call=None) -> list:
    """Run the assessment_prompt over a batch; return [{ref, assessment, rationale, confidence}]."""
    call = call or claude.call
    prompt = (settings["assessment_prompt"]
              .replace("###EXTRACTION_CONTEXT###", settings.get("extraction_context", ""))
              .replace("###BENCHMARKS###", benchmarks_text)
              .replace("###OBSERVATIONS###", observations_payload)
              .replace("###APPOINTMENT_DATE###", appointment_date or ""))
    return claude.parse_json(call(prompt, model=claude.HAIKU, max_tokens=4000))


def _payload(obs_rows) -> str:
    return "\n".join(
        f"- ref={o['id']} | sub_target={o['sub_target_id']} | date={o['date']} | {o['note'] or ''}"
        for o in obs_rows
    )


def assess(obs_row, benchmark_text: str, call=None) -> str:
    """Grade ONE observation against ONE benchmark text. The cascade's recompute unit."""
    bench = (f"=== ({obs_row['sub_target_id']}) ===\n"
             f"Current benchmark: {benchmark_text}" if benchmark_text
             else f"=== ({obs_row['sub_target_id']}) ===\nNo benchmark. Grade as Adjacent.")
    graded = _grade(_payload([obs_row]), bench, obs_row["date"], call)
    return graded[0]["assessment"] if graded else "At"


def grade_appointment(conn, appointment_id: str, call=None) -> dict:
    """Pass 1 at confirmation: grade every unassessed shell on this appointment,
    scoped to its touched sub-targets. Writes assessment + the governing benchmark
    version (graded_against_benchmark_id). Returns {observation_id: grade-dict}."""
    obs = conn.execute(
        """SELECT id, sub_target_id, date, note FROM observations
           WHERE source_encounter_id = ? AND assessment IS NULL AND status = 'active'
           ORDER BY sub_target_id, date""",
        (appointment_id,),
    ).fetchall()
    if not obs:
        return {}

    touched = sorted({o["sub_target_id"] for o in obs})
    benchmarks_text = injection.benchmarks_for(conn, touched)
    appt = conn.execute("SELECT appointment_date FROM appointments WHERE id = ?",
                        (appointment_id,)).fetchone()

    graded = {g["ref"]: g for g in _grade(_payload(obs), benchmarks_text,
                                          appt["appointment_date"], call)}
    results = {}
    for o in obs:
        g = graded.get(o["id"])
        if not g:
            continue
        governing = governing_benchmark_version(conn, o["sub_target_id"], o["date"])
        writes.set_assessment(
            conn, o["id"], assessment=g["assessment"], rationale=g.get("rationale"),
            confidence=g.get("confidence"),
            benchmark_as_of_at_obs=governing["effective_date"] if governing else None,
            graded_against_benchmark_id=governing["id"] if governing else None,
        )
        results[o["id"]] = g
    conn.commit()
    return results
