"""Seed the spine: 8 goal pages + 36 sub-targets (+ a placeholder admin user).

Idempotent — re-running upserts by id. Run after init_db():
    python -m src.db.seed
"""
import logging

from src.db.schema import init_db
from src.db.seed_data import GOAL_PAGES, SUB_TARGETS
from src.db.store import connect, count, now_iso, upsert_by_id

log = logging.getLogger(__name__)


def seed_goal_pages(conn) -> int:
    for g in GOAL_PAGES:
        upsert_by_id(conn, "goal_pages", g)
    conn.commit()
    return len(GOAL_PAGES)


def seed_sub_targets(conn) -> int:
    created = now_iso()
    for st in SUB_TARGETS:
        row = dict(st)
        row["created_at"] = created
        upsert_by_id(conn, "sub_targets", row)
    conn.commit()
    return len(SUB_TARGETS)


def seed_admin(conn) -> None:
    """Seed a placeholder admin user. password_hash is empty (cannot log in) until
    Flask auth is wired and a real password is set. candidates.decided_by points here."""
    existing = conn.execute("SELECT 1 FROM users WHERE username = 'matt'").fetchone()
    if existing:
        return
    upsert_by_id(conn, "users", {
        "id": "user_matt", "username": "matt", "password_hash": "",
        "role": "admin", "created_at": now_iso(),
    })
    conn.commit()


def seed_all(conn) -> None:
    seed_goal_pages(conn)
    seed_sub_targets(conn)
    seed_admin(conn)


def validate(conn) -> list[str]:
    """Structural checks on the seeded spine. Returns a list of problems (empty = OK)."""
    problems = []

    n_goals = count(conn, "goal_pages")
    if n_goals != 8:
        problems.append(f"goal_pages: expected 8, got {n_goals}")

    n_st = count(conn, "sub_targets")
    if n_st != 36:
        problems.append(f"sub_targets: expected 36, got {n_st}")

    # composition
    n_goal_area = count(conn, "sub_targets", "ndis = 1")
    if n_goal_area != 25:
        problems.append(f"goal-area (ndis=1) sub-targets: expected 25, got {n_goal_area}")

    n_benched = count(conn, "sub_targets", "current_benchmark IS NOT NULL")
    if n_benched != 25:
        problems.append(f"benchmarked sub-targets: expected 25, got {n_benched}")

    n_adjacent = count(conn, "sub_targets", "status = 'Adjacent-watch'")
    if n_adjacent != 3:
        problems.append(f"Adjacent-watch sub-targets: expected 3, got {n_adjacent}")

    # every sub-target points at a real goal
    orphans = conn.execute(
        "SELECT s.id FROM sub_targets s LEFT JOIN goal_pages g ON s.goal_id = g.id WHERE g.id IS NULL"
    ).fetchall()
    if orphans:
        problems.append(f"sub-targets with missing goal: {[r[0] for r in orphans]}")

    # benchmarked rows must carry an as-of date
    bad_dates = count(conn, "sub_targets",
                      "current_benchmark IS NOT NULL AND benchmark_as_of IS NULL")
    if bad_dates:
        problems.append(f"benchmarked rows missing benchmark_as_of: {bad_dates}")

    # Safety-critical flag is on dysphagia
    sc = conn.execute(
        "SELECT id FROM sub_targets WHERE severity = 'Safety-critical'"
    ).fetchall()
    if [r[0] for r in sc] != ["st_dysphagia_airway"]:
        problems.append(f"Safety-critical rows: expected [st_dysphagia_airway], got {[r[0] for r in sc]}")

    return problems


def _summary(conn) -> None:
    n_goals = count(conn, "goal_pages")
    n_total = count(conn, "sub_targets")
    n_goal_area = count(conn, "sub_targets", "ndis = 1")
    n_benched = count(conn, "sub_targets", "current_benchmark IS NOT NULL")
    n_adjacent = count(conn, "sub_targets", "status = 'Adjacent-watch'")
    n_active = count(conn, "sub_targets", "status = 'Active'")
    n_medical = count(conn, "sub_targets", "goal_id = 'goal_medical'")
    print(f"  goal_pages         : {n_goals}")
    print(f"  sub_targets total  : {n_total}")
    print(f"    ndis=1 (goal-area): {n_goal_area}")
    print(f"    benchmarked       : {n_benched}")
    print(f"    Adjacent-watch    : {n_adjacent}")
    print(f"    Active            : {n_active}")
    print(f"    medical           : {n_medical}")
    print("  per goal:")
    for r in conn.execute(
        "SELECT g.title, COUNT(s.id) n FROM goal_pages g LEFT JOIN sub_targets s "
        "ON s.goal_id = g.id GROUP BY g.id ORDER BY g.category, g.title"
    ).fetchall():
        print(f"    {r['title']:<26} {r['n']}")


if __name__ == "__main__":
    conn = connect()
    init_db(conn)
    seed_all(conn)
    print("Seeded spine:")
    _summary(conn)
    problems = validate(conn)
    if problems:
        print("\nVALIDATION FAILED:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("\nOK — spine validates (8 goals, 36 sub-targets, 25 benchmarked).")
    conn.close()
