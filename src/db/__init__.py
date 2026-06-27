"""Local SQLite data layer — the system of record (replaces notion_writer.py).

Phase 1c: schema stand-up + spine seed. See docs/decision-I-sqlite-schema.md
(authoritative physical spec) and docs/health-agent-design.md (architecture).
"""
from src.db.store import connect, new_id
from src.db.schema import init_db

__all__ = ["connect", "new_id", "init_db"]
