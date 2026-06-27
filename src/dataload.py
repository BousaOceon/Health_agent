"""Phase 1d historical data load — the direct file feed (NOT the Phase-2 email
ingestion backfill; see design §8.3).

Two passes, exploiting assessment-behind-the-gate (extraction is order-independent):
  1. extract_folder  — extract every file -> UNASSESSED draft, in any order.
                       Resumable + de-duplicated on the file path (source_ref).
  2. confirm_oldest_first — confirm drafts sorted by their extracted date, so
                       benchmarks advance sequentially (Pass 1 -> Pass 2 -> candidates).

Between the two, review dates_to_confirm() — drafts where extraction could not
find a clear appointment date — and fix them before confirming.

CLI:
  python -m src.dataload <folder>          # pass 1: extract all to drafts
  python -m src.dataload --status          # counts + dates needing attention
  python -m src.dataload --confirm         # pass 2: confirm oldest-first
  python -m src.dataload <folder> --limit 5   # extract just the first 5 (smoke test)
"""
import argparse
import json
import logging
import sys
from pathlib import Path

from src import pipeline
from src.db.store import connect
from src.extract import SUPPORTED_SUFFIXES, prepare_file

log = logging.getLogger(__name__)


def list_files(folder) -> list[Path]:
    return sorted(p for p in Path(folder).rglob("*")
                  if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)


def _already_ingested(conn, source_ref: str):
    return conn.execute("SELECT id FROM appointments WHERE source_ref=?", (source_ref,)).fetchone()


def extract_folder(conn, folder, *, call=None, limit=None) -> dict:
    """Pass 1 — extract every supported file to a draft. Skips files already ingested."""
    files = list_files(folder)
    if limit:
        files = files[:limit]
    result = {"ingested": [], "skipped": [], "errors": []}
    for p in files:
        ref = str(p.resolve())
        if _already_ingested(conn, ref):
            result["skipped"].append(p.name)
            continue
        try:
            content, sources = prepare_file(p)
            appt_id, _ = pipeline.ingest_content(
                conn, content, backfill=1, source_email="Backfill",
                source_ref=ref, content_sources=sources, call=call)
            result["ingested"].append((p.name, appt_id))
            log.info("ingested %s -> %s", p.name, appt_id)
        except Exception as e:
            log.error("data-load extract failed for %s: %s", p.name, e)
            result["errors"].append((p.name, str(e)))
    return result


def dates_to_confirm(conn) -> list:
    """Backfill drafts with no usable appointment date — fix before confirming."""
    return conn.execute(
        "SELECT id, source_ref FROM appointments "
        "WHERE backfill=1 AND status='draft' AND (appointment_date IS NULL OR appointment_date='')"
    ).fetchall()


def confirm_oldest_first(conn, *, call=None, summarize=None) -> list:
    """Pass 2 — confirm dated backfill drafts oldest-first; each runs Pass 1 + Pass 2."""
    drafts = conn.execute(
        "SELECT id, appointment_date FROM appointments "
        "WHERE backfill=1 AND status='draft' AND appointment_date IS NOT NULL AND appointment_date!='' "
        "ORDER BY appointment_date, id"
    ).fetchall()
    out = []
    for d in drafts:
        res = pipeline.confirm_report(conn, d["id"], call=call, summarize=summarize, backfill=1)
        out.append({"id": d["id"], "date": d["appointment_date"],
                    "benchmark_candidates": len(res["candidates"]),
                    "strategy_candidates": len(res.get("strategy_candidates", []))})
        log.info("confirmed %s (%s): %d benchmark + %d strategy candidates",
                 d["id"], d["appointment_date"], len(res["candidates"]),
                 len(res.get("strategy_candidates", [])))
    return out


def status(conn) -> dict:
    def c(where):
        return conn.execute(f"SELECT COUNT(*) FROM appointments WHERE {where}").fetchone()[0]
    return {
        "drafts": c("backfill=1 AND status='draft'"),
        "confirmed": c("backfill=1 AND status='confirmed'"),
        "dates_to_confirm": len(dates_to_confirm(conn)),
        "pending_candidates": conn.execute("SELECT COUNT(*) FROM candidates WHERE status='pending'").fetchone()[0],
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Phase 1d historical data load")
    ap.add_argument("folder", nargs="?", help="folder of report files to extract")
    ap.add_argument("--confirm", action="store_true", help="confirm drafts oldest-first")
    ap.add_argument("--status", action="store_true", help="show data-load status")
    ap.add_argument("--limit", type=int, help="extract only the first N files")
    args = ap.parse_args()

    conn = connect()
    try:
        if args.status:
            print(json.dumps(status(conn), indent=2))
        elif args.confirm:
            print("Confirming drafts oldest-first...")
            for r in confirm_oldest_first(conn):
                print(f"  {r['date']}  {r['id']}  +{r['benchmark_candidates']}bm +{r['strategy_candidates']}strat")
        elif args.folder:
            print(f"Extracting {args.folder} ...")
            r = extract_folder(conn, args.folder, limit=args.limit)
            print(f"  ingested: {len(r['ingested'])}  skipped: {len(r['skipped'])}  errors: {len(r['errors'])}")
            for name, err in r["errors"]:
                print(f"    ERROR {name}: {err}")
            need = dates_to_confirm(conn)
            if need:
                print(f"  {len(need)} draft(s) need a date before confirming (see --status).")
        else:
            ap.print_help()
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
