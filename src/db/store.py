"""SQLite connection + low-level access helpers (fetch-before-write discipline).

The DB path comes from settings.yaml (`db_path`, default data/health.db),
resolved relative to the repo root. Every connection enables foreign keys.
"""
import logging
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

from src.config import settings

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def db_path() -> Path:
    """Absolute path to the SQLite file (from settings.yaml, repo-root relative)."""
    configured = settings.get("db_path", "data/health.db")
    p = Path(configured)
    if not p.is_absolute():
        p = _REPO_ROOT / p
    return p


def connect() -> sqlite3.Connection:
    """Open the health DB with foreign keys on and Row access. Creates data/ if needed."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def new_id(prefix: str = "") -> str:
    """Generate a short unique id, optionally prefixed (e.g. new_id('cand') -> 'cand_ab12cd34')."""
    short = uuid.uuid4().hex[:8]
    return f"{prefix}_{short}" if prefix else short


def now_iso() -> str:
    """Current timestamp as ISO-8601 (created_at columns)."""
    return datetime.now().isoformat(timespec="seconds")


def today_iso() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Generic insert / upsert helpers (fetch-before-write)
# ---------------------------------------------------------------------------

def insert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    """INSERT one row from a dict of column -> value."""
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        list(row.values()),
    )


def upsert_by_id(conn: sqlite3.Connection, table: str, row: dict) -> str:
    """Insert if the row's id is absent, else replace it. Idempotent seeding.

    `row` must contain an `id`. Returns the id.
    """
    rid = row["id"]
    exists = conn.execute(
        f"SELECT 1 FROM {table} WHERE id = ?", (rid,)
    ).fetchone()
    if exists:
        sets = ", ".join(f"{c} = ?" for c in row if c != "id")
        params = [v for c, v in row.items() if c != "id"] + [rid]
        conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", params)
    else:
        insert(conn, table, row)
    return rid


def count(conn: sqlite3.Connection, table: str, where: str = "", params: tuple = ()) -> int:
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return conn.execute(sql, params).fetchone()[0]
