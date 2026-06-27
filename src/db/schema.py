"""SQLite DDL for the outcome-layer engine (Phase 1c).

Authoritative source: docs/decision-I-sqlite-schema.md (draft 4). This module
holds the schema as one executable script and an init_db() that applies it.
Forward FK references (e.g. benchmark_change_log.candidate_id -> candidates)
are fine in SQLite — FKs are resolved at insert, not at CREATE TABLE.

Dates are ISO-8601 TEXT (YYYY-MM-DD). Booleans are INTEGER 0/1. Enums are
CHECK constraints. Multi-value lists never queried relationally are JSON TEXT.
"""

SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;

-- ============================================================
-- SUPPORTING / EVIDENCE LAYER
-- ============================================================

CREATE TABLE IF NOT EXISTS providers (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    aliases       TEXT,                       -- comma-sep nicknames; matcher + extraction injection
    type          TEXT,                       -- GP/Paed/OT/Speech/Physio/Psychology/Continence/...
    primary_email TEXT,
    known_sender_emails  TEXT,                 -- JSON array
    known_sender_domains TEXT,
    ndis_funded   INTEGER DEFAULT 0,
    contact_phone TEXT,
    typical_report_format TEXT,
    appointment_frequency TEXT,
    notes         TEXT
    -- DERIVED, not stored: "Last Appointment" = MAX(appointments.appointment_date);
    -- "Supporting sub-targets/goals" = DISTINCT sub_target_id from observations U
    -- strategy_observations where source_provider_id = this provider. No join table.
);

CREATE TABLE IF NOT EXISTS goal_pages (
    id            TEXT PRIMARY KEY,           -- 6 NDIS + Medical + Other
    title         TEXT NOT NULL,
    category      TEXT,                       -- NDIS / Medical / Other
    plan_period   TEXT,
    goal_description TEXT,                     -- verbatim NDIS plan text (not FSSP summary)
    scope         TEXT,                       -- bounds Tier-2 adjacency
    status        TEXT CHECK (status IN ('Active','Achieved','Modified','Discontinued'))
);

CREATE TABLE IF NOT EXISTS appointments (
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
    summary_last_edited TEXT,
    summary_edited_by   TEXT,                  -- Agent / Matt / Louise
    gmail_link      TEXT,                      -- dedup key
    content_sources TEXT,                      -- JSON array (scanned-image / native-pdf / docx / email-body)
    backfill        INTEGER NOT NULL DEFAULT 0,
    sub_targets_touched TEXT,                  -- JSON array (the fan-out funnel's considered set)
    flags           TEXT                       -- per-report self_review JSON (NOT candidates)
);

-- All providers present at an appointment (the authoritative multi-relation for
-- retrieval/archive — design §16). The schema-doc DDL omitted this; added in 1d.
CREATE TABLE IF NOT EXISTS appointment_providers (
    appointment_id TEXT NOT NULL REFERENCES appointments(id),
    provider_id    TEXT NOT NULL REFERENCES providers(id),
    PRIMARY KEY (appointment_id, provider_id)
);

-- ============================================================
-- THE SPINE
-- ============================================================

CREATE TABLE IF NOT EXISTS sub_targets (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    goal_id         TEXT NOT NULL REFERENCES goal_pages(id),   -- mutable; re-pointed on spin-out
    dip_domain      TEXT,                      -- single tag (one of the 6 DIP domains)
    ndis_outcome_domain TEXT,                  -- single tag (NDIS Outcomes Framework); deferred tagging
    ssg             TEXT,                      -- optional lens: Independence / Participation / Emotional Regulation
    reporting_subgroup TEXT,                   -- optional goal-internal subgroup (e.g. DIP activity)
    scope_line      TEXT,                      -- short discriminating description; injected at extraction
    current_benchmark TEXT,                    -- present-state; NULL until promotion for Adjacent-watch
    benchmark_as_of TEXT,                      -- date this line was last confirmed/changed
    ndis            INTEGER NOT NULL DEFAULT 0,-- 1 = formal current-plan sub-target
    status          TEXT NOT NULL DEFAULT 'Active'
                      CHECK (status IN ('Active','Adjacent-watch','Achieved','Dormant')),
    severity        TEXT CHECK (severity IN ('None','Watch','Safety-critical')),  -- Medical only
    created_at      TEXT NOT NULL
);

-- ============================================================
-- FINDINGS -> OBSERVATIONS  (the benchmark lane)
-- ============================================================

CREATE TABLE IF NOT EXISTS findings (
    id              TEXT PRIMARY KEY,
    source_encounter_id TEXT NOT NULL REFERENCES appointments(id),
    source_fragment TEXT NOT NULL,             -- the anchored fact, held CONSTANT across children
    title           TEXT,
    fan_out_rationale TEXT,
    fan_out_confidence TEXT CHECK (fan_out_confidence IN ('high','medium','low')),
    fan_out_corrected INTEGER NOT NULL DEFAULT 0,
    fan_out_correction_class TEXT CHECK (fan_out_correction_class IN
                      ('over-split','under-split','wrong-targets')),
    fan_out_correction_note TEXT
);

CREATE TABLE IF NOT EXISTS observations (
    id              TEXT PRIMARY KEY,
    finding_id      TEXT NOT NULL REFERENCES findings(id),
    sub_target_id   TEXT NOT NULL REFERENCES sub_targets(id),
    goal_id         TEXT REFERENCES goal_pages(id),
    source_encounter_id TEXT NOT NULL REFERENCES appointments(id),
    source_provider_id  TEXT REFERENCES providers(id),
    author          TEXT CHECK (author IN ('Provider','Matt','Louise','System')),
    source          TEXT CHECK (source IN ('Appointment Report','Family Observation','Query Session Observation')),
    date            TEXT NOT NULL,
    note            TEXT,
    assessment      TEXT CHECK (assessment IN ('Lower','At','Above','Gap','Adjacent')),  -- DERIVED; NULL at creation
    assessment_rationale TEXT,                 -- frozen at Pass 1 / confirmation; NOT overwritten on correction
    assessment_confidence TEXT CHECK (assessment_confidence IN ('high','medium','low')),
    assessment_superseded INTEGER NOT NULL DEFAULT 0,
    milestone       INTEGER NOT NULL DEFAULT 0,
    benchmark_as_of_at_obs TEXT,
    graded_against_benchmark_id TEXT REFERENCES benchmark_change_log(id),  -- C10 version key for the cascade
    severity_screen TEXT CHECK (severity_screen IN ('None','Watch','Safety')),  -- capture-time, Medical
    status          TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','invalidated')),
    invalidated_reason_class TEXT CHECK (invalidated_reason_class IN
                      ('not-an-event','wrong-fact-replaced','duplicate','superseded-by-correction')),
    invalidated_note TEXT,
    replaced_by_observation_id TEXT REFERENCES observations(id)
);

CREATE INDEX IF NOT EXISTS idx_obs_subtarget_date ON observations (sub_target_id, date);
CREATE INDEX IF NOT EXISTS idx_obs_status ON observations (status);

-- ============================================================
-- STRATEGIES -> STRATEGY OBSERVATIONS  (the strategy lane)
-- ============================================================

CREATE TABLE IF NOT EXISTS strategies (
    id              TEXT PRIMARY KEY,          -- one row per COMPONENT
    title           TEXT NOT NULL,
    sub_target_id   TEXT NOT NULL REFERENCES sub_targets(id),
    status          TEXT CHECK (status IN ('Active','Inactive-didnt-work','Inactive-superseded','Achieved')),
    definition      TEXT,
    introduced      TEXT,
    last_referenced TEXT,                      -- bumped on EVERY mention incl. unchanged (staleness clock)
    introduced_by   TEXT REFERENCES providers(id),
    source_encounter_id TEXT REFERENCES appointments(id),
    effectiveness_context TEXT,                -- STATED-only; never inferred
    outcome_note    TEXT
);

CREATE TABLE IF NOT EXISTS strategy_observations (
    id              TEXT PRIMARY KEY,
    finding_id      TEXT REFERENCES findings(id),
    component_id    TEXT REFERENCES strategies(id),
    sub_target_id   TEXT NOT NULL REFERENCES sub_targets(id),
    source_encounter_id TEXT REFERENCES appointments(id),
    source_provider_id  TEXT REFERENCES providers(id),
    author          TEXT CHECK (author IN ('Provider','Matt','Louise','System')),
    date            TEXT NOT NULL,
    note            TEXT,
    status_read     TEXT CHECK (status_read IN
                      ('Still-active','Working-stated','Not-working-stated','Discontinued-stated','New-proposed')),
    status_superseded INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','invalidated')),
    invalidated_reason_class TEXT CHECK (invalidated_reason_class IN
                      ('not-an-event','wrong-fact-replaced','duplicate','superseded-by-correction')),
    invalidated_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_stratobs_subtarget_date ON strategy_observations (sub_target_id, date);

-- ============================================================
-- THE CHANGE-LOG SPINE  (append-only, dated; written ONLY via the gate)
-- ============================================================

CREATE TABLE IF NOT EXISTS benchmark_change_log (
    id              TEXT PRIMARY KEY,
    title           TEXT,
    sub_target_id   TEXT NOT NULL REFERENCES sub_targets(id),
    change_type     TEXT NOT NULL CHECK (change_type IN
                      ('Progression','Regression','Addition','Baseline','Correction','Revert')),
    from_value      TEXT,
    to_value        TEXT,
    effective_date  TEXT NOT NULL,             -- the OBSERVATION date that drove it
    triggering_observation_ids TEXT,           -- JSON array
    confirmed_by    TEXT CHECK (confirmed_by IN ('System-candidate','Matt-approved')),
    candidate_id    TEXT REFERENCES candidates(id),
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_change_log (
    id              TEXT PRIMARY KEY,
    title           TEXT,
    component_id    TEXT REFERENCES strategies(id),
    sub_target_id   TEXT NOT NULL REFERENCES sub_targets(id),
    change_type     TEXT NOT NULL CHECK (change_type IN
                      ('Added','Adjusted','Discontinued','Achieved','Correction','Revert')),
    from_value      TEXT,
    to_value        TEXT,
    reason          TEXT,
    effective_date  TEXT NOT NULL,
    source_encounter_id TEXT REFERENCES appointments(id),
    confirmed_by    TEXT CHECK (confirmed_by IN ('System-candidate','Matt-approved')),
    candidate_id    TEXT REFERENCES candidates(id),
    created_at      TEXT NOT NULL
);

-- Append-only enforcement (both change logs)
CREATE TRIGGER IF NOT EXISTS bcl_no_update BEFORE UPDATE ON benchmark_change_log
  BEGIN SELECT RAISE(ABORT, 'benchmark_change_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS bcl_no_delete BEFORE DELETE ON benchmark_change_log
  BEGIN SELECT RAISE(ABORT, 'benchmark_change_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS scl_no_update BEFORE UPDATE ON strategy_change_log
  BEGIN SELECT RAISE(ABORT, 'strategy_change_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS scl_no_delete BEFORE DELETE ON strategy_change_log
  BEGIN SELECT RAISE(ABORT, 'strategy_change_log is append-only'); END;

-- ============================================================
-- DECISION I — THE CANDIDATES TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS candidates (
    id              TEXT PRIMARY KEY,
    change_class    TEXT NOT NULL CHECK (change_class IN (
                      'benchmark-change','benchmark-correction','benchmark-revert',
                      'assessment-correction','adjacent-promotion','spin-out',
                      'strategy-diff','strategy-status-correction')),
    origin          TEXT NOT NULL CHECK (origin IN ('system','manual')),

    target_subtarget_id    TEXT REFERENCES sub_targets(id),
    target_observation_id  TEXT REFERENCES observations(id),
    target_strategy_id     TEXT REFERENCES strategies(id),
    target_strategy_obs_id TEXT REFERENCES strategy_observations(id),

    from_value      TEXT,
    to_value        TEXT,
    reason          TEXT NOT NULL,

    source_finding_ids     TEXT,               -- JSON array
    source_observation_ids TEXT,               -- JSON array
    triggering_rule        TEXT,
    confidence             TEXT CHECK (confidence IN ('high','medium','low')),

    status          TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','approved','rejected','withdrawn')),
    reject_reason_class TEXT CHECK (reject_reason_class IN (
                      'right-call-wrong-moment','wrong-assessment','not-a-real-finding')),
    correction_reason_class TEXT CHECK (correction_reason_class IN (
                      'defensible-but-wrong','misgrade','wrong-anchor','wrong-fact')),
    decision_note   TEXT,
    decided_by      TEXT,
    backfill        INTEGER NOT NULL DEFAULT 0,

    created_at      TEXT NOT NULL,
    decided_at      TEXT,

    resulting_log_table TEXT,
    resulting_log_id    TEXT
);

CREATE INDEX IF NOT EXISTS idx_cand_status_subtarget ON candidates (status, target_subtarget_id);

-- ============================================================
-- HEALTH ACTIONS (reused, re-anchored to sub-target)
-- ============================================================

CREATE TABLE IF NOT EXISTS health_actions (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    source_appointment_id TEXT REFERENCES appointments(id),
    provider_id     TEXT REFERENCES providers(id),
    sub_target_id   TEXT REFERENCES sub_targets(id),
    strategy_id     TEXT REFERENCES strategies(id),
    assigned_to     TEXT CHECK (assigned_to IN ('Matt','Louise','Family','Provider','Doc','School','Other')),
    category        TEXT,
    priority        TEXT CHECK (priority IN ('High','Medium','Low')),
    status          TEXT CHECK (status IN ('Open','In Progress','Done','Cancelled','Needs Triage')),
    due_date        TEXT,
    opened_date     TEXT,
    closed_date     TEXT,
    ndis_relevant   INTEGER DEFAULT 0,
    notes           TEXT
);

-- ============================================================
-- APP-INFRA & AUDIT (1c)
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin','carer')),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recompute_audit (
    id              TEXT PRIMARY KEY,
    observation_id  TEXT NOT NULL REFERENCES observations(id),
    old_grade       TEXT,
    new_grade       TEXT,
    trigger         TEXT NOT NULL,             -- data-load-advance / correction / report-retraction
    triggering_candidate_id TEXT REFERENCES candidates(id),
    created_at      TEXT NOT NULL
);
"""


# Additive migrations applied after the base schema (idempotent; guarded by
# PRAGMA table_info so re-running is safe). Append-only — never edit past entries.
_MIGRATIONS = [
    # candidate carries the specific change_type (Progression/Regression/Addition/
    # Correction/Baseline/Revert) so the approve handler can write the change log.
    ("candidates", "change_type", "ALTER TABLE candidates ADD COLUMN change_type TEXT"),
    # source file/message ref for the data-load dedup + resumability.
    ("appointments", "source_ref", "ALTER TABLE appointments ADD COLUMN source_ref TEXT"),
]


def _apply_migrations(conn) -> None:
    for table, column, ddl in _MIGRATIONS:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        if column not in cols:
            conn.execute(ddl)


def init_db(conn) -> None:
    """Apply the full schema + additive migrations (idempotent)."""
    conn.executescript(SCHEMA_SQL)
    _apply_migrations(conn)
    conn.commit()


# Tables we expect to exist after init_db — used by the connectivity check.
EXPECTED_TABLES = [
    "providers", "goal_pages", "appointments", "appointment_providers", "sub_targets",
    "findings", "observations", "strategies", "strategy_observations", "benchmark_change_log",
    "strategy_change_log", "candidates", "health_actions", "users", "recompute_audit",
]


if __name__ == "__main__":
    from src.db.store import connect

    conn = connect()
    init_db(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = [r[0] for r in rows]
    print(f"Initialised DB with {len(names)} tables:")
    for n in names:
        print(f"  {n}")
    missing = [t for t in EXPECTED_TABLES if t not in names]
    print("OK — all expected tables present." if not missing else f"MISSING: {missing}")
    conn.close()
