"""Provider matching over the SQLite providers table (was notion_writer.py).

Rules (validated Phase 1b, design §12): split combined-name strings before any
matching; normalise (strip titles, lowercase); fuzzy substring on Title; check
Aliases. The canonical provider list injected at extraction is the primary
defence — this matcher is the backstop. Never create a combined-name record.
"""
import logging
import re
import sqlite3

from src.db.store import insert, new_id

log = logging.getLogger(__name__)

_TITLE_PREFIXES = ("dr. ", "dr ", "mr. ", "mr ", "ms. ", "ms ",
                   "mrs. ", "mrs ", "prof. ", "prof ")


def normalize_name(name: str) -> str:
    """Strip honorifics and lowercase for matching."""
    name = (name or "").strip()
    low = name.lower()
    for prefix in _TITLE_PREFIXES:
        if low.startswith(prefix):
            name = name[len(prefix):]
            break
    return name.strip().lower()


def looks_like_combined(name: str) -> bool:
    """True if the string appears to bundle multiple people."""
    return bool(re.search(r",|\band\b|&", name or "", re.IGNORECASE))


def split_combined(name: str) -> list[str]:
    """Split a combined-name string into individual names (commas / and / &)."""
    parts = re.split(r",|\band\b|&", name or "", flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _aliases_list(raw: str | None) -> list[str]:
    return [a.strip() for a in (raw or "").split(",") if a.strip()]


def find_provider(conn: sqlite3.Connection, name: str) -> str | None:
    """Return the id of the provider matching `name`, or None. No creation.

    Order: exact normalised title, substring on title, then any alias.
    """
    if not name or not name.strip():
        return None
    if looks_like_combined(name):
        log.warning("find_provider got combined name %r — split before calling.", name)
        return None

    target = normalize_name(name)
    rows = conn.execute("SELECT id, title, aliases FROM providers").fetchall()

    # exact, then substring, then alias — in priority passes
    for r in rows:
        if normalize_name(r["title"]) == target:
            return r["id"]
    for r in rows:
        title_norm = normalize_name(r["title"])
        if target in title_norm or title_norm in target:
            return r["id"]
    for r in rows:
        for alias in _aliases_list(r["aliases"]):
            if normalize_name(alias) == target:
                return r["id"]
    return None


def find_or_create_provider(conn: sqlite3.Connection, name: str,
                            auto_create: bool = True) -> str | None:
    """Match `name`; if no match and auto_create, insert a stub flagged for review.

    Never creates a combined-name record. The caller must split combined strings
    (extraction is the primary defence) — a combined string here is refused.
    """
    if not name or not name.strip():
        return None
    if looks_like_combined(name):
        log.warning("Refusing to create combined-name provider %r — split first.", name)
        return None

    existing = find_provider(conn, name)
    if existing:
        return existing
    if not auto_create:
        return None

    pid = new_id("prov")
    insert(conn, "providers", {
        "id": pid,
        "title": name.strip(),
        "notes": "AUTO-CREATED stub — complete Type / NDIS Funded / Aliases.",
    })
    log.warning("Created provider stub (no match): %r — complete fields in dashboard.", name)
    return pid
