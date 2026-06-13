# Health Agent – Claude Code Context

This file is read at the start of every Claude Code session. It contains the operational context needed to work on this project without re-briefing. For full design rationale and schema detail see the project design document in the Claude.ai project.

Update this file at the end of each phase: mark the phase done, note anything that deviated from the plan, record conventions or gotchas discovered during the build, then add the next phase steps.

---

## What This Project Does

A personal health coordination agent running on a Raspberry Pi. It monitors two Gmail accounts for appointment reports, extracts structured data, maintains a Notion knowledge base, and produces pre-appointment briefs, weekly digests, NDIS reporting data, an interactive performance review, and a natural language query interface over the full health record.

**Primary user:** Engineer/owner
**Secondary user:** Wife (receives digests and relevant briefs by email; no Notion access required; can trigger agent actions via email subject patterns)
**Subject:** Family member (Tom, 7) with multiple allied health providers, on the NDIS

---

## Repository Structure

```
/health-agent/
├── CLAUDE.md                  # This file – update at end of each phase
├── requirements.txt
├── config/
│   └── settings.yaml          # All configuration; single source of truth
├── .env                       # Secrets – never commit
├── inbox/                     # Downloaded attachments awaiting processing
├── processed/                 # Archived after Notion record created
├── logs/                      # Agent run logs – metadata only, no PII
└── src/
    ├── ingest.py              # Gmail polling, attachment download, thread assembly, subject pattern detection
    ├── backfill.py            # Historical backfill mode, resumable, triage logic
    ├── extract.py             # Content routing, OCR, Claude API extraction
    ├── notion_writer.py       # All Notion API read/write
    ├── brief_generator.py     # Pre-appointment brief generation
    ├── digest_generator.py    # Weekly digest generation
    ├── archiver.py            # Health Actions archive eligibility and move
    ├── email_sender.py        # Outbound Gmail API
    ├── scheduler.py           # Job orchestration
    ├── ndis_report.py         # On-demand NDIS report generation
    ├── query_engine.py        # Two-step retrieval planning and synthesis
    ├── session_writeback.py   # Session write-back extraction and Notion write
    └── dashboard/
        ├── app.py             # Flask entry point; run with --host=0.0.0.0
        ├── routes.py          # Page routes
        ├── templates/         # Jinja2 HTML templates
        └── static/            # CSS, JS
```

---

## Environment & Secrets

All secrets in `.env` – never hardcode or commit.

```
ANTHROPIC_API_KEY=
NOTION_API_KEY=
GMAIL_PRIMARY_CREDENTIALS=config/gmail_primary_token.json
GMAIL_SECONDARY_CREDENTIALS=config/gmail_secondary_token.json
GMAIL_PRIMARY_ADDRESS=
GMAIL_SECONDARY_ADDRESS=
OUTBOUND_EMAIL_PRIMARY=
OUTBOUND_EMAIL_SECONDARY=
```

---

## settings.yaml Structure

```yaml
polling_interval_hours: 4
brief_lead_time_hours: 48
weekly_digest_day: saturday
weekly_digest_time: "07:00"
brief_generation_day: sunday          # briefs run Sunday morning after weekend draft review
brief_generation_time: "07:00"
bridge_task_when: "2. Monday"

features:
  email_polling: false
  stage_2_detection: false            # canonical Stage 2 switch (see cleanup note below)
  pre_appointment_briefs: false
  weekly_digest: false
  performance_review: false
  backfill_mode: false
  query_interface: false
  session_writebacks: false
  ndis_query_report: false

backfill:
  date_from: ""
  date_to: ""
  batch_size: 10
  action_status_default: "Needs Triage"
  dry_run: true
  last_processed_message_id: ""       # resumable

known_sender_emails: []
known_sender_domains: []
keyword_phrases: []

# --- Prompts (all editable here; never hardcode in src/) ---
extraction_context: |                 # static Tom-specific baseline; injected into every extraction call
  ...see Standing Extraction Context section...
extraction_prompt: |                  # full extraction + self-review prompt; read by extract.py, NOT hardcoded
  ...uses ###PLACEHOLDER### substitution, not .format()...
benchmark_update_prompt: |            # Haiku; updates Current Benchmark after approved Goal Progress Note
  ...must preserve three-part benchmark structure...
stage_2_prompt: |
  Assess whether this email is a health appointment report,
  clinical note, or medically relevant communication...
query_system_prompt: |
  You are a health data assistant for a family managing a
  child's allied health care and NDIS plan...

notion:
  appointments_db: ""
  health_actions_db: ""
  ndis_goals_db: ""
  goal_progress_notes_db: ""
  providers_db: ""
  performance_log_db: ""
  health_actions_archive_db: ""
  digests_page_id: ""
  main_task_db: ""
```

**Stage 2 flag:** canonical switch is `features.stage_2_detection`. The duplicate top-level `stage_2_enabled` key was confirmed absent from src/ and removed from settings.yaml in Phase 1b.

---

## Notion Databases

| Database | Purpose |
|---|---|
| Appointments | One record per appointment or meeting; supports multiple providers |
| Health Actions | Active actions only; Needs Triage status for backfill items |
| NDIS Goals | Current plan goals (6 goals; see note) |
| Goal Progress Notes | Chronological findings mapped to goals + sub-targets; includes family + query session observations |
| Providers | Provider contact info, aliases, known sender addresses and domains |
| Agent Performance Log | Sender detection audit trail with user feedback |
| Health Actions Archive | Closed actions outside the 3-appointment brief window |
| Health Summary | Static Notion page – longitudinal history, diagnoses, milestones, what works |

**Current goal set (6):** Self-Care Independence, Language and Communication, Play Skills, Feelings and Emotions, Gross Motor Skills, School Environment. Fine Motor Skills was discarded (no corresponding goal in the current NDIS plan; page deleted). Goal descriptions hold verbatim NDIS plan targets, not FSSP-derived clinician summaries.

### Critical Relation Rules

- **Appointments.Providers** → multi-relation. **This is the authoritative, load-bearing provider link for all retrieval.** Every provider present in a session is linked here, including all attendees of a team meeting.
- **Health Actions.Provider** → single relation (the specific owner of this action, even when it came from a team meeting).
- **Goal Progress Notes.Source Provider** → single relation, independent of any goal's Supporting Providers. Only populated when Source = Appointment Report AND Author = Provider.
- **Goal Progress Notes.Source** → Select: Appointment Report / Family Observation / Query Session Observation.
- **Goal Progress Notes.Author** → Select: Provider / Matt / Louise / System. Carries attribution for family-originated observations so family names never land in a provider field.
- **Goal Progress Notes.Sub-target** → Select (see Goal Progress Notes section).

**Lead Provider is NOT used.** (Decision 13/06/2026.) An earlier design carried an `Appointments.Lead Provider` single relation for "last 3 appointments" and archive logic. It was never built in Notion, and it solved a problem the Providers multi-relation solves better. All "appointments with provider X" logic queries the Providers multi-relation instead. Do not add a Lead Provider field. (Optional future "Report Author" attribution metadata is allowed, but nothing in retrieval or archive may depend on it.)

### Multi-Provider Meeting Rule

One Appointment record per meeting. **All** providers linked in the Providers multi-relation. Each extracted action assigned to its specific provider in Health Actions.Provider. A physio's brief never surfaces actions assigned to the speech therapist even from the same meeting (brief reads Health Actions.Provider, not the meeting's full provider set).

---

## Provider Matching Rules (notion_writer.py)

**Fixed in Phase 1b.** The Phase 1 FSSP run created one junk combined-name record ("Kerry Britt, Madelaine Tomlin, Sally Barnard") instead of three correctly linked providers. The fix, now implemented and validated:

1. **Split combined-name strings** on commas and "and"/"&" into individual names **before** any matching. Never create a provider record from a combined string.
2. **Normalise then fuzzy match** against existing records: case-insensitive, strip titles (Dr/Mr/Ms), trim whitespace. Partial substring match handles "Madelaine Tomlin" vs "Madelaine Tomlin (Maddy)".
3. **Check the Aliases field**, not just Title. Substring match alone fails on nicknames ("Maddy" is not a substring of "Madelaine") – the Aliases multi-value field on Providers carries known nicknames and initial forms. Matcher checks Title + Aliases.
4. **Primary defence is at extraction, not in the writer** – the canonical provider list is injected into the extraction call (see Standing Extraction Context). The model maps "Maddy" → "Madelaine Tomlin" before `notion_writer` runs; fuzzy + alias matching is the backstop.
5. If no match and auto-create is enabled: create a record with available fields and add a `flags_for_review` entry for manual Type / NDIS Funded / Aliases completion. Never auto-create a combined-name record.

---

## Email Subject Pattern Detection

Runs before sender detection. Works from either monitored inbox.

| Pattern | Action |
|---|---|
| `FORCE INGEST` + attachment | Force ingest attachment as new report |
| `FORCE BRIEF – [Provider] – [Date]` | Generate brief immediately |
| `NDIS REPORT YYYY-MM-DD YYYY-MM-DD` | Generate NDIS report for date range |

---

## Content Extraction Pipeline

All sources route through `prepare_content()` in `extract.py`. Claude always receives clean labelled text – never raw files.

```
Native PDF      → pdfplumber
Scanned PDF     → pytesseract + Pillow
Phone image     → pytesseract + Pillow
Docx            → python-docx
Email body      → BeautifulSoup
Thread          → per-message with sender/date labels
```

Output format:
```
EMAIL BODY:
[text]

ATTACHMENT (filename.pdf):
[text]

THREAD MESSAGE 2 – From: sender@domain.com – YYYY-MM-DD:
[text]
```

### Extraction call wiring (extract.py)

The extraction prompt is read from `settings.yaml` (`extraction_prompt`), **not hardcoded**. Five variables are injected before the call, using **`###PLACEHOLDER###` substitution, not `.format()` or f-strings** (the prompt body contains JSON braces that `.format()` would break – see Phase 1 deviations):

- `###EXTRACTION_CONTEXT###` ← `extraction_context` from settings.yaml
- `###GOALS_WITH_BENCHMARKS###` ← fetched from the NDIS Goals database; includes the full three-part **Current Benchmark** per goal; each named sub-target line carries an inline `(as of YYYY-MM-DD)` date used as the temporal anchor for the differential model
- `###PROVIDER_LIST###` ← canonical providers (Title + Aliases + Type) fetched from the Providers database, so the model resolves names/nicknames at extraction time
- `###TODAY###` ← `date.today().isoformat()` – injected as today's date for `report_received_date` fields and temporal context
- `###REPORT_TEXT###` ← output of `prepare_content()`

The response parser handles the `self_review` block and writes the serialised `self_review` JSON to the **Flags** field on the Appointment record.

---

## Sender Detection Logic

**Stage 1 (rule engine – free, every email):**
1. Subject matches force trigger pattern → handle separately
2. Sender in known_sender_emails → auto-process
3. Sender domain in known_sender_domains → auto-process
4. Subject matches keyword_phrases → Stage 2
5. No match → skip, log

**Stage 2 (Claude Haiku – ambiguous only, when features.stage_2_detection enabled):**
- Input: sender name, subject, first ~200 words, stage_2_prompt from settings.yaml
- Output: `{ relevant: bool, confidence: high/medium/low, reason: str }`
- High → process; Medium → flag for review; Low → skip
- All Stage 2 events logged to Performance Log regardless of outcome

Never auto-process on single keywords like "report" or "plan".

---

## Standing Extraction Context

Three context inputs provided to every extraction call (see wiring above):

**1. extraction_context (static, from settings.yaml):**
Full authoritative text lives in `settings.yaml` – do not duplicate it elsewhere. Summary of intent: Tom is 7 (born Dec 2018), Chromosome 18p deletion, mosaic Trisomy 13, **ASD Level 2 – Requiring Substantial Support (diagnosed May 2026)**, hypotonia, **dysphagia with choking risk and modified diet**, low processing speed (borderline), borderline visual-spatial skills, strong visual working memory. **Grade 1** at South Geelong Primary with Education Support. The context explicitly lists his ASD-profile behaviours (routine reliance, transition distress, scripted/repetitive language, sensory sensitivities, atypical interoception, distress presentations) as **established baseline** so a report mentioning them is not mis-read as a new finding or regression. Adult prompting/support is baseline; meaningful progress = assisted→independent, generalisation across settings, or sustained unprompted demonstration. Participation with support is baseline, not progress.

**2. goals_with_benchmarks (per goal, from NDIS Goals database):**
Each goal's three-part **Current Benchmark**. Each named sub-target line carries an inline `(as of YYYY-MM-DD)` date — this is the temporal anchor for the differential model (compare to appointment date to classify a finding as historical vs current). All 23 sub-target lines were initialised 2026-06-13. Updated by Claude Haiku after each approved Goal Progress Note (`benchmark_update_prompt`, which receives `###APPOINTMENT_DATE###` and re-dates only the changed sub-target lines).

**3. provider_list (from Providers database):**
Canonical Title + Aliases + Type per provider, so name/nickname resolution happens at extraction (primary defence for provider matching).

---

## Goal Progress Notes

**Default: no note.** The extraction is a comparison against the current benchmark, not a summary of the report. The appointment summary is where ordinary session content goes.

**Three-part Current Benchmark structure** (per NDIS goal, rich text):
- **Goal scope:** what the broad goal area covers
- **Current sub-target levels:** labelled list, one line per named sub-target; each line carries `(as of YYYY-MM-DD)` — the date that level was last confirmed
- **Overall summary:** present-tense paragraph used by the brief/query engine

`benchmark_update_prompt` (Haiku) receives `###APPOINTMENT_DATE###` and must **preserve this structure exactly**: update only the specific sub-target line(s) the note addresses and stamp each changed line with the appointment date; leave all other as-of dates unchanged; update the Overall summary only if the change materially affects it; never rewrite Goal scope.

**Sub-target field (Goal Progress Notes, Select):** 29 goal-prefixed options plus a per-goal **"Adjacent"** option. Prefixes: GM / FE / SC / PS / LC / SE. Refreshed yearly at plan change. Every note's `sub_target` must belong to the same goal as its `goal_name`.

**Temporal classification (per finding, applied first):**

Compare the appointment date to the as-of date on the relevant sub-target line:

| Appointment date vs sub-target as-of date | Classification |
|---|---|
| >1 month **before** the as-of date | **Historical** |
| Within 1 month of, or **after**, the as-of date | **Current** |

**Historical findings:** ability at or below the current benchmark is expected — never a Regression. Create a note only for a genuine gap the benchmark does not capture (a capability, context, or detail absent from the benchmark text). Historical notes: **Observation or Milestone only** — never Progress or Regression. Standardised assessment scores (PEDI-CAT, Vineland, etc.) from historical reports go in the appointment summary, not Goal Progress Notes, unless they reveal a capability the benchmark omits.

**Current findings:** create a note only for a genuine change from the benchmark: assisted→independent, new-setting generalisation, first-time milestone, confirmed current regression, or a formal assessment establishing a new current baseline. Routine session content at the expected benchmark level → no note.

**Sub-target and type rules (applied after temporal classification):**
- Named sub-target finding → use that named sub-target; type Progress / Regression / Milestone for current findings; Observation or Milestone for historical gap notes
- Finding within Goal scope but not matching a named sub-target → "Adjacent" option; type Observation
- At-benchmark, routine, or uncertain → no note

**"Adjacent" is not a catch-all.** Requires a finding within Goal scope that is clinically meaningful and genuinely does not correspond to any named sub-target.

---

## Backfill Mode

Controlled by `features.backfill_mode` flag. Resumable via `backfill.last_processed_message_id`.

All actions created during backfill receive Status: **Needs Triage**. These are excluded from:
- All active Health Actions views
- Pre-appointment briefs
- Weekly digest counts
- Bridge task open/overdue numbers
- Archive eligibility

Triage via dashboard Backfill page. Claude Haiku suggests Likely Done / Mark Open / Needs Review per action. User bulk-accepts, reviews flagged items. Only approved Open items enter the active list.

---

## Model Assignments

| Task | Model |
|---|---|
| Report extraction + self-review | claude-sonnet-* (latest) |
| Stage 2 sender detection | claude-haiku-* (latest) |
| Goal progress mapping | claude-sonnet-* (latest) |
| Pre-appointment brief | claude-sonnet-* (latest) |
| Weekly health digest | claude-sonnet-* (latest) |
| Performance recommendations | claude-haiku-* (latest) |
| Benchmark update | claude-haiku-* (latest) |
| Backfill triage suggestions | claude-haiku-* (latest) |
| Query retrieval planning | claude-haiku-* (latest) |
| Query answer synthesis | claude-sonnet-* (latest) |
| Session write-back extraction | claude-haiku-* (latest) |
| NDIS report generation | claude-sonnet-* (latest) |
| Archive eligibility check | No Claude call – pure logic |

Always use latest available version. Do not hardcode specific version strings.

---

## Extraction Self-Review (Single Pass)

Extraction and self-review happen in one Sonnet call. No separate Haiku review pass.

**Sonnet auto-corrects and reports as FYI (corrections_made):**
- Speculative action language ("consider", "potential to", "may", "could", "in future") → deleted, moved to summary
- Summary > 3 sentences → truncated
- Goal name not in provided list → removed, moved to summary
- Family member in provider field → cleared
- Assigned To is Matt when report addresses both parents → corrected to Family
- Priority inflation → downgraded with reasoning

**Sonnet flags for user decision (flags_for_review):**
- First-name-only or combined provider names (cannot auto-correct)
- Unclear provider attribution in multi-provider meeting
- Goal Progress Note close to benchmark threshold
- Novel report format (low extraction confidence)

**Auto-corrections for goal notes (in addition to the general list above):**
- Default-zero violated (routine, at-benchmark, or expected-historical content) → remove note, move to summary
- Historical finding at/below benchmark recorded as note or Regression → remove
- Named sub-target content in "Adjacent" option → correct to named sub-target + fix type
- Type doesn't match tier or temporal class → correct (named sub-target current = Progress/Regression/Milestone; historical gap = Observation/Milestone; Adjacent = Observation)
- sub_target prefix doesn't match goal_name → correct or clear
- sub_target doesn't belong to goal_name → correct or remove
- **Final reconciliation:** anything recorded as "removed" in corrections_made must be absent from goal_progress_notes and actions — model explicitly verifies before returning

**JSON response structure:**
```
{
  "appointment": { ...corrected... },
  "actions": [ ...corrected... ],
  "goal_progress_notes": [ ...corrected..., each with sub_target ],
  "self_review": {
    "corrections_made": [ { rule, original, action_taken, confidence } ],
    "flags_for_review": [ { type, item, extraction_used, suggested_action, confidence } ],
    "extraction_confidence": "high/medium/low",
    "corrections_count": N,
    "flags_count": N
  }
}
```

notion_writer.py stores the serialised self_review JSON in the **Flags** field on the Appointment record. Dashboard extraction review tab renders flags_for_review as interactive cards; corrections_made shown as read-only, collapsible FYI. Original text always preserved in corrections_made so the user can reverse a correction.

---

## Query Engine (query_engine.py)

Two-step process:

**Step 1 – Planning (Claude Haiku):** Question + query_system_prompt from settings.yaml → retrieval plan (which databases, what filters).

**Step 2 – Synthesis (Claude Sonnet):** Fetched Notion records + original question + conversation history → answer with source attribution.

Source attribution rule (in system prompt): records cited by provider and date; general clinical knowledge flagged explicitly. User always knows what came from their records versus Claude's training.

Conversation history maintained within a dashboard session. Follow-up questions can trigger additional Notion fetches via the planning step.

---

## Health Summary Page

Static Notion page (not a database). Read via Notion API and included as standing context in:
- Pre-appointment brief prompt (background context section)
- Query engine system prompt (alongside database descriptions)
- NDIS report generation prompt (baseline and diagnosis section)
- New provider summary generation prompt

**Agent behaviour:** Never overwrites. When extraction identifies a new diagnosis, significant medical event, or milestone not already in the summary, flags it as a suggested addition for user approval via dashboard. Approval required before any change. (The ASD Level 2 diagnosis was added this way – user-approved, not agent-written.)

**New provider summary generator:** Dashboard button → Claude Sonnet reformats Health Summary into a clean one to two page clinical handover document. Saved to Digests & Briefs in Notion. Prompt tone: concise, professional, written for a clinician reading it for the first time.

**How to create initially:** Written manually before Phase 3 go-live. Paste existing NDIS plans, specialist letters, and school reports into Claude.ai project. Claude drafts structured summary; primary user edits into final version. Not extracted programmatically.

---

## Session Write-Back (session_writeback.py)

Runs at end of query session on user request. Claude Haiku reviews conversation, extracts conservatively:
- **Actions** → Health Actions (Category: Query Session, Status: Open)
- **Talking points** → Health Actions (Category: Meeting Action, linked to provider) – surfaces in next brief automatically
- **Observations** → Goal Progress Notes (Source: Query Session Observation, Author: System)

User approves each item individually via dashboard panel before any Notion write. All fields editable inline before saving.

---

## Scheduled Jobs

| Job | Schedule |
|---|---|
| Email poll + ingest | Every 4 hours |
| Appointment scan | Daily 07:00 (Google Calendar, 7-day look-ahead) |
| Brief generation | **Sunday 07:00** (after weekend draft review) |
| Saturday sequence | Saturday 07:00 |
| Review reminder | Saturday 09:00 (if drafts still unconfirmed) |

**Brief timing:** Pre-appointment briefs do NOT run on the daily/Saturday job. They run **Sunday morning**, after the primary user has had the weekend to review and confirm draft records, so briefs are built from confirmed data. Force brief via dashboard or email trigger if needed sooner.

**Saturday sequence (in order):**
1. Weekly health digest → save to Notion
2. Archive eligibility check → move qualifying actions
3. Draft record summary (corrections made + flags needing review, per draft)
4. Performance review page → dashboard
5. Email: health digest → both users
6. Email: draft review summary + performance review link → primary user only
7. Bridge task → main Notion task DB (post-archive counts, excluding Needs Triage)

---

## Bridge Task

```
Title:    "Health actions weekly review"
Job:      Personal  |  Project: Home
Status:   2. To Do  |  When: 2. Monday
Due Date: (empty)
Notes:    "X open, Y overdue, Z upcoming. [digest link]"
```

Counts exclude Needs Triage actions.

---

## Archive Logic

Run in `archiver.py`. **Pure logic, no Claude call.** Keyed off `Health Actions.Provider` (the action's own owner) and the Providers multi-relation – no Lead Provider.

An action is eligible to archive when ALL true:
1. Status is Done or Cancelled (Needs Triage never archived – triage first)
2. Its source appointment is NOT within the **last 3 confirmed appointments for that action's `Health Actions.Provider`**

To compute "last 3 confirmed appointments for provider X": query Appointments where `Providers` contains X AND Status = Confirmed, sort by Appointment Date desc, take 3. Check is **per provider, not global** – an annual specialist retains closed actions far longer than a weekly physio. This is correct behaviour.

---

## Coding Conventions

- All Notion writes check for existing records first (deduplication)
- All Claude API calls in try/except; errors logged to logs/
- Log files contain metadata only – never report text, names, or clinical content
- settings.yaml is single source of truth – no magic strings in src/
- Prompts live in settings.yaml, read at runtime – never hardcoded in src/
- Extraction prompt injection uses `###PLACEHOLDER###` substitution, never `.format()`/f-strings (JSON braces in prompt body)
- Gmail OAuth tokens in config/ – in .gitignore
- Each module independently runnable with `if __name__ == "__main__"` test block
- Dashboard routes must not block – long-running tasks (Claude API, Notion bulk reads) run async or via background thread
- Feature flags checked at runtime, not import time

---

## Current Build Phase

**Phase 1 – Foundations** ✓ COMPLETE (2026-05-30)

Goal: prove full pipeline end-to-end with one real report, manually triggered.

- [x] Python venv + all dependencies installed
- [ ] `sudo apt install tesseract-ocr` on Pi  ← Pi not yet arrived; Tesseract installed on Windows dev machine
- [x] Gmail API OAuth – primary account authenticated; secondary deferred (not needed yet)
- [ ] Google Calendar API authenticated  ← deferred to Phase 3 (brief generation)
- [x] Notion API connected; all seven databases readable/writable
- [x] Content extraction working (native PDF confirmed; OCR path written, not yet tested on scanned doc)
- [x] Claude API extraction prompt returning structured data from real report
- [x] Notion writer creating Appointment + Health Action + Goal Progress Note records with correct relations
- [x] `src/test_pipeline.py` runs full pipeline on single file, moves to processed/

**Tested on 3 real reports:** individual OT session note, speech group session note, multi-provider FSSP.

**Deviations and discoveries from Phase 1:**
- `notion-client` v3 removed `.query()` – pinned to v2.2.1 in requirements.txt
- Appointments DB has a typo in Notion: property is `Appointement Date` – code matches the typo (worth a future rename + code update, low priority)
- No `Lead Provider` relation field in Appointments DB – **and by 13/06 decision there will not be one**; single/multi providers go into the `Providers` multi-relation, which is now authoritative for all retrieval
- No `Gmail Message ID` text field – using `Gmail Link` (url type) for deduplication
- Tesseract not on PATH after Windows install – hardcoded in extract.py to `C:\Program Files\Tesseract-OCR\tesseract.exe`
- Extraction prompt curly braces must use `###PLACEHOLDER###` substitution, not `.format()`, to avoid escaping JSON
- Health Actions `Detail` field is `Notes` in Notion; Goal Progress Notes `Observation` is `Note`
- Notion rich_text properties are limited to 2000 chars – raw notes written to page body blocks only (`append_raw_notes_to_page()`); the `Raw Notes` property write was removed in Phase 1b and the property can be deleted from the Appointments schema. Brief retrieval uses `notion.blocks.children.list(page_id)`.
- **Provider matching bug:** FSSP combined-name string `"Kerry Britt, Madelaine Tomlin, Sally Barnard"` created one junk provider record instead of three links. Fix per Provider Matching Rules before next test.

---

**Phase 1b – Extraction Refinements** ✓ COMPLETE (2026-06-14)

Goal: differential + temporal goal-notes model, provider-matching fix, extract.py rewiring, raw-notes fix, self_review to Flags.

- [x] extraction_context, extraction_prompt (GOAL PROGRESS NOTES + SELF-REVIEW), benchmark_update_prompt updated in settings.yaml
- [x] Differential + temporal model: STEP 1–3 logic, five-variable injection, Final reconciliation step
- [x] extract.py: reads extraction_prompt from settings.yaml, injects 5 `###PLACEHOLDER###` variables, writes self_review JSON to Flags
- [x] Provider matching fixed: combined-name split, normalise, fuzzy + Aliases match; validated on FSSP
- [x] Raw notes: page body only (`append_raw_notes_to_page()`); `Raw Notes` property write removed from `create_appointment()`
- [x] `Flags` rich-text property added to Appointments in Notion; self_review JSON writes there
- [x] `benchmark_update_prompt`: receives `###APPOINTMENT_DATE###`; re-dates changed sub-target lines only
- [x] All 23 named sub-target as-of dates initialised 2026-06-13 in Notion
- [x] Clean re-run of 3 test reports

**Validation outcome:**
- FSSP (June 2025, ~12 months historical): 6 notes → 2 defensible gap candidates (SE: Adjacent, SC: Toileting), both flagged threshold_close for user review. 3 providers correctly split and linked. ✓
- OT home visit (March 2026, ~3 months historical): 1 note (GM: Stamina & range Progress, flagged threshold_close). SC: Toileting routine note correctly removed. ✓
- Story Champs (May 2026, current): 1 note (PS: Adjacent Observation, flagged threshold_close). 3 at-benchmark candidates correctly removed. ✓

**Deviations and discoveries from Phase 1b:**
- Five injection placeholders, not four — `###TODAY###` (date.today()) was added as the fifth; CLAUDE.md and code updated
- Self-review execution gap: model can correctly reason "remove this note" in corrections_made but still emit it in the JSON. Fixed by adding "Final reconciliation" as the last SELF-REVIEW step
- Historical gap note / named sub-target type conflict: historical gaps often map to named sub-targets but must be Observation or Milestone (not Progress/Regression). Made explicit in STEP 3 type rules
- `benchmark_update_prompt` now requires `###APPOINTMENT_DATE###` — any future call site must inject it alongside GOAL_NAME, CURRENT_BENCHMARK, and PROGRESS_NOTE
- `Raw Notes` property on Appointments schema can be deleted from Notion (write removed, nothing reads it)

---

**Phase 2 – Gmail Ingestion + Email Backfill** ← NEXT

**Pre-conditions (complete before Phase 2 code starts):**
- [ ] Add **"Goal Areas Touched"** multi-select field to Appointments in Notion (6 options: one per NDIS goal name; no Other option). Add to `create_appointment()` properties, populated from `extracted["appointment"]["goals_addressed"]`. Needed before backfill so the full year is tagged automatically.
- [ ] Archive the 3 Phase 1b test records (Appointments, Health Actions, Goal Progress Notes) once the Goal Areas Touched field is wired — they will be re-ingested via backfill with the correct field populated.

**Phase 2 goals:**
- [ ] Gmail API: poll primary inbox, download attachments, assemble email threads
- [ ] Sender detection Stage 1 (rule engine); Stage 2 behind `features.stage_2_detection` flag
- [ ] Deduplication on Gmail Link url field (same report in both inboxes = one record)
- [ ] `scheduler.py`: 4-hour poll job
- [ ] Backfill mode (`features.backfill_mode`): date-range scan, batch_size=10, resumable via `backfill.last_processed_message_id`, all actions → Needs Triage
- [ ] Secondary inbox support

**Phase 2 complete when:** a real email from a known sender is polled, extracted, and written to Notion without manual intervention.

---

## Pre-Backfill Data Reset

The Phase 1b clean re-run is complete (3 Appointment records written 2026-06-14). Before running the full Gmail backfill:
1. Add "Goal Areas Touched" multi-select to Appointments and wire it in `create_appointment()` (see Phase 2 pre-conditions)
2. Archive the 3 Phase 1b test records — they will be re-ingested via backfill with Goal Areas Touched populated
3. Confirm Notion schemas match code expectations (run `python -m src.notion_writer` connectivity check)

Do not carry forward Phase 1b test records as production data.

---

## Story Champs Skills Table – Verify Next Session

Session notes from Story Champs (and similar group programs) contain a structured skills table with three columns: Not Attempted / Benefits from Assistance / Independent. Verify that:
1. pdfplumber correctly extracts the table structure and X markers into raw text
2. Extraction prompt correctly interprets which column each X appears in (if column relationships are unclear in raw text, the prompt instructs Claude to describe what was observed rather than assert a column – do not misattribute an X to the wrong column)
3. A skill marked Independent is treated differently from Benefits from Assistance in summary and Goal Progress Note type assignment (Independent = stronger evidence of Progress; Benefits from Assistance = Observation at best)

---

## Local Development (Windows, Pre-Pi)

All Phase 1–4 development works on a Windows laptop before the Pi arrives. No blockers.

**Tesseract on Windows:** UB-Mannheim installer from the Tesseract GitHub releases page. Add to PATH or set explicitly in extract.py:
```python
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

**Gmail OAuth on Windows:** Browser opens normally – no headless workaround. Token files generated on Windows are reusable on the Pi; copy config/ across at migration.

**Flask on Windows:** `http://localhost:5000`. The `--host=0.0.0.0` flag and `healthagent.local` hostname are Pi-specific.

**Python venv on Windows:** Activate with `venv\Scripts\activate`.

**Pi migration when it arrives:**
1. Push repo to GitHub and pull on Pi (or scp directly)
2. Copy config/ directory including OAuth token files to Pi
3. Create venv and install dependencies on Pi
4. `sudo apt install tesseract-ocr`
5. Run `test_pipeline.py` to confirm everything works
6. Set up cron jobs (Phase 5)

Approximately one hour. Deploying working code, not rebuilding.

---

## Likely Sticking Points

**Gmail OAuth headless:** Not needed on Windows. At Pi deployment, run auth on laptop first and copy token files to Pi config/.

**Scanned PDF quality:** Add Pillow pre-processing (greyscale, contrast, resize) before Tesseract if output is garbled.

**Notion relation fields:** Capture Appointment page ID from create response immediately. Set Health Action relations in the same write sequence – not a separate update call.

**Deduplication:** Match on provider + date + Gmail message ID. Same report in both inboxes = one record.

**Multi-provider meetings:** Appointments.Providers is a list of page IDs (all attendees). Health Actions.Provider is always a single page ID – the specific owner of that action.

**Provider matching:** Split combined-name strings before matching; check Aliases not just Title; inject the canonical provider list at extraction. See Provider Matching Rules.

**Backfill resumability:** Store last processed Gmail message ID in settings.yaml after each batch. Skip already-processed messages on startup.

**Dashboard blocking:** Any route calling Claude API or doing large Notion reads must use threading/async. Flask dev server is single-threaded by default.

**Feature flags:** Check `settings.yaml features` block at the top of any function implementing a gated capability. Return gracefully if disabled.
