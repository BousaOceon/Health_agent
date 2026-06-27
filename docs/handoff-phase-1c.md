# Handoff Brief — CLAUDE.md Rework + Phase 1c Kickoff

**For:** Claude Code (Health Agent repo)
**From:** design work in the Claude.ai project, 27/06/2026
**Purpose:** Bring the repo `CLAUDE.md` up to date with the goal-centric redesign and the SQLite/gated-change decisions, then begin Phase 1c. This brief is transient — once `CLAUDE.md` is reworked and the design docs are in the repo, it can be archived.

---

## 0. Read these first (they are the source of truth)

Two design documents are the durable source of truth for architecture, schema, prompts, and phases. **Add both to the repo** (e.g. `/docs/`) and read them before doing anything else:

- **`health-agent-design.md`** — conceptual/architectural reference: the three-layer model, the sub-target spine, fan-out, the two-pass assessment engine (now behind the confirmation gate), strategy inventory, frameworks-as-projections, brief/query/reporting, build phases. Updated 27/06/2026.
- **`decision-I-sqlite-schema.md`** — the **physical build spec**: full SQLite DDL, the Candidates table, the change-log spine, the one-cascade/three-triggers gated-change engine, the three-tier edit map, the four correction cases, typed override-capture. Draft 3, 27/06/2026.

**Authority rule:** for any physical schema question, `decision-I-sqlite-schema.md` wins. For architecture/rationale, `health-agent-design.md`. `CLAUDE.md` becomes a *lean operational pointer* to these — not a duplicate of them.

This brief does **not** restate the design. It tells you what changed since the current `CLAUDE.md`, what to preserve, and how to rework the file.

---

## 1. The one-paragraph picture of what changed

The project pivoted from an **encounter-spine, Notion-backed, two-tier-Goal-Progress-Notes** design to a **sub-target-spine, local-SQLite-backed, outcome-layer** design with a gated-change engine. The current repo `CLAUDE.md` (Phase 1b complete, Phase 2 next) is the authoritative record of the **front-half build history**, but its **architecture, schema, and phase plan are superseded**. Five headline changes: (1) **local SQLite on the Pi is the system of record**, not Notion (Flask dashboard is the UI; nightly off-box backup day one; Notion is at most an optional one-way report mirror); (2) the **sub-target is the spine** (36-row spine; goals/DIP/NDIS-outcome/SSG are projection tags), replacing the 6-goal + two-tier-notes model; (3) **assessment lives behind the confirmation gate** — extraction writes *unassessed* observation shells, Pass 1 grades at confirmation, Pass 2 (pure logic) aggregates; (4) **all changes are candidate-gated** through one typed Candidates table and one parameterised cascade; (5) **the phase plan gains 1c (SQLite build) and 1d (engine + data load) before Phase 2** (ingestion).

---

## 2. Supersession map

### DIES (remove from CLAUDE.md / do not build)

| Superseded thing | Replaced by |
|---|---|
| **Notion as the data store** (`notion_writer.py`, "maintains a Notion knowledge base", the `notion:` settings block as system-of-record) | **Local SQLite** as system of record; a store/DB layer; Flask dashboard UI. Notion only as an optional, deferred one-way report mirror. |
| **Two-tier Goal Progress Notes** (Tier 1 / Tier 2, the `Sub-target` select on notes, the differential + temporal goal-note model) | **Sub-target-anchored Observations** (Lower/At/Above/Gap/Adjacent) + a separate **Strategy Observations** running log. The Goal Progress Notes DB is replaced, not migrated — clean teardown. |
| **`###GOALS_WITH_BENCHMARKS###` injected at extraction** | Benchmarks are **not** injected at extraction. Extraction routes facts to sub-targets using title + scope. Benchmarks inject at the **Pass 1 assessment** step (post-confirmation), scoped to touched sub-targets. |
| **"Goal Areas Touched" (6 NDIS goals, encounter-level)** | **Sub-targets Touched** (sub-target level, the fan-out funnel's considered set). |
| **6-goal structure + per-goal "Adjacent"** as the spine | The **36-row sub-target spine** (Decision A): 25 goal-area + 4 Other + 5 Medical + 2 holding pens; each row single-tagged per framework. Goals demote to roll-up views. |
| **Phase 2 (Gmail ingestion) is NEXT**; the "Phase 2 pre-conditions" (add Goal Areas Touched; archive 3 test records) | **Phase 1c (SQLite structural build) is NEXT**, then 1d (engine + data load), *then* Phase 2 (ingestion). The 3 test records are torn down in the 1c/1d rebuild regardless. |
| **Notion-property gotchas** — `Appointement Date` typo, `Detail`=`Notes`, `Observation`=`Note`, the 2000-char rich_text limit / page-body raw-notes workaround | **Resolved by the SQLite rebuild** — clean column names, `TEXT` columns with no 2000-char limit. Keep these only as a one-line historical note ("resolved by SQLite rebuild"), not as live gotchas. |
| **Notion MCP data-isolation dance** (separate Notion workspace; connect via MCP for structural setup; sever at Phase 3) | **Largely moot** — the engine never enters Notion, so there is no MCP data connection to sever. Phase 1c stands up SQLite locally, no MCP. Isolation only re-enters if the optional Notion mirror is built (write-scoped token, reports only). |

### RETAINED (front half — reuse as-is, preserve in CLAUDE.md)

- **The ingestion/extraction front half**: `ingest.py`, `extract.py` content routing + OCR pipeline (pdfplumber / Tesseract / python-docx / BeautifulSoup), the clean-labelled-text output format, the OCR quality check, the Story Champs skills-table handling.
- **Provider matching** (`notion_writer.py`'s matching logic moves to the new store layer, but the *rules* stand): combined-name split, normalise, fuzzy + Aliases match, canonical provider list injected at extraction as primary defence.
- **`###PLACEHOLDER###` substitution, never `.format()`/f-strings** (JSON braces in prompt bodies).
- **Prompts live in settings.yaml**, read at runtime, never hardcoded.
- **`###TODAY###` / `###APPOINTMENT_DATE###`** injection (the date context survives; the benchmark injection does not).
- **Email subject patterns** (FORCE INGEST / FORCE BRIEF / NDIS REPORT), dual-inbox dedup on Gmail Link, thread handling.
- **Lead Provider dropped / Providers multi-relation authoritative**; multi-provider meeting rule; archive keyed off each action's own provider.
- **Saturday/Sunday job timing**; overdue = hard due dates only.
- **The Phase 1 / Phase 1b build history and validation outcomes** (see §4 — preserve verbatim-ish).
- **Self-review** as a single Sonnet pass — but its *content* changes (no assessment at extraction; see §3).

### NEW (build in Phase 1c/1d — from the schema doc)

- **Local SQLite store + a store/DB access layer** (replaces `notion_writer.py`).
- **The outcome-layer tables**: Sub-targets, Goal Pages, Observations, Strategies, Strategy Observations, Benchmark Change Log, Strategy Change Log, Findings, **Candidates** (typed), re-anchored Health Actions, Appointments (+ Sub-targets Touched), Providers, Archive — full DDL in `decision-I-sqlite-schema.md`.
- **The gated-change engine**: one typed Candidates table; one parameterised cascade (three triggers: data-load advance / live correction / report retraction — draft trivial, confirmed cascades); the four correction cases; typed override-capture; append-only change-log triggers.
- **Pass 1 assessment** (Haiku, at confirmation, scoped to touched sub-targets) and **Pass 2 reconciliation** (pure logic).
- **Flask dashboard with the Candidates review page** (day one) + nightly off-box backup.

---

## 3. The entry-flow change (most important behavioural change)

**Assessment now lives behind the confirmation gate.** This changes what `extract.py` emits and adds a new step:

- **Extraction (Sonnet, at ingestion)** produces **unassessed observation shells** — fact, sub-target anchor, source, date, Sub-targets Touched — with `assessment = NULL`. It does fan-out + attribution + strategy-vs-noise + self-review only. It does **not** grade against benchmarks, and benchmarks are **not** injected.
- **Pass 1 assessment (Haiku, at confirmation)** grades the shells against each touched sub-target's benchmark as-of the observation date, using the same `assess(fact, benchmark_as_of)` the cascade uses. This is where `###GOALS_WITH_BENCHMARKS###` now injects, scoped to touched sub-targets only.
- **Pass 2 reconciliation (pure logic)** aggregates immediately after, per touched sub-target.
- **Consequence:** a draft has nothing derived, so a draft fact is freely editable with no cascade, and **draft retraction is trivial**. The hard case is *confirmed*-report retraction (cascade).
- **Self-review content changes:** the JSON shows unassessed observations; the *assessment*-coherence sibling check (Above/Regression contradiction) moves to Pass 1; only the *split*-coherence sibling check runs at extraction.
- **Safety-critical alert** keys off the **capture-time severity screen** on Medical sub-targets (language-based, at extraction), not a benchmark grade — so deferring assessment does not mute it.

See `health-agent-design.md` §6 and `decision-I-sqlite-schema.md` §0/§4 for the full model.

---

## 4. Build history to PRESERVE in the reworked CLAUDE.md

These exist nowhere but the repo `CLAUDE.md`. Keep them (lightly reframed where SQLite resolves them):

- **Phase 1 ✓ COMPLETE (2026-05-30)** — full pipeline proven on one real report; tested on 3 reports (individual OT note, speech group session, multi-provider FSSP). Keep the deviations list, but tag the Notion-property ones (`Appointement Date`, `Detail`/`Notes`, `Observation`/`Note`, rich_text 2000-char limit) as **"historical — resolved by the SQLite rebuild."** Keep the live ones (notion-client pin → now mirror-only; Tesseract path; `###PLACEHOLDER###` rule; provider-matching bug → fixed in 1b).
- **Phase 1b ✓ COMPLETE (2026-06-14)** — differential+temporal goal-notes model, provider-matching fix, extract.py rewiring, raw-notes fix, self_review→Flags. **Keep the validation outcomes** (FSSP 6→2 candidates, OT home visit, Story Champs) as the historical record of front-half extraction quality — but add a note that the **two-tier goal-notes model it validated is now superseded** by the outcome layer; the *extraction/provider/OCR* parts of that validation still stand, the *goal-note* parts are obsolete.
- The **Story Champs skills-table** handling note — retain (front-half, still relevant; it now feeds Observations, not two-tier notes).

The point: someone reading the reworked CLAUDE.md should still see what was built and learned, without being misled into thinking the two-tier model or Notion store is live.

---

## 5. settings.yaml changes

Rework the `settings.yaml` section:

- **Drop the `notion:` block as system-of-record.** Replace with a SQLite path (e.g. `db_path: data/health.db`) and the backup target. If/when the Notion mirror is built, a minimal `notion_mirror:` block returns — deferred.
- **`NOTION_API_KEY`** → mark optional (mirror-only).
- **Prompts:** `extraction_prompt` no longer assesses or injects benchmarks — it does fan-out + attribution + self-review producing unassessed shells. Add a new **`assessment_prompt`** (Haiku, Pass 1) that injects the touched sub-targets' benchmarks and grades. `benchmark_update_prompt` stays (structure-preserving, on approval) but now operates on the Sub-targets table, not NDIS-Goals rich-text. Add prompts as the engine needs them (candidate reason-summary, goal-roll-up digest, etc.) per the design doc's model-assignment table.
- **Injection set** for extraction: `###EXTRACTION_CONTEXT###`, `###SUBTARGET_ROUTING_LIST###` (title + scope, **no benchmarks**), `###PROVIDER_LIST###`, `###ACTIVE_STRATEGY_TITLES###`, `###REPORT_TEXT###`, plus `###APPOINTMENT_DATE###`/`###TODAY###`. (See `health-agent-design.md` §9.1.)
- Keep the feature-flags block; add flags as new capabilities land.

Finalise exact keys against the real Phase 1c build.

---

## 6. Proposed reworked CLAUDE.md structure

Aim for **leaner than the current file** — point to the design docs rather than duplicating them. Suggested sections:

1. **What This Project Does** — updated one-paragraph (SQLite store, sub-target spine, outcome layer, Flask dashboard).
2. **Source of Truth** — point to `health-agent-design.md` (architecture) and `decision-I-sqlite-schema.md` (physical schema/engine) in the repo; state the authority rule.
3. **Repository Structure** — *finalise during 1c.* Note the front-half modules retained, `notion_writer.py` → store/DB layer, new engine modules (store, candidates/cascade, pass1_assess, pass2_reconcile, dashboard with Candidates page).
4. **Environment & Secrets** — `ANTHROPIC_API_KEY`, Gmail creds, SQLite `db_path`, backup target; `NOTION_API_KEY` optional/mirror-only.
5. **settings.yaml structure** — per §5 above.
6. **The data model** — a short pointer to the schema doc + the one-line table list; do **not** duplicate the DDL.
7. **The entry flow** — the §3 summary (shells → confirm → Pass 1 → Pass 2 → candidate gate).
8. **Conventions** — from `health-agent-design.md` §23 (SQLite-aware: writes check for existing rows; derived values never raw-edited — correction→candidate→cascade; change logs append-only; prompts in settings.yaml; `###PLACEHOLDER###` rule; feature flags at runtime).
9. **Build History** — Phase 1 + 1b records and gotchas per §4 (with the historical-resolved tags).
10. **Current Build Phase: Phase 1c** — the build scope (§7 below).
11. **Likely Sticking Points** — SQLite-aware rewrite (drop Notion-relation/dedup-on-Notion items; keep OCR quality, provider matching, dashboard-blocking, Gmail OAuth-on-Pi).

---

## 7. Phase 1c build scope (what to actually do)

From `health-agent-design.md` §21 and `decision-I-sqlite-schema.md`:

1. **Create the local SQLite database** and stand up the outcome-layer tables per the schema doc DDL — including the append-only change-log triggers and the `CHECK` constraints. Add the `users` table (admin/carer) for Flask auth.
2. **Build the store/DB access layer** (replaces `notion_writer.py`); migrate provider-matching into it.
3. **Re-anchor Health Actions to sub-target**; add `Sub-targets Touched` to Appointments.
4. **Seed the 36-row sub-target spine** (Decision A) two-anchored: year-ago FSSP **Baseline** + the 13/06 hand-written benchmark as latest-confirmed. Seed Other's 4 candidate domains as Adjacent-watch (Sleep seeded **Active**), the 5 Medical watch domains, and the 2 holding pens. **Five rows can be stood up benchmark-blank** (Fine Motor current level, Continence-medical, Gastro, Dental, Growth) — Matt fills these before the 1d data load; they do **not** block the structural build.
5. **Stand up the day-one Flask Candidates review page** (structured rows, grouped by sub-target, inline approve/reject) and the **nightly off-box backup**.
6. **No MCP connection** — the engine is local SQLite.

**Phase 1c does NOT include** the engine logic (Pass 1/Pass 2/cascade), the data load, or ingestion — those are 1d and Phase 2. 1c is the structural stand-up + seed.

**Blocked-on (data, not structure):** the five gap-blank seed values and the **strategy end-anchor draft** (Matt's drafting tasks) gate the 1d data load, not the 1c build.

---

## 8. Sequencing — finalise now vs during the build

- **Rework now** (so the file correctly describes the target before 1c starts): What This Project Does, Source of Truth, the data model pointer, the entry flow, conventions, build history, the supersession-driven removals, and the Phase 1c scope.
- **Finalise during 1c** (they describe code that doesn't exist yet): Repository Structure, the exact `settings.yaml` keys, the module list, and the Likely Sticking Points specifics. Update these as the structural build lands — which is the normal "update CLAUDE.md at end of phase" cadence.

---

## 9. Guardrails

- **Do not lose the build history.** The Phase 1/1b records and gotchas are the irreplaceable part of the current file.
- **Do not duplicate the design docs into CLAUDE.md.** Point to them. CLAUDE.md should get *shorter*.
- **Do not build the engine or ingest in 1c.** 1c is structure + seed only.
- **Do not reintroduce a benchmark at extraction**, a two-tier note, a Lead Provider, or a Notion write-path for engine data.
- **Data isolation:** engine data is local SQLite only; if the optional Notion report-mirror is ever built, it pushes generated reports only via a write-scoped token — never the raw record.
- **Fetch-before-write discipline** carries over to SQLite (check for existing rows before insert; the change logs are append-only by trigger).
