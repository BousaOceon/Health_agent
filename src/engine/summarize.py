"""Haiku summarizer that turns a Pass 2 supported-change into the proposed new
benchmark text (candidate.to_value), via benchmark_update_prompt. Injected into
Pass 2 so the pure-logic module stays LLM-free and testable.
"""
from src import claude
from src.config import settings


def make_summarizer(conn, call=None):
    call = call or claude.call

    def summarize(kind, obs_rows, current_benchmark):
        title_row = conn.execute("SELECT title FROM sub_targets WHERE id=?",
                                 (obs_rows[0]["sub_target_id"],)).fetchone()
        title = title_row["title"] if title_row else obs_rows[0]["sub_target_id"]
        obs_text = "\n".join(f"- {o['date']}: {o['note'] or ''}" for o in obs_rows)
        effective = max(o["date"] for o in obs_rows)
        prompt = (settings["benchmark_update_prompt"]
                  .replace("###SUBTARGET_TITLE###", title)
                  .replace("###CHANGE_TYPE###", kind)
                  .replace("###EFFECTIVE_DATE###", effective)
                  .replace("###CURRENT_BENCHMARK###", current_benchmark or "")
                  .replace("###SUPPORTING_OBSERVATIONS###", obs_text))
        to_value = call(prompt, model=claude.HAIKU, max_tokens=1500).strip()
        reason = f"{kind}: {len(obs_rows)} supporting observation(s) since the last benchmark change."
        return to_value, reason

    return summarize
