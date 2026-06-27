# Health Agent – Claude Code Context

This file is read at the start of every Claude Code session. It is a **lean operational pointer**, not a design document — the architecture, schema, and engine live in `docs/` (see Source of Truth). Keep this file short; do not duplicate the design docs into it.

Update this file at the end of each phase: mark the phase done, note anything that deviated, record conventions or gotchas discovered, then add the next phase steps.

---

## What This Project Does

A personal health coordination agent running on a Raspberry Pi. It ingests appointment reports and notes from two Gmail accounts, maintains a structured health knowledge base in a **local SQLite database on the Pi** (the system of record), and produces pre-appointment briefs, weekly digests, framework-projected reporting (NDIS annual + Victorian school DIP review), an interactive performance review, and a natural-language query interface over the full health record. A **local Flask dashboard** is the primary control and review UI on the home network. A **nightly off-box SQLite backup** is the disaster-recovery line (day one, non-negotiable). Notion is **no longer the data store** — its only optional, deferred role is a one-way mirror of generated reports.

The system is organised around the **sub-target as the spine** (36 fixed rows). Appointments are evidence; goals, the NDIS plan, the DIP, and SSG are *projections* of the same observations through different lenses.

**Primary user:** Matt (owner/operator). **Secondary user:** Louise (receives digests/briefs by email; no dashboard access required; can trigger actions via email subject patterns). **Subject:** Tom (7, born Dec 2018) — multiple allied-health providers, on the NDIS. See the Standing Extraction Context and the static Health Summary.

---

## Source of Truth

Two documents in `docs/` are the durable source of truth. Read them before working on the outcome layer:

- **`docs/health-agent-design.md`** — conceptual/architectural reference: three-layer model, the sub-target spine, fan-out, the two-pass assessment engine behind the confirmation gate, strategies, frameworks-as-projections, brief/query/reporting, build phases.
- **`docs/decision-I-sqlite-schema.md`** — the **physical build spec**: full SQLite DDL, the Candidates table, the change-log spine, the one-cascade/three-triggers gated-change engine, the three-tier edit map, the four correction cases, typed override-capture.
- **`docs/handoff-phase-1c.md`** — the transient brief that drove this CLAUDE.md rework + Phase 1c kickoff. Archive once 1c is underway.

**Authority rule:** for any physical schema question, `decision-I-sqlite-schema.md` wins. For architecture/rationale, `health-agent-design.md`. This file (CLAUDE.md) is operational pointer only. Where the design doc's per-field tables and the schema doc differ, the schema doc is authoritative for the build.

---

## Repository Structure

Front half retained as-is; the data layer and engine are new. Finalise exact module names as the 1c/1d build lands.

```
/health-agent/
├── CLAUDE.md                  # This file
├── requirements.txt
├── docs/                      # Source-of-truth design docs (above)
├── config/
│   └── settings.yaml          # All configuration + prompts; single source of truth
├── .env                       # Secrets – never commit (repo root, loaded by src/config.py)
├── data/                      # SQLite DB lives here (health.db); off-box backup target
├── inbox/  processed/  logs/  # Attachment staging, archive, metadata-only logs
└── src/
    ├── config.py              # Loads .env + settings.yaml (RETAINED)
    ├── extract.py             # Content routing, OCR, Claude extraction (RETAINED front half)
    ├── db/                    # NEW data layer (replaces notion_writer.py)
    │   ├── schema.py          #   DDL, PRAGMA foreign_keys, append-only triggers, migrations
    │   ├── store.py           #   CRUD / queries; fetch-before-write discipline
    │   └── providers.py       #   provider matching (lifted out of notion_writer.py)
    ├── dashboard/             # Flask app; Candidates review page is day-one (Phase 1c)
    │   ├── app.py  routes.py  templates/  static/
    │   └── ...
    # --- Built in later phases (1d/2/4+): ---
    # pass1_assess.py (Haiku grade at confirmation), pass2_reconcile.py (pure logic),
    # cascade.py (the gated-change engine), ingest.py (Gmail, Phase 2),
    # brief_generator.py, digest_generator.py, archiver.py, email_sender.py,
    # scheduler.py, query_engine.py, session_writeback.py, ndis_report.py
```

**`notion_writer.py` is retired** (git keeps history). Its Notion write-path is gone; its provider-matching *rules* move to `src/db/providers.py`. If the optional Notion report-mirror is ever built, it is a new, write-scoped, reports-only module — never the engine's data path.

---

## Environment & Secrets

All secrets in `.env` (repo root) — never hardcode or commit. Loaded by `src/config.py`.

```
ANTHROPIC_API_KEY=
NOTION_API_KEY=                       # OPTIONAL – only for the deferred report-mirror
GMAIL_PRIMARY_CREDENTIALS=config/gmail_primary_token.json
GMAIL_SECONDARY_CREDENTIALS=config/gmail_secondary_token.json
GMAIL_PRIMARY_ADDRESS=
GMAIL_SECONDARY_ADDRESS=
OUTBOUND_EMAIL_PRIMARY=
OUTBOUND_EMAIL_SECONDARY=
```

SQLite path and backup target live in `settings.yaml` (`db_path`, backup config), not `.env`.

---

## settings.yaml Structure

Single source of truth; prompts read at runtime, never hardcoded in `src/`. Finalise exact keys against the 1c build. Shape:

```yaml
db_path: data/health.db
backup:                               # nightly off-box SQLite backup (day one)
  target: ""                          # off-box path/destination
  time: "02:00"

polling_interval_hours: 4
brief_lead_time_hours: 48
brief_scope_window_months: 6          # single-provider brief working-set window (design §14)
weekly_digest_day: saturday
weekly_digest_time: "07:00"
brief_generation_day: sunday
brief_generation_time: "07:00"
bridge_task_when: "2. Monday"

features:                             # checked at runtime, not import time
  email_polling: false
  stage_2_detection: false
  pre_appointment_briefs: false
  weekly_digest: false
  performance_review: false
  backfill_mode: false                # historical data load (1d) / ingestion backfill (Phase 2)
  query_interface: false
  session_writebacks: false
  ndis_query_report: false

known_sender_emails: []
known_sender_domains: []
keyword_phrases: []

# --- Prompts (all editable here; never hardcode in src/) ---
extraction_context: |                 # static Tom baseline; injected every extraction
extraction_prompt: |                  # fan-out + attribution + self-review → UNASSESSED shells.
                                      # Does NOT assess and does NOT inject benchmarks.
                                      # ###PLACEHOLDER### substitution, not .format()
assessment_prompt: |                  # NEW – Haiku, Pass 1 at confirmation; injects touched
                                      # sub-targets' benchmarks + as-of, grades Lower/At/Above/Gap/Adjacent
benchmark_update_prompt: |            # Haiku; structure-preserving; operates on the Sub-targets
                                      # table (not goal rich-text); receives ###APPOINTMENT_DATE###
stage_2_prompt: |
query_system_prompt: |
# add prompts as the engine needs them (candidate reason-summary, goal roll-up digest, etc.)

# notion_mirror:  (deferred — returns only if the one-way report mirror is built)
```

**The `notion:` system-of-record block is removed.** Database identity now lives in SQLite, not Notion DB IDs.

---

## The Data Model (pointer — full DDL in `docs/decision-I-sqlite-schema.md`)

Do **not** duplicate DDL here. One-line table list:

| Layer | Tables |
|---|---|
| **Evidence** | `appointments` (encounters; Providers link is authoritative for retrieval; `sub_targets_touched`, `content_sources`, `flags`) |
| **Spine** | `sub_targets` (the working unit; benchmark + as-of; goal/dip/ndis-outcome/ssg tags; `scope_line`; `severity`) |
| **Benchmark lane** | `findings` (fan-out parent; constant `source_fragment`) → `observations` (sub-target-anchored, assessed; `severity_screen`, `graded_against_benchmark_id`) |
| **Strategy lane** | `strategies` (one row per component) → `strategy_observations` (running log) |
| **Change-log spine** | `benchmark_change_log`, `strategy_change_log` (append-only, trigger-enforced) |
| **Gate** | `candidates` (one typed table; `change_class`; grouped by sub-target in review) |
| **Roll-up** | `goal_pages` (6 NDIS + Medical + Other; roll-up view; Supporting Providers **derived**, not stored) |
| **Reused** | `health_actions` (re-anchored to sub-target + strategy), `providers`, archive |
| **App-infra/audit** | `users` (admin/carer), `recompute_audit` (cascade ripple trail) |

Static, not a table: **Health Summary** (curated local document — biography/diagnoses/what-works).

---

## The Entry Flow (most important behavioural change vs old design)

**Assessment lives behind the confirmation gate.** Extraction no longer grades; benchmarks are no longer injected at extraction.

1. **Extraction (Sonnet, at ingestion)** — fan-out + per-sub-target materiality + attribution + strategy-vs-noise + self-review → writes **unassessed observation shells** (`assessment = NULL`), findings, strategy-obs shells, actions, appointment (`status='draft'`), and `self_review` → `flags`. Severity screen on Medical findings is set here (drives the immediate safety alert, independent of grading).
2. **Draft review** — user edits facts, fixes attribution, retracts junk. Nothing derived exists yet, so facts edit freely and draft retraction is trivial.
3. **On confirmation → Pass 1 (Haiku)** grades the shells against each touched sub-target's benchmark as-of the observation date (scoped to touched sub-targets only — that is where `###...BENCHMARKS###` injects now). Same `assess()` the cascade reuses.
4. **Pass 2 (pure logic)** aggregates dated grades per touched sub-target → proposes benchmark changes as **candidates** (never auto-applied).
5. **Candidate gate** — all derived-value changes (benchmark/strategy/assessment corrections, promotions, spin-outs) route through the one typed `candidates` table and the **one cascade / three triggers** (data-load advance · live correction · confirmed-report retraction). See schema doc §1–§5.

**Do not reintroduce:** a benchmark at extraction, a two-tier Goal Progress Note, a Lead Provider field, or a Notion write-path for engine data.

---

## Standing Extraction Context (injection wiring — design §9.1)

Five inputs injected per extraction call, `###PLACEHOLDER###` substitution (not `.format()` — JSON braces in the prompt body):

- `###EXTRACTION_CONTEXT###` — static Tom baseline (from settings.yaml). Tom is 7 (born Dec 2018): Chromosome 18p deletion, mosaic Trisomy 13, **ASD Level 2 – Requiring Substantial Support (diagnosed May 2026)**, hypotonia, **dysphagia with choking risk + modified diet**, low processing speed (borderline), borderline visual-spatial, strong visual working memory. **Grade 1** at South Geelong Primary with Education Support. ASD-profile behaviours (routine reliance, transition distress, scripted/repetitive language, sensory sensitivities, atypical interoception) are **established baseline** — not new findings/regressions. Adult prompting/support is baseline; progress = assisted→independent, generalisation, or sustained unprompted demonstration.
- `###SUBTARGET_ROUTING_LIST###` — each sub-target's title + `scope_line` (+ goal), **no benchmarks** — enough to route a fact to the right sub-target(s).
- `###PROVIDER_LIST###` — canonical Title + Aliases + Type (primary defence for provider matching).
- `###ACTIVE_STRATEGY_TITLES###` — thin active-component titles + sub-targets (recognise status language; do not resolve component).
- `###REPORT_TEXT###` — output of `prepare_content()`.

Plus `###TODAY###` and `###APPOINTMENT_DATE###` (recorded on every shell; the date Pass 1 judges against).

Benchmarks inject **later**, at Pass 1 (`assessment_prompt`, Haiku), scoped to touched sub-targets only.

---

## Provider Matching (now in `src/db/providers.py`)

Rules unchanged from Phase 1b (validated on the FSSP record); only the home moves off `notion_writer.py`:

1. **Split combined-name strings** on commas / "and" / "&" before any matching. Never create a provider from a combined string.
2. **Normalise then fuzzy match**: case-insensitive, strip titles (Dr/Mr/Ms), trim, partial substring.
3. **Check Aliases**, not just Title (nicknames like "Maddy" aren't substrings of "Madelaine").
4. **Primary defence is at extraction** — the canonical provider list is injected so the model resolves names before the matcher runs; fuzzy + alias is the backstop.
5. No match + auto-create enabled → create with available fields + a `flags_for_review` entry for manual completion. Never auto-create a combined-name record.

---

## Email Subject Pattern Detection (Phase 2)

Runs before sender detection; works from either inbox. `FORCE INGEST` + attachment → force ingest. `FORCE BRIEF – [Provider] – [Date]` → generate brief now. `NDIS REPORT YYYY-MM-DD YYYY-MM-DD` → generate report for range.

---

## Content Extraction Pipeline (RETAINED — `extract.py`)

All sources route through `prepare_content()`; Claude always receives clean labelled text. Native PDF → pdfplumber; scanned PDF → pdfplumber quality check then pytesseract+Pillow; image → pytesseract+Pillow; docx → python-docx; email body → BeautifulSoup; thread → per-message with sender/date labels. OCR quality check re-routes a low-density "native" PDF to Tesseract. Story Champs–style skills tables: if column structure is uncertain in raw text, the prompt instructs Claude to describe what was observed rather than assert a column (Independent = stronger evidence than Benefits-from-Assistance).

---

## Model Assignments (full table — design §20)

Latest version of each tier; never hardcode version strings. Highlights: **Sonnet** = extraction (+fan-out/attribution/self-review), pre-appointment brief, weekly digest, query synthesis, NDIS/DIP report. **Haiku** = Pass 1 assessment, strategy set-diff, promotion clustering, candidate reason-summary, benchmark/strategy update on approval, goal roll-up, Stage 2 detection, query planning, session write-back. **Pure logic, no Claude** = Pass 2 (regression/progression/addition), staleness, archive eligibility.

---

## Coding Conventions

- All writes/inserts check for an existing row first (deduplication).
- Derived/gated values are **never raw-edited** — corrections route through the candidate gate; change logs are append-only (trigger-enforced). See the three-tier edit map in the schema doc.
- All Claude API calls in try/except; errors → `logs/` (metadata only — never report text, names, or clinical content).
- settings.yaml is the single source of truth — no magic strings in `src/`.
- Prompts live in settings.yaml, read at runtime — never hardcoded.
- Extraction prompt injection uses `###PLACEHOLDER###` substitution, never `.format()`/f-strings (JSON braces in prompt body).
- Gmail OAuth tokens in `config/` — in `.gitignore`.
- Each module independently runnable with an `if __name__ == "__main__"` test block.
- Dashboard routes must not block — long-running tasks (Claude API, bulk DB reads) run async / background thread.
- Feature flags checked at runtime, not import time.

---

## Build History (preserved — the irreplaceable part of this file)

**Phase 1 – Foundations ✓ COMPLETE (2026-05-30).** Full pipeline proven end-to-end on one real report; tested on 3 (individual OT note, speech group session, multi-provider FSSP). venv + deps; Gmail primary OAuth; Notion connectivity (front-half era); native-PDF extraction; Claude extraction returning structured data; record creation with correct relations.

Phase 1 deviations — **live** ones still relevant:
- `notion-client` v3 removed `.query()` → pinned v2.2.1 (now mirror-only relevance).
- Tesseract path: was hardcoded to the Windows install; **fixed on Pi migration** to use PATH with a Windows fallback (`extract.py`).
- Extraction prompt braces require `###PLACEHOLDER###` substitution, not `.format()`.
- Provider-matching combined-name bug (`"Kerry Britt, Madelaine Tomlin, Sally Barnard"` → one junk record) → **fixed in 1b**.

Phase 1 deviations — **historical, resolved by the SQLite rebuild** (no longer live gotchas): the Notion `Appointement Date` typo; `Detail`=`Notes`; `Observation`=`Note`; the rich_text 2000-char limit / page-body raw-notes workaround. Clean column names under SQLite.

**Phase 1b – Extraction Refinements ✓ COMPLETE (2026-06-14).** Provider-matching fix (validated on FSSP — 3 providers correctly split/linked); `extract.py` reads `extraction_prompt` from settings.yaml and injects placeholders; raw notes to page body; self_review → Flags. The **differential+temporal two-tier goal-notes model it validated is now SUPERSEDED** by the outcome layer (sub-target-anchored observations). The *extraction / provider-matching / OCR* parts of that validation still stand; the *goal-note* parts are obsolete. Validation outcomes (kept as front-half quality record): FSSP 6→2 candidates; OT home visit 1 note; Story Champs 1 note.

**Pi migration ✓ (2026-06-27).** Moved dev from Windows to the Pi (Debian 13 trixie, Python 3.13). Created `venv/`, installed all deps from binary wheels (pdfplumber needs no `libpoppler-cpp-dev`; Pillow needs no `libjpeg-dev`; `poppler-utils` already present for pdf2image; added `pdf2image` to requirements). Installed `tesseract-ocr` 5.5.0. Moved `.env` to repo root. Fixed the Windows-only Tesseract path. Config + secrets load verified.

---

## Current Build Phase

**Phase 1c – Stand up the SQLite store (structure + seed). ✓ COMPLETE (2026-06-27)**

- [x] `data/health.db` + all 14 outcome-layer tables per the schema DDL — append-only change-log triggers, `CHECK` constraints, indexes, FK on, `users` + `recompute_audit`. (`src/db/schema.py`)
- [x] `src/db/` package (schema.py, store.py, providers.py); provider-matching migrated to `providers.py`. (`notion_writer.py` left in place but superseded — see deviations.)
- [x] Health Actions re-anchored to sub-target; `appointments` has `sub_targets_touched` + `content_sources`.
- [x] **36-row spine seeded + validated** (`src/db/seed_data.py`, `seed.py`): 8 goal pages, 36 sub-targets, 25 benchmarked @ 2026-06-13, 3 Adjacent-watch Other rows, Sleep + Dysphagia + 4 medical gap-blanks seeded blank. 11 providers migrated from Notion; matching verified.
- [x] Day-one **Flask Candidates review page** (`src/dashboard/`, grouped by sub-target, inline approve/reject + typed reason) + **nightly backup** (`src/backup.py`).
- [x] No MCP in the engine — local SQLite only. (Notion MCP was used once to *pull seed data*; the running code has zero MCP.)

**Phase 1c deviations & decisions:**
- **`benchmark_change_log` is NOT seeded in 1c.** The 13/06 benchmark lives on `sub_targets.current_benchmark`/`benchmark_as_of`. Both change-log anchors (FSSP Baseline + 13/06) are written in **1d** so the append-only log stays chronologically correct (avoids a double-Baseline). FSSP Baseline deferred to start of 1d (agreed).
- **`ndis_outcome_domain` seeded NULL for all 36 rows.** Decision A resolved NDIS-goal + DIP + SSG only; the NDIS Outcomes Framework tag is a later projection task (needed before NDIS-outcome-projected reporting, not before 1d).
- **Carved benchmarks:** the 5 setting-split carves use the fuller 13/06 Notion text as `current_benchmark` and the Decision-A split wording as `scope_line`; the 3 behaviour carves use the Decision-A carved text (no separate Notion line existed). (Agreed approach.)
- **Title prefixes dropped** — titles stand alone; grouping is by tag (goal/DIP/SSG), per design §3.2.
- **`notion_writer.py` + `test_pipeline.py` (old Notion path) left in place, superseded.** Provider-matching is already migrated to `src/db/providers.py`; physically deleting them + rewriting `test_pipeline.py` for SQLite is folded into the 1d pipeline build (which replaces test_pipeline anyway). Nothing in `src/db/` imports them.
- **Candidate approve/reject in 1c records the decision (lifecycle + typed reason) only** — applying the change (mutation + cascade) is wired in 1d.

**Phase 1c did NOT include** the engine logic (Pass 1/Pass 2/cascade), the data load, or ingestion — those are 1d and Phase 2.

**Run it:** `python -m src.db.seed` (build + seed + validate) · `python -m src.dashboard.app` (dashboard at localhost:5000; add `--host=0.0.0.0` on the Pi) · `python -m src.backup` (snapshot).

**Then:** Phase 1d (engine + historical data load, two-anchored, oldest-first), Phase 2 (Gmail ingestion + ingestion backfill), Phase 3 (end-to-end validation + write Health Summary), Phase 4 (outputs + dashboard core), Phase 5 (performance loop + cron), Phase 6 (query + write-back). See design §21.

---

**Phase 1d — Part A: the engine ✓ COMPLETE (2026-06-27); Parts B/C pending Matt's data**

The full entry-flow engine is built and unit-tested (62 tests, all stubbed — no live Claude calls yet). Modules:
- `src/claude.py` — model ids (from `settings.models`) + the `call()` seam (mockable).
- `src/extract.py` — `extract_report` rewired to the new injection set; emits UNASSESSED shells.
- `src/engine/injection.py` — routing list / provider list / active strategies / Pass-1 benchmarks from SQLite.
- `src/engine/persist.py` — extraction → DRAFT (appointment + findings + shells + strategy-obs + actions + `appointment_providers`).
- `src/engine/pass1.py` — `assess()` (atomic, shared with cascade) + `grade_appointment()` (Haiku, at confirmation).
- `src/engine/pass2.py` — reconciliation (pure logic): Progression/Regression/Addition candidates, gate-tight + idempotent.
- `src/engine/benchmark.py` — change-log + `governing_benchmark_version` (C10 version key, rowid tie-break) + `seed_baseline`.
- `src/engine/cascade.py` — version-gated recompute + Pass 2 delta + `recompute_audit`.
- `src/engine/apply.py` — `apply_candidate` (benchmark-change/-correction, assessment-correction, adjacent-promotion, spin-out, strategy-diff, strategy-status-correction) + `reject_candidate`.
- `src/engine/strategy.py` — set-diff (match → status_read → strategy-diff candidates) + strategy change-log.
- `src/engine/summarize.py` — Haiku benchmark-text summarizer (fills candidate `to_value`).
- `src/engine/safety.py` — capture-time Safety alert (fires at ingest, pluggable notifier).
- `src/pipeline.py` — `ingest_content` (extract → draft → safety screen) + `confirm_report` (Pass 1 → Pass 2 → set-diff).
- Dashboard approve/reject now **apply** via the engine.

**Part A deviations & decisions:**
- **Schema gap fixed:** added `appointment_providers` join table (the authoritative all-attendees multi-relation; schema-doc DDL had omitted it). Plus `candidates.change_type` (additive migration).
- **Prompts are first DRAFTS** in settings.yaml (extraction_prompt rewritten; assessment_prompt new; benchmark_update_prompt now per-sub-target; `ndis_sub_targets` removed; `models:` block added). Marked `[DRAFT]` — to be refined in Matt's prompt-design session + tuned against real reports during the load.
- **No live Claude calls yet** — every test stubs the `claude.call` seam. First real calls are the Part C data load.
- `notion_writer.py` + `test_pipeline.py` deleted (superseded Notion path).

**Engine tests:** `python -m src.engine.test_pass2` (11) · `test_gate` (14) · `test_pass1` (10) · `test_entry_flow` (14) · `test_strategy` (13).

**Part B (two-anchored seeding) + Part C (data load) need Matt's four data items:** the ~20 historical reports, the FSSP report, the 6 blank Active benchmarks (Sleep / Dysphagia / Continence / Gastro / Dental / Growth), and the current active strategy-inventory draft.

---

## Likely Sticking Points (finalise specifics during 1c)

- **`assess()` is a Haiku call, not pure logic.** The cascade's recompute is **version-gated** (`observations.graded_against_benchmark_id`): re-grade only when the governing benchmark *version* (a change-log id, not the as-of date) moves, so a cascade over an unchanged sub-target makes zero LLM calls and stays idempotent. Pure-logic idempotency is a Pass-2 property only.
- **Two-anchored seeding** writes `benchmark_change_log` Baseline + latest-confirmed entries directly (`confirmed_by='Matt-approved'`, `candidate_id` NULL) — seeding does not go through the candidate gate.
- **Candidates page in 1c has no live producer** — the cascade that fills it is 1d. Build the table + page + manual approve/reject in 1c; full validation comes with the 1d data load.
- **Forward FK references** in the DDL (e.g. `benchmark_change_log.candidate_id` → `candidates`) are fine in SQLite (resolved at insert, not create) — create all tables in one script.
- **OCR quality** on scanned PDFs — add Pillow pre-processing (greyscale/contrast/resize) if Tesseract output is garbled.
- **Dashboard blocking** — Flask dev server is single-threaded; any route calling Claude or doing bulk DB reads must thread/async.
- **Gmail OAuth (Phase 2)** — token files from Windows are reusable; browser auth done on laptop, copy `config/` across. Already on the Pi.
