"""Nightly off-box SQLite backup (Phase 1c, day-one disaster-recovery line).

Uses SQLite's online backup API for a consistent snapshot even if the DB is in
use, writes a timestamped copy to settings.backup.target (falls back to a local
backups/ dir with a warning if the off-box target is unset), and prunes to the
most recent KEEP files.

    python -m src.backup
"""
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from src.config import settings
from src.db.store import db_path

log = logging.getLogger(__name__)

KEEP = 14  # retain the most recent N backups


def backup_dir() -> tuple[Path, bool]:
    """Return (destination dir, off_box). Falls back to repo-local backups/ if unset."""
    target = (settings.get("backup", {}) or {}).get("target", "") or ""
    if target.strip():
        return Path(target).expanduser(), True
    return db_path().resolve().parents[1] / "backups", False


def run_backup() -> Path:
    src = db_path()
    if not src.exists():
        raise FileNotFoundError(f"No database to back up at {src} — run `python -m src.db.seed` first.")

    dest_dir, off_box = backup_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not off_box:
        log.warning("backup.target not set in settings.yaml — writing LOCAL backup to %s "
                    "(not off-box; set backup.target before go-live).", dest_dir)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"health-{stamp}.db"

    source = sqlite3.connect(str(src))
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)          # consistent online snapshot
        finally:
            target.close()
    finally:
        source.close()

    _prune(dest_dir)
    log.info("Backup written: %s (%d bytes)", dest, dest.stat().st_size)
    return dest


def _prune(dest_dir: Path) -> None:
    backups = sorted(dest_dir.glob("health-*.db"))
    for old in backups[:-KEEP]:
        old.unlink()
        log.info("Pruned old backup: %s", old.name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        dest = run_backup()
        dest_dir, off_box = backup_dir()
        print(f"Backed up to {dest}")
        print("OFF-BOX: yes" if off_box else "OFF-BOX: NO — set backup.target in settings.yaml before go-live")
    except Exception as e:
        print(f"Backup FAILED: {e}", file=sys.stderr)
        sys.exit(1)
