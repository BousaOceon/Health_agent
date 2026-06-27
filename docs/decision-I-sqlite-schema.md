# Health Agent — Decision I & the Gated-Change Engine

**SQLite schema · Phase 1c build spec**
Status: draft 4 for review · 27/06/2026 (folds in the pre-1c schema reconciliations: sub_targets +ssg/reporting_subgroup/scope_line; observations +severity_screen/graded_against_benchmark_id; appointments +content_sources; providers +authored fields; users + recompute_audit DDL; the C10 version-gate on cascade recompute). Draft 3 added assessment-behind-the-confirmation-gate; draft 2 added typed override-capture, the four correction cases, and the Pass 2 triggers.
Resolves: the data-layer fork (system-of-record) + Decision I (candidate/change-approval schema) + the gated-change lifecycle questions.

---

## 0. What this draft resolves

Three things that turned out to be one:

1. **Data layer — local SQLite on the Pi is the system-of-record.** The engine ops (Pass 2 reconciliation, cadence/staleness, archive) are aggregate queries over dated rows; the Findings → Observations → Sub-targets → Change-Logs model is ~1:1 with relational tables; corrections need *atomic recompute*, which Notion structurally cannot do. The Flask dashboard is the UI; a nightly off-box SQLite backup is the disaster-recovery line (non-negotiable, day one); a one-way Notion mirror of generated reports is optional and deferrable.
2. **Decision I — one `candidates` table**, typed by `change_class`, grouped by sub-target in the review UI. It is *not* the appointments-scoped `flags` field, and its records are structured rows, not JSON blobs.
3. **The gated-change lifecycle** — reversibility, origination, assessment corrections, report retraction — all resolve to **one parameterised cascade** with three triggers (data-load advance · live correction · report retraction).

**Entry-flow decision folded in (27/06/2026): assessment lives behind the confirmation gate.** Extraction (Sonnet) writes **unassessed observation shells** — fact, anchor, source, date, but `assessment = NULL`. **Pass 1 assessment** (a scoped Haiku call) grades the shells **at confirmation**, using the *same* `assess(fact, benchmark_as_of)` the cascade calls on recompute; **Pass 2** aggregates immediately after. Nothing derived exists at draft, so a draft fact is freely editable with no cascade (the edit-map is clean by construction), and **draft retraction becomes trivial** — the hard retraction case is a *confirmed* report (§4). This is why first-assessment and re-assessment are one code path, and why `assessment` / `assessment_rationale` / `assessment_confidence` are written at confirmation, not extraction.

---

## 1. The integrity rule

> **A value's edit policy is determined by one question: does anything derive from it?**

| Tier | Records | Edit policy | Mechanism |
|---|---|---|---|
| **Asserted facts** | observation note/date/provider/fact; the verbatim source fragment; action wording; appointment metadata | **Edit freely.** Extraction is fallible; this is the surface that catches what slips past review. Original preserved, edit attributed + dated. | A form per field. The only genuinely new build. |
| **Interpretation** | encounter/status summaries | **Edit freely, not preserved**, but `last_edited` + `edited_by` stamped. Once a human edits, the agent **proposes, never overwrites**. | Light: two metadata columns + a never-stomp rule. |
| **Derived / gated values** | observation `assessment`; benchmark lines; strategy component status/definition; strategy-obs `status_read` | **Never raw-edited.** A change is a *correction → candidate → cascade*. | Reuses the candidate gate. **Zero new editor.** |
| **History** | benchmark & strategy change logs | **Never edited, ever.** A wrong entry is countered by a new compensating entry. | Append-only (enforced by trigger). No edit UI. |

A *fact* is asserted → re-assert it (edit). An *assessment* is derived → fix the input and recompute (gate). A *log entry* is historical → only append (compensating entry). This isn't a list of special cases; it's that one test, which is why it holds as the schema grows.

### 1.1 The override-capture principle (the engine's tuning substrate)

> **Every place a human overrides the agent, capture the override as a structured, typed, queryable signal — never free text alone, never silent.**

The decision engine improves only from *paired* data: what the agent said (+ its rationale + its confidence, frozen) and what the human corrected it to (+ a typed reason-class). This is a schema requirement at **every** agent-decision point, not a nice-to-have bolted on later — the difference between "we could tune this someday" and tuning data sitting in queryable form from day one. The override surfaces and where each is captured:

| Agent decision | Agent's call (frozen) | Override captured as | Tuning question |
|---|---|---|---|
| Observation grade *(set at Pass 1 / confirmation)* | `assessment` + `assessment_rationale` + `assessment_confidence` | `assessment-correction` candidate + `correction_reason_class` | which benchmarks the model misgrades |
| Fan-out split *(set at extraction)* | `fan_out_rationale` + `fan_out_confidence` | `fan_out_corrected` + `fan_out_correction_class` on the finding | over/under-splitting patterns |
| Pass 2 proposal | the candidate + `confidence` | `reject_reason_class` + note | which proposals are noise |
| Observation validity | the recorded fact | `invalidated_reason_class` | hallucinated / mis-anchored findings |
| Strategy status-read | `status_read` | `strategy-status-correction` candidate + `correction_reason_class` | strategy-language misreads |

Rule of construction: **reason-classes are enums, plus an optional free-text note.** The enum is what makes "misgrades cluster on FE sub-targets" a single query; the note carries the specifics. Original rationale/confidence are **never overwritten** on correction — they are the wrong-reasoning evidence you are learning from. (Note the two decision *times*: the fan-out split and its rationale are frozen at extraction; the grade and its rationale are frozen at Pass 1 / confirmation. A grade override therefore learns against the Pass-1 rationale, not an extraction-time one.)

---

## 2. The change vocabulary

Three distinct things people conflate. Keep them separate:

**`candidates.change_class`** — what a proposed change *is* (the review queue):

| change_class | origin | on approval, mutates… | writes a change-log entry? | runs cascade? |
|---|---|---|---|---|
| `benchmark-change` | system (Pass 2) | `sub_targets.current_benchmark` + as-of | **yes** — Progression / Regression / Addition | no (it *is* the Pass 2 output) |
| `benchmark-correction` | manual | `sub_targets.current_benchmark` + as-of | **yes** — Correction | **yes** |
| `benchmark-revert` | system (Pass 2) | restore prior benchmark + as-of | **yes** — Revert | no |
| `assessment-correction` | manual | `observations.assessment` **in place** | **no** — the candidate *is* the audit | **yes** |
| `adjacent-promotion` | system (cluster) | `sub_targets.status` Adjacent-watch → Active; seed first benchmark | **yes** — Baseline | no |
| `spin-out` | system/manual | `sub_targets.goal_id` re-point | no (no benchmark moves; history travels on the relation) | no |
| `strategy-diff` | system (set-diff) | `strategies` row (add / adjust / discontinue / achieve) | **yes** — Added / Adjusted / Discontinued / Achieved | no |
| `strategy-status-correction` | manual | `strategy_observations.status_read` **in place** | **no** — candidate is the audit | re-run set-diff |

Note the two **in-place corrections** (`assessment-correction`, `strategy-status-correction`) write **no** change-log entry — the approved candidate row is their permanent audit. A change log entry appears *only when a benchmark or strategy component actually moves*.

**`benchmark_change_log.change_type`**: `Progression` · `Regression` · `Addition` · `Baseline` · `Correction` · `Revert`
**`strategy_change_log.change_type`**: `Added` · `Adjusted` · `Discontinued` · `Achieved` · `Correction` · `Revert`

**In-place mutation (no log of its own):** an observation's `assessment`, a strategy-obs's `status_read`. Audited by their approved candidate.

---

## 3. Schema (SQLite DDL)

Dates are ISO-8601 `TEXT` (`YYYY-MM-DD`). Booleans are `INTEGER` 0/1. Enums are `CHECK` constraints. Multi-value lists that are never queried relationally (touched-sets, source-id arrays) are JSON `TEXT`; anything queried is a real relation.

```sql
PRAGMA foreign_keys = ON;

-- ============================================================
-- SUPPORTING / EVIDENCE LAYER (abbreviated to engine-relevant fields)
-- ============================================================

CREATE TABLE providers (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    aliases       TEXT,                       -- comma-sep nicknames; matcher + extraction injection
    type          TEXT,                       -- GP/Paed/OT/Speech/Physio/Psychology/Continence/...
    primary_email TEXT,
    known_sender_emails  TEXT,                 -- JSON array
    known_sender_domains TEXT,
    ndis_funded   INTEGER DEFAULT 0,
    contact_phone TEXT,                        -- authored metadata (Phase-4 brief/handover)
    typical_report_format TEXT,               -- authored; aids extraction-format expectations
    appointment_frequency TEXT,               -- authored; informs the brief-scope window per provider
    notes         TEXT
    -- DERIVED, not stored: "Last Appointment" = MAX(appointments.appointment_date) via the appointments↔providers link;
    -- "Supporting sub-targets / goals" = DISTINCT sub_target_id from observations ∪ strategy_observations where source_provider_id = this provider
    --   (windowed for brief scope — see design §14). No goal/sub-target↔provider join table.
);

CREATE TABLE goal_pages (
    id            TEXT PRIMARY KEY,           -- 6 NDIS + Medical + Other
    title         TEXT NOT NULL,
    category      TEXT,                       -- NDIS / Medical / Other
    plan_period   TEXT,
    goal_description TEXT,                     -- verbatim NDIS plan text (not FSSP summary)
    scope         TEXT,                       -- bounds Tier-2 adjacency
    status        TEXT CHECK (status IN ('Active','Achieved','Modified','Discontinued'))
);

CREATE TABLE appointments (
    id              TEXT PRIMARY KEY,
    title           TEXT,
    meeting_type    TEXT,
    appointment_date TEXT,                     -- the observation/encounter date
    report_received_date TEXT,
    type            TEXT,
    status          TEXT NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft','confirmed','not-approved','archived')),
    not_approved_reason TEXT,
    source_email    TEXT,                      -- Primary / Secondary / Both
    summary         TEXT,                      -- interpretation: editable, not logged
    summary_last_edited TEXT,                  -- version stamp (Tier-2 edit policy)
    summary_edited_by   TEXT,                  -- Agent / Matt / Louise
    gmail_link      TEXT,                      -- dedup key
    content_sources TEXT,                      -- JSON array: which source types fed extraction (scanned-image / native-pdf / docx / email-body); provenance for briefs/digests + OCR-quality review
    backfill        INTEGER NOT NULL DEFAULT 0,
    sub_targets_touched TEXT,                  -- JSON array (the fan-out funnel's considered set)
    flags           TEXT                       -- per-report self_review JSON (NOT candidates)
);

-- ============================================================
-- THE SPINE
-- ============================================================

CREATE TABLE sub_targets (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,            -- "SC · Dressing — upper body" (XX· is display only)
    goal_id         TEXT NOT NULL REFERENCES goal_pages(id),   -- mutable; re-pointed on spin-out
    dip_domain      TEXT,                      -- single tag (Interpersonal Interactions — naming fix)
    ndis_outcome_domain TEXT,                  -- single tag
    ssg             TEXT,                      -- optional projection lens: Independence / Participation / Emotional Regulation (Decision A 25/06, refined 27/06)
    reporting_subgroup TEXT,                   -- optional goal-internal subgroup for a reporting roll-up
    scope_line      TEXT,                      -- short discriminating description; injected at extraction (###SUBTARGET_ROUTING_LIST###) to route facts, esp. between near-neighbours
    current_benchmark TEXT,                    -- present-state; NULL until promotion for Adjacent-watch
    benchmark_as_of TEXT,                      -- date this line was last confirmed/changed
    ndis            INTEGER NOT NULL DEFAULT 0,-- 1 = formal current-plan sub-target
    status          TEXT NOT NULL DEFAULT 'Active'
                      CHECK (status IN ('Active','Adjacent-watch','Achieved','Dormant')),
    severity        TEXT CHECK (severity IN ('None','Watch','Safety-critical')),  -- Medical only
    created_at      TEXT NOT NULL
);

-- ============================================================
-- FINDINGS → OBSERVATIONS  (the benchmark lane)
-- ============================================================

CREATE TABLE findings (
    id              TEXT PRIMARY KEY,          -- stable; survives reprocessing
    source_encounter_id TEXT NOT NULL REFERENCES appointments(id),
    source_fragment TEXT NOT NULL,             -- the anchored fact, held CONSTANT across children
    title           TEXT,
    fan_out_rationale TEXT,                    -- why split as it was (tuning substrate)
    fan_out_confidence TEXT CHECK (fan_out_confidence IN ('high','medium','low')),
    fan_out_corrected INTEGER NOT NULL DEFAULT 0,  -- 1 = human changed the split at review
    fan_out_correction_class TEXT CHECK (fan_out_correction_class IN
                      ('over-split','under-split','wrong-targets')),  -- typed override
    fan_out_correction_note TEXT
);

CREATE TABLE observations (
    id              TEXT PRIMARY KEY,
    finding_id      TEXT NOT NULL REFERENCES findings(id),    -- provenance + sibling binding
    sub_target_id   TEXT NOT NULL REFERENCES sub_targets(id), -- THE relation of record
    goal_id         TEXT REFERENCES goal_pages(id),           -- denormalised; re-derived on re-point
    source_encounter_id TEXT NOT NULL REFERENCES appointments(id),
    source_provider_id  TEXT REFERENCES providers(id),        -- only when author = Provider
    author          TEXT CHECK (author IN ('Provider','Matt','Louise','System')),
    source          TEXT CHECK (source IN ('Appointment Report','Family Observation','Query Session Observation')),
    date            TEXT NOT NULL,             -- appointment/observation date
    note            TEXT,                      -- goal-framing around the constant fragment
    assessment      TEXT CHECK (assessment IN ('Lower','At','Above','Gap','Adjacent')),  -- DERIVED; NULL at creation (extraction writes a shell), set by Pass 1 at confirmation
    assessment_rationale TEXT,                 -- frozen at Pass 1 / confirmation (when the grade is set); NOT overwritten on correction
    assessment_confidence TEXT CHECK (assessment_confidence IN ('high','medium','low')),  -- set at Pass 1
    assessment_superseded INTEGER NOT NULL DEFAULT 0,  -- 1 = grade corrected; rationale is stale-model-reasoning
    milestone       INTEGER NOT NULL DEFAULT 0,
    benchmark_as_of_at_obs TEXT,               -- the benchmark date this was judged against (frozen)
    graded_against_benchmark_id TEXT REFERENCES benchmark_change_log(id),  -- VERSION key for the cascade's recompute gate: re-grade only when the governing benchmark version changes (not on every cascade, and not keyed on date alone — a wording-only correction can preserve the as-of date)
    severity_screen TEXT CHECK (severity_screen IN ('None','Watch','Safety')),  -- capture-time language screen on Medical findings; set at EXTRACTION (independent of assessment); drives the immediate alert and is queryable ("which findings tripped")
    status          TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','invalidated')),
    invalidated_reason_class TEXT CHECK (invalidated_reason_class IN
                      ('not-an-event',            -- recorded something that didn't happen → no replacement
                       'wrong-fact-replaced',     -- event real, described wrong → replacement entered
                       'duplicate',
                       'superseded-by-correction')),
    invalidated_note TEXT,                     -- optional specifics alongside the class
    replaced_by_observation_id TEXT REFERENCES observations(id)  -- the corrected replacement, if any
);

CREATE INDEX idx_obs_subtarget_date ON observations (sub_target_id, date);
CREATE INDEX idx_obs_status ON observations (status);

-- ============================================================
-- STRATEGIES → STRATEGY OBSERVATIONS  (the strategy lane — mirrors the benchmark lane)
-- ============================================================

CREATE TABLE strategies (
    id              TEXT PRIMARY KEY,          -- one row per COMPONENT
    title           TEXT NOT NULL,
    sub_target_id   TEXT NOT NULL REFERENCES sub_targets(id),  -- the "set" = filtered view, not a table
    status          TEXT CHECK (status IN ('Active','Inactive-didnt-work','Inactive-superseded','Achieved')),
    definition      TEXT,                      -- what an `adjust` edits
    introduced      TEXT,
    last_referenced TEXT,                      -- bumped on EVERY mention incl. unchanged (staleness clock)
    introduced_by   TEXT REFERENCES providers(id),
    source_encounter_id TEXT REFERENCES appointments(id),
    effectiveness_context TEXT,                -- STATED-only; never inferred
    outcome_note    TEXT
);

CREATE TABLE strategy_observations (
    id              TEXT PRIMARY KEY,          -- the running log: a row per mention
    finding_id      TEXT REFERENCES findings(id),             -- shared spine with observations
    component_id    TEXT REFERENCES strategies(id),           -- empty if unmatched/general
    sub_target_id   TEXT NOT NULL REFERENCES sub_targets(id),
    source_encounter_id TEXT REFERENCES appointments(id),
    source_provider_id  TEXT REFERENCES providers(id),
    author          TEXT CHECK (author IN ('Provider','Matt','Louise','System')),
    date            TEXT NOT NULL,
    note            TEXT,
    status_read     TEXT CHECK (status_read IN              -- DERIVED (status, not magnitude); NULL at creation, set by the Pass-2 set-diff at confirmation (mirrors observations.assessment)
                      ('Still-active','Working-stated','Not-working-stated','Discontinued-stated','New-proposed')),
    status_superseded INTEGER NOT NULL DEFAULT 0,            -- 1 = status_read corrected
    status          TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','invalidated')),
    invalidated_reason_class TEXT CHECK (invalidated_reason_class IN
                      ('not-an-event','wrong-fact-replaced','duplicate','superseded-by-correction')),
    invalidated_note TEXT
);

CREATE INDEX idx_stratobs_subtarget_date ON strategy_observations (sub_target_id, date);

-- ============================================================
-- THE CHANGE-LOG SPINE  (append-only, dated; written ONLY via the gate)
-- ============================================================

CREATE TABLE benchmark_change_log (
    id              TEXT PRIMARY KEY,
    title           TEXT,                      -- auto: "sub-target — change type — date"
    sub_target_id   TEXT NOT NULL REFERENCES sub_targets(id),
    change_type     TEXT NOT NULL CHECK (change_type IN
                      ('Progression','Regression','Addition','Baseline','Correction','Revert')),
    from_value      TEXT,                      -- prior benchmark (NULL for Baseline/Addition)
    to_value        TEXT,
    effective_date  TEXT NOT NULL,             -- the OBSERVATION date that drove it (not processing date)
    triggering_observation_ids TEXT,           -- JSON array
    confirmed_by    TEXT CHECK (confirmed_by IN ('System-candidate','Matt-approved')),
    candidate_id    TEXT REFERENCES candidates(id),   -- the candidate that produced this entry
    created_at      TEXT NOT NULL
);

CREATE TABLE strategy_change_log (
    id              TEXT PRIMARY KEY,
    title           TEXT,
    component_id    TEXT REFERENCES strategies(id),
    sub_target_id   TEXT NOT NULL REFERENCES sub_targets(id),  -- denormalised for grouped review
    change_type     TEXT NOT NULL CHECK (change_type IN
                      ('Added','Adjusted','Discontinued','Achieved','Correction','Revert')),
    from_value      TEXT,
    to_value        TEXT,
    reason          TEXT,                      -- verbatim-anchored where possible
    effective_date  TEXT NOT NULL,
    source_encounter_id TEXT REFERENCES appointments(id),
    confirmed_by    TEXT CHECK (confirmed_by IN ('System-candidate','Matt-approved')),
    candidate_id    TEXT REFERENCES candidates(id),
    created_at      TEXT NOT NULL
);

-- Append-only enforcement (example; replicate for strategy_change_log)
CREATE TRIGGER bcl_no_update BEFORE UPDATE ON benchmark_change_log
  BEGIN SELECT RAISE(ABORT, 'benchmark_change_log is append-only'); END;
CREATE TRIGGER bcl_no_delete BEFORE DELETE ON benchmark_change_log
  BEGIN SELECT RAISE(ABORT, 'benchmark_change_log is append-only'); END;

-- ============================================================
-- DECISION I — THE CANDIDATES TABLE
-- ============================================================

CREATE TABLE candidates (
    id              TEXT PRIMARY KEY,          -- 'cand_0001'
    change_class    TEXT NOT NULL CHECK (change_class IN (
                      'benchmark-change','benchmark-correction','benchmark-revert',
                      'assessment-correction','adjacent-promotion','spin-out',
                      'strategy-diff','strategy-status-correction')),
    origin          TEXT NOT NULL CHECK (origin IN ('system','manual')),

    -- target (one primary, per change_class)
    target_subtarget_id    TEXT REFERENCES sub_targets(id),
    target_observation_id  TEXT REFERENCES observations(id),
    target_strategy_id     TEXT REFERENCES strategies(id),
    target_strategy_obs_id TEXT REFERENCES strategy_observations(id),

    -- the proposed change
    from_value      TEXT,                      -- prior text/grade/status (NULL for additions/baselines)
    to_value        TEXT,                      -- proposed new value
    reason          TEXT NOT NULL,             -- Haiku-written human-readable rationale

    -- provenance (system origin) / authorship (manual origin)
    source_finding_ids     TEXT,               -- JSON array
    source_observation_ids TEXT,               -- JSON array (the supporting run)
    triggering_rule        TEXT,               -- which Pass 2 rule fired (system)
    confidence             TEXT CHECK (confidence IN ('high','medium','low')),

    -- lifecycle
    status          TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','approved','rejected','withdrawn')),
    reject_reason_class TEXT CHECK (reject_reason_class IN (
                      'right-call-wrong-moment',   -- stays valid, may re-propose later
                      'wrong-assessment',          -- spawns an assessment-correction on the trigger obs
                      'not-a-real-finding')),      -- triggers observation invalidation
    correction_reason_class TEXT CHECK (correction_reason_class IN (
                      'defensible-but-wrong',      -- reasonable on the text; human knew more (not a model fault)
                      'misgrade',                  -- wrong on the text it had (the gold tuning signal)
                      'wrong-anchor',              -- right fact, wrong sub-target (→ re-point, not invalidate)
                      'wrong-fact')),              -- for assessment-/strategy-correction candidates
    decision_note   TEXT,                       -- free-text on approve/reject (rides alongside the class)
    decided_by      TEXT,                       -- Matt / Louise (admin)
    backfill        INTEGER NOT NULL DEFAULT 0, -- 1 = data-load; suppresses correction-audit noise only

    created_at      TEXT NOT NULL,
    decided_at      TEXT,

    -- back-link to the entry this produced (NULL for in-place corrections / withdrawn / rejected)
    resulting_log_table TEXT,                  -- 'benchmark_change_log' / 'strategy_change_log'
    resulting_log_id    TEXT
);

CREATE INDEX idx_cand_status_subtarget ON candidates (status, target_subtarget_id);

-- ============================================================
-- HEALTH ACTIONS (reused, re-anchored to sub-target)
-- ============================================================

CREATE TABLE health_actions (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    source_appointment_id TEXT REFERENCES appointments(id),
    provider_id     TEXT REFERENCES providers(id),   -- single owner, even from a team meeting
    sub_target_id   TEXT REFERENCES sub_targets(id), -- outcome-layer anchor (goal denormalised)
    strategy_id     TEXT REFERENCES strategies(id),  -- when the action enables a component
    assigned_to     TEXT CHECK (assigned_to IN ('Matt','Louise','Family','Provider','Doc','School','Other')),
    category        TEXT,
    priority        TEXT CHECK (priority IN ('High','Medium','Low')),
    status          TEXT CHECK (status IN ('Open','In Progress','Done','Cancelled','Needs Triage')),
    due_date        TEXT,                      -- hard provider-stated deadlines only
    opened_date     TEXT,
    closed_date     TEXT,
    ndis_relevant   INTEGER DEFAULT 0,
    notes           TEXT                       -- freely editable (no derivation downstream)
);

-- ============================================================
-- APP-INFRA & AUDIT (1c)
-- ============================================================

CREATE TABLE users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin','carer')),
    created_at    TEXT NOT NULL
);
-- DDL defined in 1c (seed one 'admin' row; candidates.decided_by references it).
-- Flask auth/role-gating WIRING is deferred (day-one is single-user; dashboard is home-network-only) — §25.

CREATE TABLE recompute_audit (
    id              TEXT PRIMARY KEY,
    observation_id  TEXT NOT NULL REFERENCES observations(id),
    old_grade       TEXT,
    new_grade       TEXT,
    trigger         TEXT NOT NULL,             -- data-load-advance / correction / report-retraction
    triggering_candidate_id TEXT REFERENCES candidates(id),  -- the correction/advance that drove it, where applicable
    created_at      TEXT NOT NULL
);
-- Captures the internal auto-regrades that do NOT surface as candidates (the cascade's ripple).
-- Append-only; SUPPRESSED during the data load (backfill flag) — those provisional grades were scratch, not corrections.
-- Tuning substrate ("how far do corrections ripple"); defined in 1c, written by the 1d cascade.
```

---

## 4. The one cascade, three triggers

The decisions that don't fit in a single extraction call all reduce to this. **Trigger is an invalidated/updated input to a derived value — never the mere arrival of new data** (a late old report is an *addition*: recorded as-of its own date, no replay).

```
PROCEDURE cascade(sub_target, trigger):
    # trigger ∈ { data-load-advance, correction, report-retraction }
    # the proximate change is already applied (approval handler, or the retraction teardown)
    # NB: a draft report has no assessed/derived state yet (assessment is set at confirmation),
    #     so draft retraction is a plain teardown with nothing to recompute; only a CONFIRMED
    #     report's retraction actually drives this cascade.

    # 1. recompute derived grades for affected observations of this sub-target
    #    VERSION-GATED (C10): assess() is a Haiku call, NOT pure logic — so re-grading must be
    #    gated on a benchmark VERSION change, or a re-run could re-invoke the LLM and flip a grade
    #    on identical inputs (non-deterministic), breaking idempotency. Re-grade an observation ONLY
    #    when the governing benchmark version differs from the one it was graded against. The version
    #    key is graded_against_benchmark_id (a change-log entry), NOT the as-of date — a wording-only
    #    correction can preserve the date.
    for obs in observations(sub_target)
              where status = 'active'
                and source_appointment.status = 'confirmed':       # the gate must not leak
        governing = governing_benchmark_version(sub_target, obs.date)   # the change-log entry in force for obs.date
        if governing.id == obs.graded_against_benchmark_id:
            continue                                               # unchanged version → keep grade, NO assess() call (idempotent)
        new_grade = assess(obs.fact, governing.benchmark_text)     # same assess() as Pass 1, only when the version moved
        obs.graded_against_benchmark_id = governing.id             # re-stamp the version
        obs.benchmark_as_of_at_obs = governing.as_of
        if new_grade != obs.assessment:
            obs.assessment = new_grade                              # mutate IN PLACE (no new row)
            obs.assessment_superseded = 1
            if not trigger.backfill:
                record_recompute_audit(obs, old, new, trigger)     # suppressed during data load

    # 2. re-run Pass 2 (pure logic) over THIS sub-target only — counts over dated active grades
    picture = pass2_aggregate(sub_target)

    # 3. emit DELTA candidates, idempotent against already-approved change-log state
    for proposed in picture.supported_changes:
        if not already_approved(proposed):
            raise_candidate(proposed)              # new progression / addition

    for change in approved_changes(sub_target):
        if not still_supported(change, picture):
            raise_candidate(revert(change))        # withdraw a change the corrected grade no longer supports

    # NOTHING here auto-applies a benchmark move. Every move re-enters the gate.
```

**The three triggers, same procedure:**

| Trigger | Proximate change | Why it's safe |
|---|---|---|
| **Data-load advance** | approve a sequential benchmark advance (oldest-first) | the play-forward re-grades the rest of that sub-target's run against the now-current benchmark |
| **Live correction** | approve a `benchmark-correction` or `assessment-correction` | the wrong input is fixed; dependents recompute; reverts surface for any change the bad value drove |
| **Report retraction** | **draft = trivial** (plain teardown — nothing derived exists yet, assessment is post-confirmation); **confirmed = cascade** (hard-delete the report's findings/observations) | for a confirmed report, provenance (finding / source-encounter) tears down its records and the cascade withdraws any candidates Pass 2 raised from them, re-grading and re-aggregating each affected sub-target. A pure draft never reached Pass 2 (gate-tight), so its teardown recomputes nothing. |

**Two invariants this places on Pass 2:**
1. **Idempotent against approved state** — re-running proposes only the *delta* (new, or now-unsupported → revert), never re-proposing what's settled. This is the property that makes data-load, correction, and retraction all safe.
2. **Gate-tight aggregation** — Pass 2 reads only `observations.status = 'active'` whose `source_appointment.status = 'confirmed'`. Unconfirmed drafts and invalidated facts never reach the count.

**A third invariant on step 1 (the version gate, C10).** Pass 2 is pure logic and idempotent by nature; **`assess()` is not** — it is the Pass-1 Haiku call, and re-invoking it on identical inputs can return a different grade. So step 1 must be **version-gated**: re-grade an observation only when its governing benchmark *version* (`graded_against_benchmark_id`) has moved. A cascade re-run over an unchanged sub-target then makes **zero** `assess()` calls — versions match, grades stand — so the LLM step inherits the idempotency the logic steps have. Non-determinism is confined to where re-grading is genuinely warranted (the benchmark actually changed), which is acceptable. The version key is a change-log *id*, not the as-of *date*, because a wording-only correction can leave the date unchanged. *(Open at 1d: the exact resolution of `governing_benchmark_version(sub_target, date)` over the change log — a careful pass, since a loose implementation reintroduces the spurious-flip bug. The schema hook — `observations.graded_against_benchmark_id` — is in place now.)*

**When Pass 2 fires (three scopes, one procedure):**

| Trigger | Scope | Notes |
|---|---|---|
| **Appointment confirmation** | the touched sub-targets of that appointment only | the steady-state path. On confirmation: (i) flip that report's observations to `confirmed`; (ii) **Pass 1 grades the shells** (Haiku, scoped to the touched sub-targets) — this is first-assessment, the same `assess()` the cascade uses; (iii) Pass 2 aggregates each affected sub-target. A multi-provider meeting is simply a wider scope on one run. |
| **Cascade** (correction / retraction / data-load advance) | the one sub-target | as in the procedure above |
| **Full sweep** | every sub-target | data-load end (convergence validation); ad-hoc re-validation |

Firing on every confirmation is cheap, not expensive: the costly Sonnet extraction already happened at ingestion; at confirmation there is one scoped Haiku **assessment** call (Pass 1, the touched sub-targets only), then **Pass 2 is pure logic** (counts over dated rows, milliseconds locally), **scoped** (only the confirmed report's sub-targets), and **idempotent** (re-running over an unchanged sub-target proposes and writes nothing). Out-of-date-order confirmation is safe because Pass 2 always aggregates the sub-target's *full dated run*, not just the new row — the §6.3 recency logic handles a late report tipping the current picture.

**Backfill flag scope (precise):** during the data load, legitimate advances **still log** (Progression / Addition / Baseline — that's the real year of history you're validating). The flag suppresses **only** the step-1 recompute audit and `Correction` entries, because those provisional grades were scratch, not true values that got corrected. You end the load with a clean trajectory and no fake-correction noise.

**Per-sub-target independence:** after the one-time bulk extraction (the single expensive Sonnet pass), the data-load step-through is independent across all 36 sub-targets — 36 small trajectories, most quiet, processed in any order. The end-state of each should converge on the 13/06 hand-written benchmark; convergence *is* the extraction-validation signal, divergence *is* the gap candidate.

---

## 5. The four cases that look the same but aren't

What's wrong determines the mechanism — and only one of the four ever creates a replacement row.

| What's wrong | Example | Mechanism | New row? | Pass 2 duty |
|---|---|---|---|---|
| **Wrong grade** (derived output) | "t-shirt unprompted" graded `At` vs a "needs prompts" benchmark | `assessment-correction` candidate → grade mutates **in place**; `assessment_superseded=1` | no | re-count (row stays, grade changed) |
| **Wrong anchor** (right fact, wrong sub-target) | a real, well-described obs filed against the wrong target | **re-point** `sub_target_id` (+ log the re-point); do **not** invalidate | no | the obs leaves one sub-target's count, joins another's |
| **Wrong fact** (event real, described incorrectly) | said "jumper", was "t-shirt" | invalidate (`wrong-fact-replaced`) **and enter a corrected replacement**, same Finding; `replaced_by_observation_id` links them. **Finding-grain:** because `source_fragment` is held constant across all fan-out siblings, the corrected fact fans to **every sibling observation on that Finding** — each invalidated-and-replaced — not just the one looked at | **yes** — the replacement(s), one per affected sibling | filter the invalidated, count the replacement; cascade each affected sub-target |
| **Non-event** (recorded something that didn't happen) | hallucinated / duplicate | invalidate (`not-an-event` / `duplicate`), **no replacement** | no | filter it out |

The governing line: a wrong *output* mutates in place; a wrong *anchor* re-points; a wrong *fact* invalidates-and-replaces (at **Finding grain** — across all siblings sharing the fact); a *non-event* invalidates with nothing behind it.

**Why wrong-fact is Finding-grain.** The shared `source_fragment` lives on the Finding and is held identical across every fanned sibling (it is what stops the records drifting in fact). So a wrong shared fact is wrong on *all* of them at once — correcting only the observation in front of you would leave N−1 siblings asserting the old, wrong fact, each still feeding Pass 2 on its own sub-target. The correction therefore operates on the Finding: invalidate every active sibling, enter a corrected replacement per sub-target (same new Finding fact), and cascade each affected sub-target. This is the post-confirmation counterpart to assessment-behind-the-gate: while a record is in draft the fact is freely editable with no siblings yet assessed, so this Finding-grain correction is only needed once a Finding's children have been confirmed and graded.

**Why the grade re-grade never spawns a row, and never touches the rationale.** The original `assessment_rationale` is *"why the model judged this `At` against the benchmark as it stood that day."* When an upstream benchmark correction re-grades it to `Above`, the model's original reasoning didn't *become* wrong — the input it reasoned against changed. So: preserve the original rationale (it's a true record of the call at the time + the tuning evidence), flip `assessment` in place, set `assessment_superseded=1` (the query engine then knows not to cite the stale logic), and capture *why it changed* in the **candidate + recompute audit** — never re-written onto the observation. Four things, four homes: the *fact* (immutable on the obs), the *original rationale* (frozen on the obs), the *current grade* (mutated in place), the *why-it-changed* (the candidate/cascade trail).

A new observation row for a grade or non-event would give Pass 2 two rows sharing one Finding/date/fact with different grades — and Pass 2 counts grades over dates. It would double-count and fabricate a progression unless a filter is remembered on every run. Mutate-in-place / invalidate-in-place is precisely what keeps Pass 2 clean. (The misgrade reason split feeds tuning: `defensible-but-wrong` = human knew more, not a model fault; `misgrade` = wrong on the text it had, the gold signal, paired with the frozen rationale + confidence.)

---

## 6. Settled here · still open

**Settled by this draft:**
- **Assessment behind the confirmation gate (27/06)** — extraction writes unassessed observation shells (`assessment = NULL`); Pass 1 grades at confirmation (scoped Haiku, same `assess()` as the cascade); Pass 2 aggregates immediately after. First-assessment and re-assessment are one code path. This is what makes the draft fact freely editable with no cascade, and draft retraction trivial.
- SQLite-on-Pi as system-of-record; Flask UI; nightly off-box backup (day one); Notion mirror optional/deferred.
- One `candidates` table, typed; structured rows; grouped by sub-target in review. **Distinct from `flags`** (per-report extraction self-review, cleared at draft confirmation); the **Candidates page is day-one** — it is the primary interface for the 1d data load, not a Phase 5 nicety.
- Full change-type vocabulary, including `Correction` / `Revert` and the two in-place corrections that write no log entry.
- The three-tier edit map (facts / interpretation / derived) and its one governing test.
- **Typed override-capture at every agent-decision point** (§1.1) — reason-classes as enums + optional note; original rationale/confidence never overwritten. Adds: `fan_out_correction_class`, `invalidated_reason_class`, `correction_reason_class`. Grade rationale frozen at Pass 1; fan-out rationale frozen at extraction.
- **The four correction cases** (§5): wrong grade → mutate in place; wrong anchor → re-point; wrong fact → invalidate + replace **at Finding grain (fans across siblings)**; non-event → invalidate, no replacement.
- One parameterised cascade; three triggers (data-load advance / live correction / **report retraction — draft trivial, confirmed cascades**); Pass 2 idempotency + gate-tightness invariants; **Pass 2 fires per-confirmation (Pass 1 grade → Pass 2 aggregate, scoped to touched sub-targets), per-cascade (one sub-target), and full-sweep at load end**; backfill flag scoped to the correction audit only.
- Observation `active/invalidated` (+ classed reason + `replaced_by`), appointment `draft/confirmed/not-approved`, summary version-stamps.
- **Pre-1c schema reconciliations (27/06)** — `sub_targets` gains `ssg`, `reporting_subgroup`, `scope_line`; `observations` gains `severity_screen` (capture-time, Medical) and `graded_against_benchmark_id` (the C10 version key); `appointments` gains `content_sources`; `providers` gains authored `contact_phone` / `typical_report_format` / `appointment_frequency`; `users` and `recompute_audit` DDL written. **Derived, not stored:** provider "Last Appointment" and provider→sub-target/goal support (no join table) — brief scope is a windowed query over `observations ∪ strategy_observations` (design §14). Appointment status is **four** states (`draft/confirmed/not-approved/archived`).

**Still open (not blocking the 1c structural build):**
- **Confirmed-report retraction during the oldest-first data load** — *draft* retraction is now trivial (a draft has no assessed/derived state — assessment is post-confirmation). The hard case is retracting a *confirmed* mid-sequence report after Pass 2 advanced downstream benchmark state from it. The cascade handles the *mechanism*; the *operational runbook for the ripple ordering* during the load is a Phase 1d detail. Bounded, not closed.
- **Multi-source encounter reconciliation — timing residual** (design doc §13.1): two sources of one encounter are matched to one draft encounter and reconciled before draft exit (bound to one Finding, or marked corroboration-not-counted, so Pass 2 never double-counts). The residual is the case where the first source was already *confirmed* before the second arrives. Phase 2/3.
- **`recompute_audit` home** — a lightweight per-observation recompute trail (live only): a dedicated small table vs a JSON column on the observation. Minor; decide at build.
- **Pass 1 model — Haiku default, validate at 1d** — assessment is a bounded benchmark-comparison, planned as Haiku; if it misgrades on real reports (which fabricates progressions), bump to Sonnet. A run of low-confidence grades is the escalation signal.
- **Strategy-lane start-anchor** (design doc §8.2.1) — the strategy inventory is two-anchored like benchmarks: Matt drafts the current active inventory (end-anchor); FSSP strategies seed the start; gaps tolerable. Drafting task before the load.
- **Manual-candidate entry point UI** — the `origin='manual'` path exists in the schema (false-negative case: a true slow progression read as a defensible run of `At`); the dashboard affordance to raise one is a Phase 4/5 build.
- **Borderline-confirm nudge** — a run of low-confidence `At` on one sub-target as a review nudge (not a candidate); optional, Phase 5, rides the cadence analytics.

---

*Next: stand up these tables in Phase 1c, seed the 36-row spine two-anchored (year-ago FSSP Baseline + 13/06 benchmark as latest-confirmed), then build Pass 1/Pass 2 + the cascade in Phase 1d and run the data load through it.*
