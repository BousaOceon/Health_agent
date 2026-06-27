# Health Agent — Design Reference

**Project:** Personal Health Coordination Agent
**Status:** Design complete; both Phase 1c blockers closed (Decision A — sub-target spine — 25/06/2026; Decision I — candidate schema + data layer — 27/06/2026). Build sequenced from Phase 1c; the structural build is unblocked pending the five gap-blank seed values (Section 25).
**System of record:** Local SQLite on the Pi; Flask dashboard as UI; nightly off-box backup from day one; a one-way Notion mirror of generated reports is optional and deferred. The physical outcome-layer schema and the full gated-change engine are specified in `decision-I-sqlite-schema.md` — the authoritative Phase 1c/1d build spec; this document is the conceptual/architectural source of truth and defers to the schema doc for physical table definitions.
**Subject of care:** Tom (7, born Dec 2018) — multiple allied-health providers, on the NDIS

---

## 1. Project Overview

An automated agent running on a Raspberry Pi that ingests appointment reports and notes from two Gmail accounts, maintains a structured health knowledge base in a **local SQLite database on the Pi** (the system of record), and produces pre-appointment briefs, weekly digests, framework-projected reporting (NDIS annual and the Victorian school DIP review), and a natural-language query interface over the full health record. A **local Flask web dashboard** is the primary control and review interface on the home network. Notion is no longer the data store — its only optional, deferred role is a one-way mirror of generated reports for mobile browse/share (Section 3.0).

The system is organised around **NDIS goals as the spine** — more precisely, around the **sub-target** as the durable working unit. Appointments are evidence; goals and the school/NDIS frameworks are *projections* of the same underlying observations. This matches how the household's existing work/project system already operates: goals are workstreams, encounters are meeting notes, observations are the distilled record, the benchmark is current state, strategies are the plan, and actions are the tasks.

### Core outputs

- **Pre-appointment briefs** — goal-structured, generated ahead of each appointment; also a consistency forcing-function and a live-capture surface (Section 14)
- **Weekly health digest** — emailed to both household members
- **Weekly agent performance review** — interactive dashboard page for the primary user
- **NDIS annual reporting** and **DIP (school) review data** — two saved views over one dataset, on demand
- **Monday bridge task** — written to the primary user's existing Notion task database each week
- **Natural-language query interface** with session write-back
- **Local web dashboard** — Pi-hosted, home network only

### Primary users

- **Primary user / owner:** Matt — lead designer and operator
- **Secondary user:** Louise — receives digests and relevant briefs by email; no Notion access required; can trigger agent actions via email subject patterns
- **Subject:** Tom — see the Standing Extraction Context (Section 9) and the static Health Summary (Section 20)

---

## 2. The architectural model — three layers

The system separates *what arrived* from *where Tom is* from *the reasoning that connects them*.

| Layer | Object | Authoritative for |
|---|---|---|
| **Evidence** | Encounter record (Appointments) | What arrived, from whom, when; raw text; source email; deduplication |
| **Outcome** | Goal pages · Sub-targets/Benchmarks · Observations · Strategies · Actions | Where Tom is, what we're working on, what has changed |
| **Engine** | Assessment · benchmark-change · promotion · strategy-diff logic | Judging observations against the benchmark; promoting gaps and adjacents; reconciling the strategy inventory |

The **finding** is the bridge between evidence and outcome: a single discrete thing a clinician (or family member) said, which fans out into one or more goal-scoped observation records (Section 5).

The encounter record is authoritative for provenance and stays load-bearing for ingestion, deduplication and retrieval. The **durable, queryable, conversation-ready object is the sub-target page** — the unit a brief, an NDIS report, or a query answer is actually built from.

### 2.1 What a "goal" is here

A goal page is any tracked outcome area framed in goal format. Three kinds, all using the same machinery:

1. **Active NDIS goals (6)** — Self-Care Independence, Language and Communication, Play Skills, Feelings and Emotions, Gross Motor Skills, School Environment. Full benchmark assessment.
2. **Medical** — framed as "Tom remains generally healthy within the known limits of his diagnoses." Sub-targets are watch/focus domains (gastro, dental, growth, dysphagia/airway, continence). Read on a **status axis** rather than a capability axis (Section 11).
3. **Other** — a single page whose scope is defined *by exclusion*: developmentally or clinically relevant findings not covered by a current goal area. Candidate domains (e.g. Fine Motor Skills — a former NDIS goal, not in the current plan) live **inside it as sub-target rows**, not as their own pages (Section 2.2).

**The goal is a projection, the sub-target is the spine.** A goal is *mutable* — a sub-target can be re-projected across NDIS, DIP, and paediatric lenses, or spun out of Other into its own page. The sub-target is the stable thing everything anchors to: benchmark, observations, strategies, history. So the **sub-target row is the rich working page**, and the goal demotes to a summarised roll-up *over* sub-targets (Section 4.1).

### 2.2 The Other page

`Other` is one row in Goal Pages. Its candidate domains are sub-target rows pointing at it:

- **Seeded candidate domains** (Decision A seed list — Section 3.2) are sub-target rows with `Goal → Other`, `Status: Adjacent-watch`, `NDIS: false`, and **no benchmark** (a benchmark is written only on promotion to Active). Observations mapping to one of these are logged against it and assessed `Adjacent` (N/A — there is no benchmark to judge against until promotion).
- **The residue** — a finding matching nothing, not even a seeded Other sub-target — lands on a single `Unclassified` sub-target inside Other, logged with its verbatim anchor. This is the only place loose, unstructured findings pool, and it is deliberately the last resort. It is reviewed **to be emptied**: each periodic review either promotes a cluster out of it into a real Other sub-target, or confirms an item was genuinely incidental and lets it rest. A holding pen, not a home.

Everything that is a real finding gets a structured, anchored home; the worst case is `Other / Unclassified`, which is still searchable and still reviewed. The encounter summary is **not** a capture fallback (Section 6.1).

### 2.3 Frameworks are projections, not the spine

Goal pages are the evidence base; NDIS, the Victorian DIP, and the paediatrician summary are all *projections* of the same observations through different domain lenses. NDIS annual wants the 6 plan goals; the DIP review wants its 6 ICF-based domains; the paediatrician wants everything. Because the school review explicitly accepts documentation the school already holds rather than fresh assessments, the agent's accumulated evidence is exactly what a DIP review consumes.

Mechanically, **each sub-target carries a `DIP domain` tag and an `NDIS-outcome domain` tag** (Section 3.2). A DIP-prep report is generated the same way as the NDIS report — same observation data, re-grouped by DIP domain instead of plan goal. Fine Motor observations that are adjacent/dormant for NDIS-plan purposes become first-class evidence under the DIP's Self-Care/Mobility domains. The 2-yearly DIP review and the annual NDIS review are two saved views over one dataset, not separate reconstructions.

**The three frameworks:**

- **NDIS Outcomes Framework** — 8 life-outcome domains; for Tom's school-age-to-14 cohort the relevant ones are Daily living, Lifelong learning, Relationships, Social & community participation, and Health & wellbeing. These are broad life areas, not the granular skills the plan goals track.
- **ICF** (International Classification of Functioning) — the underlying allied-health framework both others rest on.
- **Victorian Disability Inclusion Profile (DIP)** — the school plan, reviewed roughly every 2–3 years; 6 ICF-based domains across 31 activities: Learning & Applying Knowledge, General Tasks & Demands, Communication, Mobility, Self-Care, Interpersonal Interactions.

**SSG goals are a projection lens carried as a light optional tag** (Decision A 25/06/2026, refined 27/06/2026). The school's termly Student Support Group goals — Independence, Participation, Emotional Regulation — are a re-grouping of the *same* existing sub-targets through a school-side lens, regenerated each term. They add **no new database structure** and no benchmark machinery: like NDIS and DIP, an SSG view is a saved roll-up over the sub-target spine. But rather than recompute the grouping each term, a sub-target carries an **optional single-select `SSG` tag** (one of Independence / Participation / Emotional Regulation, or none) — exactly the cheap mechanism the DIP tag uses — so the termly roll-up reads a tag instead of re-deriving the grouping. Still a lens, just a tagged one.

---

## 3. Database map

### 3.0 System of record — local SQLite on the Pi

The data store is a **local SQLite database on the Pi**, not Notion (Decision, 27/06/2026). The engine operations (Pass 2 reconciliation, cadence/staleness, archive eligibility) are aggregate queries over dated rows; the Findings → Observations → Sub-targets → Change-Log model is ~1:1 with relational tables; and correction handling needs *atomic recompute*, which a Notion-backed store structurally cannot do. The **Flask dashboard** is the UI (status, Candidates review, sub-target pages, query). A **nightly off-box SQLite backup** is the disaster-recovery line — non-negotiable from day one. A **one-way Notion mirror** of generated reports (mobile browse + share-a-report) is optional and deferrable; build it only if mobile browse genuinely nags.

This shift makes the earlier Notion-MCP data-isolation mitigation largely moot: engine data never enters Notion, so there is no cross-role MCP-exposure surface to sever (Section 23). The Pi agent talks to its local DB through code, not through an MCP connector.

**Schema authority.** The structures below are the **logical** model. Their **physical** definitions — SQLite DDL, `CHECK` constraints, indexes, append-only triggers, the Candidates table, and the gated-change engine — are specified in `decision-I-sqlite-schema.md` (the Phase 1c/1d build spec). Where this document's per-field tables (Section 16) and the schema doc differ in detail, **the schema doc is authoritative for the physical build**; the design doc carries the rationale. Reconciling residual field-level divergence between the two is a build-time step, not chased exhaustively here. The terms "database," "table," "page," and "row" below describe the logical model; physically they are SQLite tables and rows surfaced through the Flask dashboard (and, optionally, mirrored to Notion pages).

### 3.0.1 Structure map

The outcome layer adds nine structures. The evidence and supporting structures from the front half persist.

```
EVIDENCE LAYER
└── Appointments (Encounters)     — Providers multi-relation; Sub-targets Touched; Findings rollup

OUTCOME LAYER
├── Sub-targets                   — THE working page (one row = one page); benchmark + as-of + projection tags + embedded views
├── Goal Pages                    — summarised roll-up over sub-targets
├── Benchmark Change Log          — dated, append-only; every regression / progression / addition / baseline
├── Strategy Change Log           — dated, append-only; every component add / adjust / discontinue / achieve
├── Findings                      — one row per discrete clinician statement (the fan-out parent)
├── Observations                  — benchmarked-capability datapoints; sub-target-anchored, assessed
├── Strategy Observations         — strategy running log; every mention incl. "still trying, no change"
├── Strategies                    — one row per component; inventory maintained by set-diff
├── Health Actions                — reused; now tags to SUB-TARGET and/or strategy component
└── Candidates                    — propose → approve queue; one typed table, all change types feed it (Decision I, RESOLVED — Section 17)

SUPPORTING (reused)
├── Providers
├── Agent Performance Log
├── Health Actions Archive
└── Health Summary (static document)
```

**The two running logs never join in the assessment logic.** The benchmark reconciliation pass (Section 6) reads **only** the Observations table. Strategy Observations are a deliberately separate store, so strategy mentions can never be swept into that aggregation and fabricate a progression from "still trying B." This is structural insulation — there is no `type != strategy` filter to forget, because they are different tables. They share only the Findings spine, so a strategy-observation and a benchmark-observation from the same sentence remain bindable for sibling-coherence.

### 3.1 The sub-target is the working page; the goal is a roll-up

The spine is the sub-target, not the goal. A goal is mutable; the sub-target is the stable thing everything anchors to. The **sub-target is the rich record** — its dashboard page renders the benchmark, the embedded per-sub-target views, and the history — and the goal is a summary view over sub-targets, which is exactly what a goal is in the projection model (Section 2.3): a lens, not a container. (In an optional Notion mirror, the sub-target row maps to a page with the same embedded views; the Flask dashboard renders the equivalent views directly over SQLite.)

**Sub-target page (the row's body)** — for one sub-target, everything scoped to it on one page:

| Section | Content |
|---|---|
| Header fields | Goal(s) it serves (NDIS goal + DIP domain + NDIS-outcome tags); target; current benchmark + as-of date; short active-strategy summary |
| Observations | Embedded view of Observations filtered to this sub-target, newest first |
| Strategy Observations | Embedded view of the strategy running log for this sub-target |
| Strategies | Embedded view of components for this sub-target: Active / Inactive (+ why) / Achieved |
| Benchmark history | Embedded Benchmark Change Log for this sub-target |
| Strategy history | Embedded Strategy Change Log for this sub-target |

Because the sub-target is the unit, every embedded view is already scoped — no separate reference or synthetic table is needed; the row-as-page gives the per-sub-target views for free.

**Goal Page (the roll-up).** A light page whose body is a summarised digest: a current-state paragraph per sub-target (including its active strategies in brief), plus metrics of interest (e.g. sub-targets moved this quarter, stale sub-targets). It is a *view over* sub-targets, maintained by Haiku, not their home. Goal scope still lives here (it bounds Tier-2 adjacency). Because each sub-target carries goal / DIP / NDIS-outcome tags, the same sub-targets roll up into NDIS, DIP, or paediatric digests — different roll-ups, one set of pages.

### 3.2 Sub-targets

The structural heart. The benchmark lives in **addressable rows** (not goal rich-text), and each row *is* the working page above.

| Field | Type | Notes |
|---|---|---|
| Title | Title | e.g. "SC · Dressing — upper body". Carries enough context to understand the sub-target's application at a glance (it is the primary routing signal at extraction — Section 9.1). The `XX ·` lead-in is a display convention for scannability, not a governing field — the authoritative grouping is the Goal relation. |
| Goal | Relation → Goal Pages | The grouping tag (mutable — re-pointed on spin-out). Goal is denormalised onto child records from here. One NDIS-goal per row (single-tag rule). |
| DIP domain | Select | The Victorian DIP domain this sub-target informs (Learning & Applying Knowledge / General Tasks & Demands / Communication / Mobility / Self-Care / Interpersonal Interactions). One per row. Enables DIP-projected reporting. |
| NDIS-outcome domain | Select | The NDIS Outcomes Framework domain (Daily living / Lifelong learning / Relationships / Social & community participation / Health & wellbeing). One per row. Sits alongside DIP for NDIS-outcome-projected views. |
| SSG | Select (optional) | The termly Student Support Group lens (Independence / Participation / Emotional Regulation), or none. A light single-select so the SSG roll-up reads a tag (Section 2.3). |
| Reporting subgroup | Select (optional) | Any goal-internal sub-grouping used for a reporting roll-up, where one exists. Tagged only when a specific subgroup matters for a report. |
| Scope line | Text | A short discriminating description of what this sub-target covers — injected at extraction alongside the title to route facts to the right sub-target, especially to separate near-neighbours (e.g. the three Safety splits). |
| Current Benchmark | Text | Present-state description of where Tom is on this sub-target. Injected at the **assessment** step (post-confirmation), not at extraction (Section 9.2). |
| Benchmark As-Of | Date | Date this benchmark line was last confirmed or changed. |
| NDIS | Checkbox | True = formal current-plan sub-target; False = tracked-but-informal. |
| Status | Select | Active / Adjacent-watch / Achieved / Dormant. |
| Severity | Select | (Medical only) None / Watch / Safety-critical — drives escalation. |

**Tags are per-framework, each single-valued.** A sub-target carries **one** NDIS-goal, **one** DIP domain, **one** NDIS-outcome domain, and **optionally one** SSG tag — single *per axis*, not single *in total*. This is the form of Decision A's single-tag rule: the split-don't-merge decisions guarantee one value per framework; adding more frameworks (DIP, NDIS-outcome, SSG) just adds more single-valued axes.

**Status semantics:** `Active` has a benchmark and is assessed normally. `Adjacent-watch` is a candidate domain (usually under Other) with no benchmark — observations are logged as `Adjacent` / N-A until promotion. `Achieved` / `Dormant` are retired but retained for history. Promotion (Adjacent-watch → Active) writes the first benchmark as a Baseline change-log entry; the sub-target then assesses normally and its prior observations retroactively become its history — no re-tagging, because they already point at this sub-target (Section 6.3).

**Grouping is by relation/tag, not by an identity prefix.** A sub-target carries several *framework* groupings at once — one NDIS goal, one DIP domain, one NDIS-outcome domain, optionally one SSG — and these frameworks need not align. (For example, the **School Environment goal's sub-targets distribute across two DIP domains** — Learning & Applying Knowledge and General Tasks & Demands — via several rows, each single-tagged; it is the *goal's set* that spans two DIP domains, not any one row carrying two DIP tags.) A single embedded prefix could encode only one of these groupings, so grouping is done by relation/tag — pick the projection per view. The `XX ·` lead-in in the title is a display convention only. Spinning a sub-target out of Other is a one-field Goal re-point and never re-labels it.

**Informal sub-targets are tracked, NDIS-flagged.** The system tracks a broader list than the formal NDIS sub-targets and flags each with `NDIS: true/false`. A recurring informal sub-target — one that accumulates a year of data — is exactly the signal that justifies formal inclusion at plan review. The flag keeps the formal list clean for reporting while letting the broader list accumulate.

### 3.2.1 The sub-target spine — RESOLVED (Decision A, 25/06/2026)

The spine is fixed at **36 sub-targets**, built by gap-analysis of the live NDIS Goals DB (6 goals / 23 sub-targets) against the authentic Victorian DIP Functional Needs Domain Table (6 domains / 31 activities). Composition:

- **25 goal-area** sub-targets (under the 6 NDIS goals)
- **4 Other** candidate domains (Adjacent-watch)
- **5 Medical** watch domains
- **2 holding pens** — `Other / Unclassified` and `Other medical / watch` (Section 2.2, Section 11)

**Single-tag rule.** Every sub-target carries exactly **one NDIS-goal tag and one DIP-domain tag** — the "split-don't-merge" decisions below removed all multi-tags, so routing is deterministic and every observation has one clean home on each axis. The full deliverable — the 36-row table, the 8 carved benchmarks, and the routing + capture-screen rules — lives in the filed note *Health Agent — Decision A / sub-target spine — 25/06/2026* and is the seeding source for Phase 1c.

**The split-don't-merge decisions** (each preserves the single-tag rule by splitting a capability that spanned settings or axes, rather than carrying a multi-tag):

- **"Manage big behaviours" → three sub-targets** — Self-regulation & coping / Change & transition tolerance / Social-emotional understanding. Feelings was the lone single-sub-target goal and a high-focus area; the split gives working resolution and one clean DIP tag each (2× General Tasks & Demands, 1× Interpersonal Interactions).
- **Safety split on setting (not merged)** — Personal safety awareness (Self-Care; everyday/home/community), Environment safety scanning (Play; while-absorbed), Danger awareness in new environments (School; unfamiliar/busy). Same capability, distinct settings + facets; benchmarks tightened so routing is deterministic.
- **Endurance split on axis** — Stamina & range (physical exertion; Gross Motor / DIP Mobility) vs Build fatigue levels (sustained participation; School / DIP General Tasks). The thinnest split — a future merge would reintroduce a multi-NDIS-goal tag, so the merge option stays designed-but-unused.

**The 4 Other candidate domains** (Adjacent-watch sub-targets under Other, no benchmark until promotion): **Fine Motor** (ICF fine hand use; former goal), **General Tasks & Demands** (executive/routine/transition dimension — significant for an ASD profile, previously only implicit under Feelings + School), **Cognition / Learning** (Tom's documented processing-speed and visual-spatial profile, with no goal home), and **Sleep** — reclassified Medical → Other (OT is working independent sleep-onset strategies, so it is a capability sub-target with a strategy inventory, not a medical watch domain; seeded **Active**, as it has live OT info, not Adjacent-watch). Community participation was folded into existing Play/School coverage rather than seeded as a fifth Other domain.

**The 5 Medical watch domains:** dysphagia/airway, gastro, dental, growth, continence (continence sits under Medical, not Other). Read on a status axis with a `Severity` flag (Section 11).

> Five sub-targets still need a seed-state value before the two-anchored data load (Section 8): **Fine Motor** (current level), **Continence-medical**, **Gastro**, **Dental**, **Growth** — the data may be in unseen reports or the domain is genuinely quiet. These five gap-blanks block the *data load* (Phase 1d), **not** the *structural build* (Phase 1c). See Section 25.

### 3.3 Benchmark Change Log

Append-only, dated. This is the mechanism that gives the data load order-independence and an auditable trail.

| Field | Type | Notes |
|---|---|---|
| Title | Title | Auto: "Sub-target — change type — date" |
| Sub-target | Relation → Sub-targets | |
| Change Type | Select | Progression / Regression / Addition / Baseline |
| From | Text | Prior benchmark text (empty for Baseline / Addition) |
| To | Text | New benchmark text |
| Effective Date | Date | The observation date that drove the change (not the processing date) |
| Triggering Observations | Relation → Observations | The record(s) that drove it |
| Confirmed By | Select | System-candidate / Matt-approved — nothing edits a benchmark without passing through candidate → approved |

**Cadence analytics (derived).** Because every change is dated, the log supports per-sub-target temporal analysis valuable in its own right: time-between-changes, clustered changes, and especially **staleness detection** — "this sub-target hasn't moved in 6 months." Staleness is not just a statistic; it is a candidate *action*: the agent can raise "GM-balance flat for 6 months → consider booking OT time to target it," feeding the periodic review surface (Section 6.4) and optionally generating a suggested Health Action. Long gaps, change clusters, and which sub-targets move together are exactly the patterns a plan-review or focus-setting conversation wants.

### 3.4 Strategy Change Log

Parity with the Benchmark Change Log. In-place edits to a component row would lose history — "why did we adjust C to C′ in March, what was C before, and why was A dropped?" is exactly the reasoning a plan review or a new provider wants, and it must not be overwritten. Every component change appends a dated entry here; the component row holds *current* state, the log holds *how it got there*.

| Field | Type | Notes |
|---|---|---|
| Title | Title | Auto: "Component — change type — date" |
| Component | Relation → Strategies | The component changed |
| Sub-target | Relation → Sub-targets | Denormalised, for sub-target-grouped review |
| Change Type | Select | Added / Adjusted / Discontinued / Achieved |
| From | Text | Prior definition/status (empty for Added) |
| To | Text | New definition/status |
| Reason | Text | The stated rationale ("poor fit for Tom," "C′ more effective") — verbatim-anchored where possible |
| Effective Date | Date | The encounter date that drove the change |
| Source Encounter | Relation → Appointments | |
| Confirmed By | Select | System-candidate / Matt-approved |

The set-diff (Section 7.2) writes candidate entries here; nothing mutates a component without a corresponding approved log entry, exactly as benchmark changes work. This makes the strategy history queryable ("what have we tried for dressing over the year, and why did each stop?") — a first-class output, not reconstructable-from-memory.

### 3.5 Findings (the fan-out parent)

One row per discrete clinician statement. Usually invisible in daily use, but structurally load-bearing — it binds fanned observations and enables deduplication and reconciliation.

| Field | Type | Notes |
|---|---|---|
| Title | Title | Short verbatim-anchored fragment of the source statement |
| Source Encounter | Relation → Appointments | |
| Source Fragment | Text | The anchored fact — held constant across all child observations |
| Finding ID | Text/ID | Stable ID; survives reprocessing |
| Fan-out Rationale | Text | Why this finding was split as it was — which sub-targets recorded vs only touched, and why (written at extraction). Serves performance review and prompt tuning. |
| Fan-out Confidence | Select | high / medium / low — the model's confidence in the fan-out split. Low-confidence splits are a tuning and review signal. |
| Child Observations | Relation → Observations | The fan-out |

The delimitation rule for "what is one finding" (clinical claim vs sentence vs clause) is prompt-tuning, settled against real reports in Phase 1d.

### 3.6 Observations (fanned, assessed children)

Recorded **broadly** (Section 6.1). Each observation is **anchored to a sub-target**, with the goal denormalised onto the record. This matters: because the relation of record is to the *sub-target*, promoting a sub-target out of Other into its own goal page is a one-field re-point, and the whole observation history travels with it. Relating directly to the goal would force a bulk re-tag on every promotion.

| Field | Type | Notes |
|---|---|---|
| Title | Title | Auto: "Sub-target — date" |
| Finding | Relation → Findings | Provenance + sibling binding |
| Sub-target | Relation → Sub-targets | **The relation of record.** Named sub-target, an Adjacent-watch sub-target, or Other/Unclassified |
| Goal | Relation → Goal Pages | Denormalised from the sub-target's Goal, for fast goal-page views; re-derived if the sub-target is re-pointed |
| Source Encounter | Relation → Appointments | Denormalised for brief queries |
| Source Provider | Relation → Providers | Only when Author = Provider |
| Author | Select | Provider / Matt / Louise / System |
| Date | Date | Appointment/observation date |
| Note | Text | Goal-specific framing wrapped around the constant source fragment |
| Assessment | Select | Lower / At / Above / Gap / Adjacent (see below). **Null at creation** — extraction writes an unassessed shell; Pass 1 populates this at confirmation (Section 6). |
| Assessment Rationale | Text | Why this assessment value was assigned — e.g. "judged Above: unprompted completion across two settings vs the benchmark's 'with verbal prompts'" (written at **Pass 1 / confirmation**, when the grade is assigned; frozen thereafter, never overwritten on later correction). Serves performance review and prompt tuning; supports the reject-with-correction path (Section 17). |
| Assessment Confidence | Select | high / medium / low — the model's confidence in the assigned value. A run of low-confidence `At`s on one sub-target is a detectable smell for an under-assessed true progression. |
| Milestone | Checkbox | First-time / formal-assessment marker (co-exists with Assessment) |
| Benchmark As-Of (at obs) | Date | The benchmark date this was judged against — frozen at assessment time (empty for Adjacent) |

**Assessment values.** `Lower` / `At` / `Above` require a benchmark to judge against. `Gap` = the observation falls clearly inside a *named* sub-target but its benchmark is silent on this case → drives a **benchmark-extension** review. `Adjacent` = the observation is within a goal's scope (or in Other) but maps to *no* sub-target with a benchmark → assessment N/A → drives a **new-sub-target** review. Both are always logged; they are deliberately distinct because they trigger different promotions at different grains (Section 6.4). Pooling them into one value would merge two different review queues that produce two different artifacts.

### 3.7 Strategies — a maintained inventory

A strategy has no "correct" state to converge on. The benchmark tracks *Tom's state* (evidence-driven, has a correct value, converges); a strategy tracks *our intent* (decision-driven, fluid, has only a current value). So a strategy is **not** assessed against a target the way an observation is assessed against a benchmark. It is a **maintained inventory** of what we are currently doing, and the only operation is to reconcile what an encounter says about tactics against what is currently logged. The target lives on the sub-target benchmark; the strategy lists the tactics aimed at it.

**Two levels.** A **strategy set** is 1:1 with a sub-target — "how are we working on this right now." It contains one or more **components** (tactics) — the visual schedule, the timer, the first-then board. "Try this and this and this" = three components in one set. This mirrors the sub-target↔benchmark-line relationship one level down: a set holds components the way a sub-target holds benchmark lines; add/keep/adjust operate per component, the parent persists.

**The set is not a table.** There is **one** Strategies database, holding **one row per component**, each related to its sub-target. The "set" is simply the filtered view of components sharing a sub-target — a query, not a second table (the same pattern as benchmark lines: the Sub-targets DB holds the lines; there is no separate "benchmark set" table).

| Field | Type | Notes |
|---|---|---|
| Title | Title | The component/tactic, e.g. "Visual schedule for school-morning transitions" |
| Sub-target | Relation → Sub-targets | The set anchor (goal denormalised). All components on one sub-target form its set |
| Status | Select | Active / Inactive-didn't-work / Inactive-superseded / Achieved |
| Definition | Text | What the tactic is / how it is done — what an `adjust` edits |
| Introduced | Date | |
| Last Referenced | Date | Updated on every encounter mention, *including unchanged ones* — resets the staleness clock |
| Introduced By | Relation → Providers | |
| Source Encounter | Relation → Appointments | The encounter that introduced it |
| Effectiveness / Context | Text | **Stated-only.** Qualitative notes captured when an encounter or family explicitly comments. Never inferred (see below) |
| Outcome Note | Text | Why it went inactive — populated on retirement |
| Supporting Actions | Relation → Health Actions | One-off actions that enable this component |

**Effectiveness is stated, never inferred.** With multiple components running together, sub-target movement cannot be decomposed into "component B did 60% of it" — that is confounded and the data will never support it. So:

- **Aggregate effectiveness** ("is the set working?") lives on the **sub-target's observations** — a flat benchmark while components are active *is* the not-working signal, attributed to the set as a whole.
- **Per-component effectiveness/context** is captured only when an encounter or family **explicitly states it** ("C′ works better," "B is for high-arousal moments"). This is the common and valuable "which tactics work, in what situations, what to change" discussion — it gets a dated, sourced home.
- **No derived correlation.** The agent does not compute "which component was active when the benchmark moved." Low value, high error, and recoverable on demand: if that view is ever wanted, the query interface can interrogate the stored observations + lifecycle dates at the moment it matters.

**Retirement-by-neglect is human-driven.** A tactic quietly stops being mentioned. The agent **never** infers discontinuation from silence (silence = keep). The staleness clock (`Last Referenced` vs now) surfaces it — "B is Active but cold for 4 months — retire?" — to the user, via the periodic review and the pre-appointment brief (Section 14). The user decides. This is why logging the unchanged mention matters: without it you cannot tell "still actively using B" from "B forgotten." Encounters drive additions and *stated* changes; the user drives retirement-by-neglect, agent-flagged.

Brief salience is driven by **timing** (recently added or changed) and **last-appointment coverage**, not by any trial/established status flag.

### 3.8 Strategy Observations (the strategy running log)

The benchmark lane has two logs — Observations (every reading, including `At`) and the Benchmark Change Log (only when the benchmark moves). The strategy lane mirrors that, or it loses the "still working / still trying, no change" datapoint that `Last Referenced` alone cannot preserve (a date stamp is not a record, and is overwritten). So a strategy mention **always** writes a Strategy Observation row (the running log), and *separately* — only when the mention constitutes a change — writes a Strategy Change Log entry. Exactly parallel to: an observation always records, and *may* additionally trigger a benchmark change.

| Field | Type | Notes |
|---|---|---|
| Title | Title | Auto: "Component (or sub-target) — date" |
| Finding | Relation → Findings | Provenance + sibling binding (shared spine with Observations) |
| Component | Relation → Strategies | The component referenced (empty if the mention is about the set generally or a not-yet-matched tactic) |
| Sub-target | Relation → Sub-targets | Always set (goal denormalised) |
| Source Encounter | Relation → Appointments | |
| Source Provider | Relation → Providers | When Author = Provider |
| Author | Select | Provider / Matt / Louise / System |
| Date | Date | |
| Note | Text | "Still using B, no change" / "tried D today" / "C not working in transitions" — verbatim-anchored |
| Status read | Select | Still-active / Working-stated / Not-working-stated / Discontinued-stated / New-proposed |

`Status read` carries a *status*, not a magnitude — a strategy observation has no benchmark *level* to grade against. That is the only difference in shape from a benchmark observation; the "record every datapoint, change-log only on change" skeleton is identical.

**Critical separation:** Strategy Observations are a separate database from Observations. The benchmark reconciliation pass (Section 6) reads only Observations; it must never see strategy rows, or it would count "still trying B" as a capability reading and fabricate a progression. Two databases make that structurally impossible. Both still share the Findings spine, so a strategy-observation and a benchmark-observation from the same sentence remain bindable for sibling-coherence.

### 3.9 Health Actions (reused, re-anchored)

Re-anchored to the **sub-target** (not the goal), for the same reason observations are: a sub-target re-projected NDIS↔DIP carries its actions with it, and any report sharing the sub-target picks them up. Full schema in Section 16 (Database 2). The outcome-layer deltas over the front-half schema: a `Sub-target` relation (goal denormalised) and a `Strategy` relation (the action supports a specific component); the `Provider` single-relation is kept.

Actions remain **single events** ("buy the visual schedule board"); strategy components are **ongoing** ("use the visual schedule daily"). Section 7 resolves the boundary.

---

## 4. The fan-out model — one finding, many sub-targets

A clinician sentence can be evidence for more than one sub-target, and **assessed differently on each**. The funnel has one rule applied uniformly — there is no privileged "primary":

1. A finding is evaluated against the set of sub-targets it plausibly relates to → that set **is** *Sub-targets Touched* (Section 10).
2. For **each** sub-target in that set, the same materiality test is applied independently: *does the finding directly, materially speak to THIS sub-target?* Each that passes → its own observation record. Those that do not → remain only "touched."

**The hat — one record.** "Tom put his hat on with positioning help" is *directly about* Self-Care / Dressing (benchmark covers other garments, not hats → **Gap**). It does not directly speak to any benchmarked Gross-Motor sub-target, so it produces no Gross-Motor record — at most "touched" there. One record.

**The ramp — two records.** "Tom climbed the ramp alongside a peer, accepting side-by-side climbing" is *directly about* Play Skills / Parallel play AND Gross Motor / Climbing — both benchmarked, both materially addressed. Two observation records, each authored from its own sub-target's perspective, each standalone-readable. A single multi-linked row could not hold two sub-target tags and two assessments — hence two records.

### 4.1 The rule is per-sub-target materiality

There is no first/second; there is a set, and a test asked once per member:

> A finding lands on **every** sub-target it directly and materially speaks to. For each, record an observation. An **adjacent** (un-benchmarked) record is created **only when the finding's direct subject is that adjacent area itself** — never as a second copy of a finding that already has a benchmarked home. If the finding merely *brushes* a sub-target (it is about something else), that sub-target is **touched** (Section 10), not recorded.

There is no label to flip, because the test — *is the finding about this sub-target?* — is identical for every candidate. The hat is direct-subject to Dressing only → one record. The ramp is direct-subject to two benchmarked targets → two records. A finding direct-subject to Gross Motor that only faintly evokes a Play theme → one Gross-Motor record; the Play brush is caught by Sub-targets Touched.

**Capture broadly, fan reluctantly.** Recording a finding on a sub-target it is genuinely about is cheap and default (Section 6.1). What is *expensive* is a **benchmark change** (Section 6.2, candidate-gated). Fan-out itself is not suppressed — it is disciplined by materiality: a finding produces as many records as it has direct subjects, no more. The explosion vector (one chatty paragraph → speculative records across five lightly-brushed areas) is killed by the direct-subject test. Recurrence + Sub-targets Touched catch anything genuinely important that did not clear the bar this time (Section 6.4).

### 4.2 The shared fact is held constant

Rewriting per sub-target risks the two records **drifting in fact**, not just framing — "positioning help" on one becoming "minimal support" on the other. That would produce two timestamped records disagreeing about the same moment, both citable in a brief. **Rule:** framing and emphasis may differ per sub-target; the observed fact is anchored to the same verbatim `Source Fragment` from the Findings parent. Target-specific interpretation layers *around* a constant fact.

### 4.3 Sibling-aware self-review

Fan-out needs a sibling check beyond per-note review, and it now runs in **two parts** at two stages, because assessment is deferred (Section 6):

- **At extraction — split coherence.** Do these N observations make sense as a *split* of one finding? (A finding fanned to two sub-targets that obviously don't both belong is a mis-split, catchable on the text alone, before any grade exists.)
- **At Pass 1 (confirmation) — assessment coherence.** Now that grades exist: are the siblings' assessments mutually coherent? *Above* on sub-target A + *Regression* on sub-target B from the same sentence usually means a mis-split.

> These N observations share a Finding — is the split sound (extraction), and once graded, are the assessments mutually coherent (Pass 1)?

Disagreement like Above/Gap is expected and fine. Contradiction like Above/Regression is a mis-split signal. Both checks key off the shared Finding ID, and the assessment-coherence check spans both running logs.

---

## 5. The finding taxonomy

A session might produce: an **observation** (something seen), a **strategy mention** (a tactic proposed, continued, changed, or discontinued), and **actions** (single events that enable a tactic). The encounter fans into more than observations — the finding taxonomy is the routing model.

| Finding type | Routes to | Notes |
|---|---|---|
| **Observation** | Observation record → sub-target, assessed | The default; capture-broadly applies |
| **Strategy mention** | Pass 2 set-diff against the sub-target's strategy inventory (Section 7.2) | New / continued / adjusted / discontinued component |
| **Action** | Health Actions, optionally `Strategy` relation | Single event; may enable a component |

| | Strategy component | Action |
|---|---|---|
| Lifespan | Ongoing / long-running | Single event |
| Example | "Daily visual schedule for transitions" | "Buy a visual schedule board"; "Email school about using it" |
| Tracked | Active → Inactive (didn't-work / superseded) / Achieved | Open → Done |
| Lives on | Strategy inventory, sub-target tagged | Health Actions, optionally tagged to a component |

---

## 6. The assessment engine — two passes, both behind the confirmation gate

This is the part that does **not** live in the extraction call. **Extraction produces *unassessed* records; assessment happens after draft confirmation** (Decision, 27/06/2026). This is the load-bearing entry-flow decision: it keeps the edit-map clean by construction (Section 6.1.1) and unifies first-assessment with the cascade's recompute.

### 6.0 Entry flow — what extraction writes vs what the gate releases

The Sonnet extraction call does **fan-out + attribution only**. It creates:

- **Findings** (the discrete clinician statements, with the constant `source_fragment`)
- **Observation *shells*** — each anchored to a sub-target, with its fact/note/source/date and `Sub-targets Touched`, but **no `assessment` value** (the grade column is null at creation)
- **Strategy observation shells**, actions, and the appointment record (`status='draft'`)
- the `self_review` block → `flags`

Nothing derived exists yet. The draft sits for review; the user edits facts, fixes attribution, retracts junk. **On confirmation**, two things fire in order: **Pass 1 assessment** (grade the now-trusted shells), then **Pass 2 reconciliation** (aggregate). Both are gate-tight by construction — they only ever run on confirmed records.

This is why a draft fact is *freely editable* with no cascade: at draft there is genuinely nothing downstream of it. The edit-map's "does anything derive from it?" test returns *no* for a draft observation's fact, so free-edit is correct and safe (Section 6.1.1).

### 6.1 Capture broadly, assess tightly

Capture and assessment are different operations, gated differently.

- **Capture** — does this finding get a structured, sub-target-anchored, verbatim-anchored observation record? → **Yes, by default**, for anything mapping to a sub-target or to an Adjacent-watch / Other slot. The sub-target is the **home of record**; the encounter summary is **not** a retrieval fallback. Not recording an at-benchmark observation is not avoiding duplication — it is *losing the data*. Capture happens at extraction (as shells).
- **Assess** — does this observation sit Lower/At/Above its benchmark, and does the run change a benchmark? → **Behind the gate**: Pass 1 grades at confirmation; Pass 2 aggregates; benchmark *changes* are candidate-queued, human-approved.

At-benchmark observations are the *denominator*: a plateau, a slow drift, a run of "At" that suddenly breaks are only visible if the "At"s were recorded. Stability itself is data. The `Assessment` field makes `At` a first-class value, not an absence. The thing to avoid (the model trying to make every line a needle-mover) is gated on **assessment**, not on **capture**.

### 6.1.1 Why assessment-behind-the-gate keeps the edit-map clean

The three-tier edit map (`decision-I-sqlite-schema.md`) classifies the observation *fact* as freely editable and the *assessment* as derived/gated. The fact, though, is what the assessment derives from — and because `source_fragment` is held **constant across all fan-out siblings** (Section 4.2), a free edit to a shared fact would otherwise silently invalidate N sibling assessments across N sub-targets with no trigger. Deferring assessment removes the hazard at entry: while a record is in draft, no assessment exists to invalidate, so the fact is genuinely free.

**Post-confirmation fact correction is Finding-grain.** Once confirmed (and assessed), a wrong shared fact is the §5 **wrong-fact** correction (invalidate + replace, same Finding) — but applied at **Finding grain, not single-observation grain**: because the fact is shared, the correction fans across **every sibling observation built on that Finding**, then cascades each affected sub-target. The mechanism is the existing one; it must be written to fan over siblings, not treat one observation in isolation.

### 6.2 Pass 1 — per-record assessment (at confirmation, not extraction)

On confirmation, each observation shell against an **Active** sub-target (one with a benchmark) is graded against the **benchmark as-of the observation's date**. This is the **same `assess(fact, benchmark_as_of)` function the cascade calls on recompute** — first-assessment and re-assessment are one code path:

- **Lower** — below the benchmark level
- **At** — confirms the benchmark → recorded, no benchmark change (inert, but kept as data)
- **Above** — exceeds the benchmark
- **Gap** — falls clearly inside *this named sub-target* but the benchmark is silent on this case → feeds the **benchmark-extension** review
- **Adjacent** — within a goal's scope (or in Other) but maps to *no* benchmarked sub-target → assessment N/A → feeds the **new-sub-target** review

`Gap` and `Adjacent` are deliberately distinct: one says "extend an existing benchmark," the other says "there is no sub-target here yet."

**Model assignment.** Pass 1 is a **bounded benchmark-comparison**, not full extraction — a separate **Haiku** call per confirmed report, scoped to that report's touched sub-targets, injecting only those sub-targets' benchmarks (not all 36 — Section 9). The expensive Sonnet call stays at one-per-report for *extraction*; assessment rides a cheaper, narrower call. (This is the deliberate cost trade for deferring assessment: assessment no longer free-rides the extraction call.) **Haiku is the planned default; validate at the 1d data load** — because a misgrade fabricates progressions, if Haiku misgrades on real reports, bump Pass 1 to Sonnet. The grade carries a confidence value, so a run of low-confidence Haiku grades is itself the signal to escalate.

**Nothing auto-edits a benchmark.** A benchmark edit changes the threshold every future observation is judged against; advance it on a fluke and the next genuine "At" reads as "Lower" → a fabricated regression. All benchmark changes write to a candidate/holding state. The actual edit is a Haiku-suggested, Matt-approved promotion. Fan-out *floods* this queue (one chatty paragraph → three candidates), which is exactly why the holding state is load-bearing: over-fan produces visible candidates, not silent edits.

**The safety-critical alert does not depend on assessment.** Deferring grading must not mute the immediate alert. The alert keys off the **capture-time severity screen** on Medical sub-targets — a language-based screen the extractor runs at capture ("screened, not silent," Section 11), independent of any benchmark grade — so it fires at processing time even though assessment is deferred to confirmation.

### 6.3 Pass 2 — reconciliation / aggregation (separate pass over the log)

The extractor sees one report and cannot see the run. These decisions require history:

- **Regression** — multiple "Lower" in a row, or repeated ≥3 months apart on the same sub-target
- **Progression** — confirmed "Above" (not a fluke single reading)
- **Addition** — repeated "Gap" on the same un-benchmarked case

So regression / progression / addition are a **reconciliation pass** over the observation history per sub-target — run after Pass 1, not inside extraction. This pass is **pure logic, not an LLM call**: Pass 1 already did the per-record reasoning (at confirmation); aggregating dated assessments into a change is arithmetic — deterministic, auditable, and cheap to run repeatedly over a backfilled year.

**Milestone** survives as a marker on an observation (the `Milestone` checkbox), co-existing with the Assessment tag — not a separate assessment value. It remains the vehicle for historical first-time wins.

**Assessment timing and late-arriving reports.** Observations are graded Lower/At/Above against the benchmark **as-of the report's date** — this is Pass 1, run at confirmation. It does not replay *on new-data arrival*: a later report never re-grades earlier observations. (The *only* re-grade path is the cascade, fired by a correction or a sequential benchmark advance — never by the mere arrival of more data; `decision-I-sqlite-schema.md`.) The recency handling lives entirely in Pass 2, which operates over history:

- A **recent** late-arriving report can legitimately tip the picture — e.g. turning a prior one-off "Above" into a change-triggering run — because Pass 2 looks at the *current* aggregate for that sub-target, and the recent report is part of it.
- An **old** late-arriving report updates *history* (its observation exists, assessed as-of its own date) but does **not** retroactively rewrite the benchmark trajectory — Pass 2 simply does not re-derive a months-old change from a report that arrived late.

There is no replay on new-data arrival. Observations are assessed as-of their date at confirmation; benchmark changes are only ever proposed by Pass 2's current-picture view, and grades only ever recomputed by the cascade.

### 6.4 The promotion engine — one recursive process, three grains

`Gap` and `Adjacent` are not two unrelated mechanisms — they are the **same verb** (*accumulate, review, promote*) operating at different grains. So is spinning a sub-target out of Other into its own goal page.

| Grain | Trigger | Accumulates as | Promotes to | Artifact produced |
|---|---|---|---|---|
| **Benchmark line** | Repeated/significant `Gap` on a named sub-target | Gap observations on that sub-target | A new line in that sub-target's benchmark | Benchmark `Addition` (change-log entry) |
| **Sub-target** | Cluster of `Adjacent` on a theme | Adjacent observations (in a goal or in Other) | A new Active sub-target (Adjacent-watch → Active, first benchmark written) | New Sub-target row + Baseline change-log entry |
| **Goal page** | A sub-target inside Other matures / becomes clearly standalone | A populated Other sub-target | Its own Goal Page (re-point the sub-target's Goal relation) | New Goal Page; one-field re-point carries history |

The shape is identical at every level: log freely → a periodic review looks for clusters or significant singletons → on approval, promote and let the existing structure absorb it.

**Two safeguards carry up the whole engine:**

- Promotion is always **candidate → human-approved**, never automatic (the same pattern as benchmark changes).
- Promotion **never re-tags history** — because observations anchor to the sub-target, and the sub-target is what moves. Re-pointing one relation carries every linked observation with it.

**Three review streams, one surface.** The engine produces three distinct review streams — benchmark-extension (Gap-driven), new-sub-target (Adjacent-cluster), and spin-out (sub-target maturity). They share one periodic review surface (Notion candidate views during the data load; the dashboard review page for the ongoing loop in Phase 5), but they produce three different artifacts and are presented as three sections, not merged into one list. The `Other / Unclassified` emptying review (Section 2.2) is a fourth, lower-stakes stream on the same surface.

### 6.5 Operations — model/logic assignment and cadence

The machinery maps to models on the principle: **pure logic where the decision is deterministic, Haiku for bounded classification/clustering, Sonnet only where reasoning across content is required.**

| Operation | Model / logic | Cadence |
|---|---|---|
| Extraction + fan-out + attribution + strategy-vs-noise + self-review (creates unassessed shells) | **Sonnet** (the one extraction call) | Per report (at ingestion) |
| Pass 1 per-record assessment (grade shells vs benchmark as-of date) | **Haiku** (bounded benchmark-comparison; same `assess()` the cascade uses) | **At confirmation**, scoped to that report's touched sub-targets |
| Regression / progression / addition detection (Pass 2) | **Pure logic** (counts over dated assessment rows) | At confirmation (touched sub-targets) + per-cascade + full sweep at data-load end |
| Strategy set-diff — match mention → existing component (Pass 2) | **Haiku** (bounded resolution in a tiny per-sub-target pool) | At confirmation (when strategy content present) |
| Candidate generation (assemble proposed change) | **Logic** + **Haiku** for the human-readable reason summary | With Pass 2 |
| Staleness detection (cold components, flat sub-targets) | **Pure logic** (date math) | Weekly |
| Promotion clustering (Gap/Adjacent → suggest extension / new sub-target) | **Haiku** (batched theme judgement) | Weekly |
| Benchmark / strategy update on approval | **Haiku** (structure-preserving) | On approval |

Two consequences for planning: the regression/progression/addition engine is **pure logic, not an LLM call**; and the per-report cost is now **one Sonnet extraction (at ingestion) + one Haiku assessment (at confirmation)**, plus logic and occasional Haiku for set-diff/clustering. The Sonnet call stays at one-per-report; assessment moved off it onto a cheaper scoped Haiku call (the deliberate trade for assessment-behind-the-gate). Per-report reconciliation is narrow (only the sub-targets that report touched); the time-based reviews (staleness, promotion clustering) run weekly. Steady-state token cost stays close to the front-half-only model, with a one-off bump during the data-load backfill — recompute the per-report profile at Phase 1d once it is real.

---

## 7. Strategy capture

### 7.1 Speculative language is strategy language

Self-review's speculative-language rule still strips genuinely speculative *one-off action* noise from the actions list. But providers phrase **strategies** in that same speculative form — "you could try a visual schedule" **is the strategy**, not noise to discard. So strategy capture takes priority over the delete rule: speculative language proposing an ongoing approach to a goal is recognised and captured as a Strategy (tagged to its sub-target), never folded into the appointment Summary. The Summary catches only vague hedging with no actionable content.

> Speculative language proposing an *ongoing approach to a goal* → candidate **Strategy** (tagged to sub-target).
> Speculative language proposing a *one-off task* → still scrutinised; only an action if concrete and owned.
> Vague hedging with no actionable content → still summary only.

### 7.2 The set-diff — maintaining the inventory across encounters

There is no strategy "assessment against a target." The operation is a **set-diff**: compare what the encounter says about tactics against the sub-target's current inventory. **Every mention writes a Strategy Observation row** (the running log, Section 3.8) — including unchanged ones; *and* mentions that constitute a change additionally produce a candidate that, on approval, mutates the component and writes a Strategy Change Log entry. Two logs, exactly like the benchmark lane:

| Encounter says | Inventory state | Strategy Observation (always) | Change candidate (only if change) |
|---|---|---|---|
| Mentions a tactic, **new** | not present | row, `New-proposed` | **Add** component (Active) |
| Mentions a tactic, **unchanged** | present, Active | row, `Still-active` (+ "working/not-working" if stated) | none — bump `Last Referenced` only |
| Mentions a tactic, **changed** | present | row, noting the change | **Adjust** — edit Definition (or retire-and-link C→C′) |
| **Explicitly** discontinues | present, Active | row, `Discontinued-stated` | **Discontinue** → Inactive (+ stated reason) |
| Silent on a present tactic | present, Active | *no row* | **No change** — silence = keep; `Last Referenced` not bumped |

So "still trying B, no change" is a first-class Strategy Observation row, not just a date bump — preserving the denominator the way at-benchmark observations do on the other lane. Only a *changed* mention also touches the change log.

**Worked example** — "we tried A, B, C; A wasn't a good fit, continuing B and C, no progress yet, let's try D and adjust C to C′": **five Strategy Observation rows** (A discontinued-stated, B still-active with "no progress" as stated context, C changed, D new-proposed); then the **change candidates** A → Inactive-didn't-work ("poor fit"), C → C′ (adjust), D → add; B is keep-only (row written, no change-log entry). On approval each change appends a Strategy Change Log entry.

### 7.3 Two-pass strategy extraction

**Pass 1 (extraction) — recognise and tag, do not match.** The extractor flags strategy-related content and tags it to a **sub-target** (the same safe classification it already does for observations). It must **not** try to resolve a mention to a *specific existing component* — it cannot see the inventory reliably and would mint duplicates. Two things stay in Pass 1 regardless:

- **Strategy-vs-noise classification** (Section 7.1) — "you could try X" as proposed-tactic vs speculative noise vs one-off action. This is about the linguistic form of the finding and cannot move to Pass 2.
- **Wide-net recognition of status language** — "the schedule's going well" must be flagged as strategy-status content even though Pass 1 will not resolve *which* schedule. Over-tag in Pass 1; Pass 2 discards mentions that match nothing. This is the safe error direction.

**Pass 2 (reconciliation) — match and diff.** Loads only the strategy inventory for *that sub-target* (a handful of components, not the whole set), resolves each Pass-1 mention within that small pool, and runs the set-diff above. The sub-target tag is the index that scopes matching down to reliable entity resolution — against 3 candidates, not 40.

**Standing-context injection — thin titles, not the full set.** To avoid Pass 1 under-recognising status language, inject a thin list — active component **titles + their sub-targets** ("Visual schedule → SE/transitions; Chewy tool → MED/dysphagia"), not full definitions. Titles to *recognise*; definitions stay in Pass 2 to *assess*. So the standing extraction context is five inputs, the fifth deliberately lightweight (Section 9).

---

## 8. Benchmarks, strategies, and the data load — two-anchored

Two benchmark anchors are reconciled in one append-only log:

- Seed each sub-target with a **Baseline** entry from the year-ago FSSP (Effective Date ≈ FSSP date).
- Keep the hand-written current benchmark as the **latest confirmed entry** (Effective Date = its authoring date).
- The data load fills the **trajectory between two known endpoints**, each record judged against the benchmark as-of its own date.

The hand-written benchmark is never discarded — it is the top of the log. Anything that does not fit between the two anchors surfaces as a gap candidate, including sub-targets poorly reported in the period, which a parent observation record can fill.

### 8.1 Test and real data load are the same operation

The historical run is a **real backfill** that populates observations *and* the benchmark change log as production data — and the convergence question becomes its own **validation signal**. If seeding the year-ago FSSP baseline and replaying forward trends toward the hand-written current benchmark, that *is* the quality check; the divergences are precisely the gaps worth reviewing. So there is no choice between test and real — it is a real backfill whose convergence on a known endpoint validates the extraction.

- **Value:** high. The query interface, cadence analytics, strategy history, and both the NDIS and DIP reports get a real year of depth from day one.
- **Incremental effort over a throwaway test:** low. The pipeline runs either way; the difference is keeping the outputs as production data and seeding the log properly.
- **Real cost:** review time on the **batched benchmark-change candidates** — the same candidate → approve gate as live operation, run in bulk. Convergence makes most of them cheap to confirm.

### 8.2 Sequential benchmark advancement is a precondition of the data load

The two-anchored model only works if the benchmark **moves through the year as the data load replays**. If the benchmark stays pinned at the year-ago Baseline while a year of reports is processed, every later observation is judged against a stale-low benchmark and reads as `Above` → the load fabricates a wall of false progressions. So the **Pass 2 reconciliation engine must exist and run during the data load**, processing reports oldest-first and advancing the benchmark via approved candidates as it goes, so each observation is judged against the benchmark *as it stood at that observation's date*.

This makes the data load and Pass 2 **co-validating**: the load is the first real test of the reconciliation engine, and the engine's correctness is what makes the load's convergence on the hand-written benchmark meaningful. Convergence ⇒ sequential advancement works; large divergence ⇒ the engine or the extraction needs tuning, *and the divergences are themselves the gap candidates worth reviewing*. Consequently the data load is **Phase 1d**, after the engine is built — never before.

### 8.2.1 The strategy lane is two-anchored too

The strategy inventory needs the same two-anchor treatment as benchmarks, or the set-diff replaying from an empty set mislabels pre-window strategies. A strategy that was already running *before* the replay window first appears mid-replay as an unchanged "still using X" mention; against an empty inventory the set-diff reads *not-present* → `New-proposed` → it is added late and falsely flagged as new (Decision, 27/06/2026).

The fix mirrors the benchmark anchors:

- **End-anchor (the important one):** Matt drafts the **current active strategy inventory** — the parallel to the hand-written current benchmark — as the convergence target. This is a sit-down drafting task, like the benchmarks.
- **Start-anchor:** seed year-ago FSSP strategies as the inventory's starting state where the FSSP records them. Gaps are tolerable — a strategy absent from the FSSP simply gets added when first mentioned in the replay, which is correct.
- With the start-anchor seeded, a pre-window strategy seen mid-replay as "still using X" **matches** the seeded inventory → `Still-active`, not a false `New-proposed`.

So the strategy lane converges on Matt's drafted current inventory exactly as the benchmark lane converges on the hand-written benchmark; the end-anchor is what matters, the start-anchor's gaps are safe.

### 8.3 Two backfills, not one

"Backfill" covers two independent operations with different feedback loops:

1. **Historical data load** — run a year of *already-in-hand* reports (the 15–20 historical set) through extraction → observations + benchmark change log + strategy inventory. Fed **directly** (file drops), so it needs **none** of the email-identification pipeline. Exercises the **outcome layer** (fan-out, assessment, reconciliation, candidate approval, two-anchored convergence). Refinement loop: **extraction/assessment-prompt tuning**, driven by the batched candidate queue and the `Flags` self-review data.
2. **Ingestion backfill** — run sender detection / Stage 2 / subject-patterns / dedup over a year of *inbox* history. Tests the **front-half pipeline**. Refinement loop: the **performance-review loop** (known-sender/keyword tuning, settings.yaml write-back).

The **data load comes first** (Phase 1d), against the validated extraction, because it carries the structural risk (it bakes the benchmark log) and needs no email plumbing. The **ingestion backfill comes later** (Phase 2 proper), once sender detection exists. The high-value structural validation is not gated behind building the email pipeline.

### 8.4 Review surface — the Flask Candidates page, day one

The data load produces bulk `flags` data and a bulk **candidate queue** (benchmark changes, gap/adjacent promotions, strategy-inventory diffs). The review surface it needs is batch, one-off, and grouped — and with SQLite as the system of record (Section 3.0), that surface is the **Flask dashboard Candidates page, built day one** (Decision I, 27/06/2026). It is **not** a Phase 5 nicety and **not** a set of Notion views — it is the primary interface for the Phase 1d data load.

- **Data-load review = the Candidates page.** Candidates are structured SQLite rows; the page filters to pending candidates, **grouped by sub-target**, with inline approve/reject — you see the whole sub-target's run at once and bulk-confirm convergence. The earlier "Notion views first" plan is superseded: the engine data lives in SQLite, so the review surface is the dashboard over that store from the outset.
- **Dashboard performance-review page = the recurring loop.** The sender-detection accept/reject cards and `settings.yaml` write-back (Section 13) are a *separate* dashboard surface for the *ongoing* ingestion loop, built in Phase 2/5 where the recurring stream it reviews actually exists. The Candidates page (engine changes) and the performance-review page (sender detection) are distinct surfaces with distinct lifecycles.

**Data-model constraint:** candidate records are **structured rows** — a `status` (pending/approved/rejected/withdrawn), a typed `change_class`, a `reason`, the source-finding/observation links, the target sub-target/component — *never* a serialised JSON blob, and distinct from the appointments-scoped `flags` field. Full schema and the typed change vocabulary: Decision I, Section 17 and `decision-I-sqlite-schema.md`.

---

## 9. Standing context — extraction injection vs assessment injection

Because assessment is deferred to confirmation (Section 6), the **benchmarks are no longer injected at extraction**. Extraction needs only enough to *route* a fact to the right sub-target(s); the benchmarks inject later, at the Pass 1 assessment step, scoped to the touched sub-targets.

### 9.1 Extraction injection (Sonnet, at ingestion)

Five inputs are injected before each extraction call, using **`###PLACEHOLDER###` substitution, not `.format()`/f-strings** (the prompt body contains JSON braces that `.format()` would break):

**1. `###EXTRACTION_CONTEXT###`** (static, from settings.yaml) — Tom-specific clinical baseline. Tom is 7 (born Dec 2018): Chromosome 18p deletion, mosaic Trisomy 13, **ASD Level 2 – Requiring Substantial Support (diagnosed May 2026)**, hypotonia, **dysphagia with choking risk and modified diet**, low processing speed (borderline), borderline visual-spatial skills, strong visual working memory. **Grade 1** at South Geelong Primary with Education Support. The context explicitly lists his ASD-profile behaviours (routine reliance, transition distress, scripted/repetitive language, sensory sensitivities, atypical interoception, distress presentations) as **established baseline**, so a report mentioning them is not mis-read as a new finding or regression. Adult prompting/support is baseline; meaningful progress = assisted→independent, generalisation across settings, or sustained unprompted demonstration. Full verbatim text lives in settings.yaml.

**2. `###SUBTARGET_ROUTING_LIST###`** (per sub-target, from the Sub-targets table) — each sub-target's **title + scope line** (and goal), rich enough to route a fact to one or more sub-targets, **without** the benchmark. This replaces the former benchmark injection at extraction. The scope must be discriminating enough to separate near-neighbours (e.g. the three Safety sub-targets split on setting) — so the routing signal lives in the title + a short scope line, not goal-level scope alone, which is too coarse. Goal scope still bounds Tier-2 adjacency.

**3. `###PROVIDER_LIST###`** (from the Providers table) — canonical Title + Aliases + Type per provider, so the model resolves names/nicknames to canonical providers at extraction time. The primary defence for provider matching (Section 12).

**4. `###ACTIVE_STRATEGY_TITLES###`** (thin list, from the Strategies table) — active component titles + their sub-targets, so extraction recognises strategy-status language without trying to resolve to a specific component (Section 7.3).

**5. `###REPORT_TEXT###`** — clean labelled output of `prepare_content()` (Section 18).

`###APPOINTMENT_DATE###` is also injected (recorded on every shell; the date Pass 1 will later judge against).

### 9.2 Assessment injection (Haiku, at confirmation)

At confirmation, the Pass 1 assessment call injects, **scoped to the touched sub-targets only**: each touched Active sub-target's **current benchmark + as-of date + goal scope**, plus the appointment date. This is where `###GOALS_WITH_BENCHMARKS###` now lives. Scoping to touched sub-targets (a handful, not all 36) keeps the call small and is the natural answer to benchmark-injection scaling as the spine grows.

---

## 10. Sub-targets Touched

A by-product of the fan-out funnel rather than a separate tagging step. The funnel (Section 4) already evaluates a finding against a set of plausible sub-targets, then filters by the materiality test. **That input set is "Sub-targets Touched."** The model lists what it considered; the ones that clear materiality become observation records; the whole considered set is persisted as touched (a multi-select on the encounter).

- **Touched is the superset, not the leftover.** It includes the sub-targets that *became* observations, not just the brushed-but-unrecorded ones. Recorded ⊆ Touched.
- This makes **"touched repeatedly but never recorded over a year"** a clean derivable signal — either a missed pattern or a genuine adjacency worth promoting (Section 6.4). That is its real value, beyond the quick filter.
- A goal-level "Goal Areas Touched" view is available if wanted — it is the denormalised roll-up of Sub-targets Touched (goal from each touched sub-target).

Three distinct mechanisms — do not conflate them:

| Mechanism | Grain | Cost | Purpose |
|---|---|---|---|
| **Sub-targets Touched** (multi-select on encounter, from the funnel's considered set) | sub-target-level, flat | ~free (by-product of fan-out) | "which sessions considered sub-target X"; under-recording signal |
| **Observation record** (recorded when materiality passes) | sub-target-level, assessed | cheap to record, gated only on benchmark change | the actual tracked signal and denominator |
| **Finding ID** | binds siblings (incl. strategy-observations) | structural | provenance + dedup + reconciliation |

Under capture-broadly, Touched is an **index + an under-recording detector**, not a data-loss backstop (recorded observations are not suppressed).

---

## 11. Medical as a goal — same machinery, different axis

Goal: "Tom remains generally healthy within known diagnostic limits." Sub-targets = watch/focus domains aligned to his specialists (gastro, dental, growth, dysphagia/airway, continence).

What changes under the same engine:

- **Axis** — capability (below/at/above independence) is read as **status** (worsening / stable / improving). This is the **same `Observations.Assessment` field**, not a parallel one: medical sub-targets read its values as a status axis (Lower≈worsening, At≈stable, Above≈improving), with `Gap` / `Adjacent` unchanged in meaning. The medical extraction prompt relabels the vocabulary for the model; the stored field and its options are identical, so one Observations schema serves both and cross-domain queries stay uniform.
- **Milestone** barely applies — formal results still mark, but "first independent X" does not.
- **Severity flag** — dysphagia/airway is a *safety* watch. A "worsening" there must escalate harder than a gross-motor regression. Medical sub-targets carry a `Severity` field (None / Watch / Safety-critical) that goal sub-targets do not need.
- **Safety-critical alert.** When extraction produces a worsening (or any flagged concern) on a `Safety-critical` medical sub-target, the agent sends an **immediate email alert at processing time** — not the weekly digest, not waiting for draft confirmation. This is the one path that bypasses the normal review cadence, because a choking-risk escalation cannot sit in a draft queue until Saturday. The alert names the finding and links the source encounter; it does not auto-confirm any record.

**The `Other medical / watch` holding pen** (Decision A, 25/06/2026). Medical gets its own holding pen, mirroring `Other / Unclassified`, for infrequent or one-off medical appointments that don't map to a seeded watch domain (ENT, orthopaedics, one-offs). It differs from the Other/Unclassified pen in one critical way: **pen findings run a severity screen at capture** — `None / Watch / Safety` — even when the sub-target is un-benchmarked. So a safety signal arriving against an un-seeded medical area still reaches the immediate-alert path; it is **"screened, not silent."** The screen value persists on the observation shell (`observations.severity_screen`, set at extraction, independent of assessment) so it drives the alert *and* is later queryable ("which findings tripped the screen, when"). Like the Unclassified pen it is reviewed to be emptied, but on a medical cadence — it **drains at the paediatrician 6-monthly**, where one-off findings are either promoted to a real watch domain or confirmed incidental and left to rest.

---

## 12. Provider matching

The canonical provider list is injected into the extraction call (`###PROVIDER_LIST###`) as the **primary defence**: the model maps "Maddy" → "Madelaine Tomlin" before `notion_writer` runs. The fuzzy + alias match in `notion_writer` is the backstop. Rules (in `notion_writer.py`):

1. **Split combined-name strings** on commas and "and"/"&" into individual names **before** any matching. Never create a provider record from a combined string. (This fixes the failure mode where a single combined string such as `"Kerry Britt, Madelaine Tomlin, Sally Barnard"` would otherwise create one junk provider record instead of three links.)
2. **Normalise then fuzzy match** against existing records: case-insensitive, strip titles (Dr/Mr/Ms), trim whitespace. Partial substring match handles "Madelaine Tomlin" vs "Madelaine Tomlin (Maddy)".
3. **Check the Aliases field**, not just Title. Substring match alone fails on nicknames ("Maddy" is not a substring of "Madelaine") — the Aliases field carries known nicknames and initial forms. The matcher checks Title + Aliases.
4. If no match and auto-create is enabled: create a record with available fields and a `flags_for_review` entry for manual Type / NDIS Funded / Aliases completion. Never auto-create a combined-name record.

Provider attribution in a multi-provider meeting: each extracted action is assigned to its specific provider in `Health Actions.Provider`; where attribution is unclear, the extractor flags it for the user. There is no Lead Provider field (Section 16, Database 1).

---

## 13. Email ingestion & sender detection

### Dual inbox monitoring

- **Primary Gmail** — health provider senders, appointment confirmations, the secondary user's emailed notes, self-submitted scans, force-trigger subjects
- **Secondary (Louise's) Gmail** — same detection logic; catches reports that only went to her address
- **Deduplication** — same document arriving in both inboxes creates one Appointment record, not two

### Email subject pattern detection (checked before sender detection)

Specific subject patterns trigger agent actions directly, bypassing sender detection. They work from either monitored inbox.

| Subject pattern | Action |
|---|---|
| `FORCE INGEST` + attachment | Force ingest the attached file as a new report |
| `FORCE BRIEF – [Provider] – [Date]` | Generate pre-appointment brief immediately |
| `NDIS REPORT YYYY-MM-DD YYYY-MM-DD` | Generate NDIS report for the date range |

### Two-stage sender detection

**Stage 1 — rule engine (free, every email):**

1. Subject matches a force-trigger pattern → handle separately
2. Sender in `known_sender_emails` → auto-process
3. Sender domain in `known_sender_domains` → auto-process
4. Subject matches `keyword_phrases` → Stage 2
5. No match → skip, log

**Stage 2 — Claude Haiku (ambiguous only, when `features.stage_2_detection` enabled):**

- Input: sender name, subject, first ~200 words, `stage_2_prompt` from settings.yaml
- Output: `{ relevant: bool, confidence: high/medium/low, reason: str }`
- High → process; Medium → flag for review; Low → skip
- All Stage 2 events logged to the Performance Log regardless of outcome

**Keyword approach.** Use phrases, not single words, to minimise false positives ("appointment summary", "session notes", "clinical report", "discharge summary", "referral letter", "progress notes", "NDIS" anywhere in subject). Single words like "report" or "plan" trigger Stage 2 review only, never auto-process. Build the keyword list empirically: start with known senders, observe what gets missed, derive keywords from actual missed subjects, refine via the dashboard performance review.

### Email thread handling

The full thread is fetched, not just the triggering message. Each message is labelled by sender and date. User responses are captured — if a response confirms completing an action, it is logged as a closed Health Action with the date of the response.

### 13.1 Multi-source encounter reconciliation (before draft exit)

One encounter can be described by **two sources**: a family/brief-captured note (the live-capture or returned-brief surface, Sections 14.1 and 15.2; `Author: Matt/Louise`) and the provider's later written report (`Author: Provider`). These are not document-duplicates — they are different authors describing the same moment — so document dedup (above) will not merge them, and if both became separate confirmed observations on the same sub-target around the same date, **Pass 2 would count both and one real event could fabricate a progression**.

**Rule (Decision, 27/06/2026): two sources of one encounter are attributed to the same encounter and reconciled *before either passes beyond draft*.** By confirmation they are either **bound to one Finding** (so Pass 2 sees one datapoint, with the richer/corroborated framing) or the second is marked **corroboration-not-counted** (kept, linked, visible, but excluded from the Pass 2 count). Divergence between the two is **flagged for adjudication, never silently merged** — the difference is often signal (setting variance: home vs clinic), not noise.

**The matching mechanism — second arrival joins the existing draft, does not mint a new encounter.** Because the two sources usually arrive days apart, the later arrival must **match to the existing draft encounter** on date + provider + subject, and attach to it, rather than create a second Appointment. This is a small extension of the dedup matcher (it already matches documents; here it matches *encounters* across sources).

**Residual (open question, Section 25):** the case where the first source was **already confirmed** before the second arrives. Then the second is not a draft-time reconciliation but *new evidence on a confirmed encounter* — it attaches to the confirmed encounter and routes any change through the candidate gate, rather than being reconciled pre-draft. The timing rule for this needs settling so "reconcile before draft exit" is always achievable.

---

## 14. Brief generation — goal-structured

Because every observation/strategy/action carries its source encounter, and the encounter page references the records it produced, the brief is goal-centric *within* a provider's scope.

**Single-provider brief (e.g. OT) — derived sub-target scope.** The brief covers the provider's *working set*, derived (not stored) at **sub-target grain**, then rolled up under parent goals for display. Two distinct queries:

- **Scope (what to include)** — the distinct sub-targets where this provider has an **Observation or Strategy Observation within a window** (default ~6 months; a `settings.yaml` knob), **unioned with their most-recent-appointment sub-targets** as a floor (so an infrequent provider is never blank), **minus any Achieved/Dormant**. Capture-broadly makes this reliable: a quiet check-in still writes an *At* observation, so a maintained sub-target stays in scope; strategy-only touches are caught via the Strategy Observations union. *Scope is not "last appointment"* — one session is usually a slice of the rotation.
- **Delta (what to show per sub-target)** — for each in-scope sub-target: current benchmark, **what moved since this provider's last session on it** (with assessment), **active strategy components surfaced as the thing to check in on** ("how's the visual schedule going?"), any **cold components flagged for retirement** (staleness, Section 3.7), open actions, and a high-level "focus this session" line.

The window value is settled empirically at the Phase 1d manual brief mock-up (the data load gives a real year to test that ~6 months captures each provider's working set without dragging in stale areas). A brand-new provider with no history yields a minimal brief — handled by the new-provider brief below.

**Paediatrician 6-monthly:** pulls *across all goal pages* — the goal-page structure is already the report structure.

**NDIS annual report:** a **read, not a reconstruction** — per-goal narrative is literally what the report is.

**DIP (school) review:** the same data re-projected by DIP domain (Section 2.3) rather than plan goal — a saved view, not a separate build.

**New-provider brief:** Health Summary (who Tom is) + current-state on a manually selected set of sub-targets — the onboarding/curation path, defined in Section 19. Distinct from the derived-scope single-provider brief above.

### 14.1 The brief as a consistency forcing-function

The brief is more than an output — it is a lever on *input quality*, the system's biggest uncontrolled variable. Provider note-taking varies; the system's evidence is only as good as the worst reporter. But the pre-appointment prep is a moment the user controls.

- **It normalises the input stream.** If the prep consistently asks the same questions (has this benchmark moved? how is each active component going? is this still live?), the *appointment* discusses them and the *encounter note* captures them — consistent questions in, consistent evidence out, regardless of that provider's defaults.
- **It is a behavioural lever.** Actively reviewing and updating the brief before a session makes the session more productive and keeps focus on the areas to progress. This argues for the brief being something the user *interacts with* before the session, not just a generated document.
- **It is a parent-observation entry point.** Prep thinking ("has dressing moved? is the timer still helping?") *is* a set of family-authored observations (`Author: Matt/Louise`, `Source: Family Observation`). The brief lets the user log what prep surfaces — filling exactly the sub-targets providers report poorly — *before* the appointment.

**Brief-live-in-the-meeting (a mode, not a requirement).** The brief open during the appointment is simultaneously the agenda (drives consistent discussion), the reference (everyone informed), and the **capture surface** (decisions/observations logged live, in the system's structured vocabulary, against the right sub-target). That makes the highest-fidelity encounter record the one the user takes, with the provider's later written report as corroboration/dedup. The cost is real — structured note-taking while participating in a child's appointment is cognitive load — so it is a *mode the brief supports*, not a requirement. Some sessions run from it; others, listen and let the report flow in. Both modes work.

---

## 15. Query interface, session write-back, and reporting

### 15.1 Query interface

Natural-language querying of the full health knowledge base, blending record retrieval with Claude's general clinical knowledge. Two-step process:

**Step 1 — retrieval planning (Claude Haiku):** the question plus `query_system_prompt` from settings.yaml → a structured retrieval plan (which databases, what filters). Invisible to the user.

**Step 2 — answer synthesis (Claude Sonnet):** fetched records (from the local store) + original question + conversation history → a conversational answer. Follow-up questions maintain conversation history and can trigger additional fetches via the planning step.

**Source attribution (in the system prompt):** records cited by provider and date; general clinical knowledge flagged explicitly, so the user always knows what came from their records versus Claude's training. The query system prompt's database descriptions are updated to the outcome layer — Sub-targets (benchmark + as-of), Observations (assessed, sub-target-anchored), Strategy Observations, Strategies, Benchmark/Strategy Change Logs, Goal Pages, Appointments, Health Actions, Providers — so retrieval plans target the right structures.

The query interface is also the recovery path for anything deliberately *not* maintained as a standing field — e.g. per-component effectiveness correlation (Section 3.7) is computed on demand here from stored observations + lifecycle dates, never maintained.

### 15.2 Session write-back

Runs at the end of a query session on user request. Claude Haiku reviews the conversation and extracts conservatively:

- **Actions** → Health Actions (Category: Query Session, Status: Open)
- **Talking points** → Health Actions (Category: Meeting Action, linked to provider) — surface in the next brief automatically
- **Observations** → Observations (Source: Query Session Observation, Author: System), sub-target-anchored
- **Strategy observations** → Strategy Observations (Author: System, with the stated `Status read`); a query-session origin is identifiable by an empty `Source Encounter`. Anything constituting a strategy *change* routes through the candidate gate rather than editing a component directly.

The user approves each item individually via a dashboard panel before any Notion write; all fields are editable inline. Where a write-back observation would propose a benchmark or strategy change, it routes through the same candidate gate as any other change (Section 17) — it does not edit a benchmark directly.

### 15.3 NDIS and DIP reporting

On-demand (not scheduled). Triggered via the dashboard (date-range picker) or the `NDIS REPORT YYYY-MM-DD YYYY-MM-DD` email subject.

Both reports are **reads over the same dataset**, differing only in the grouping projection:

- **NDIS annual** — group sub-targets by NDIS goal; filter Observations by plan-period date range and NDIS-reportable significance; Claude Sonnet generates a per-goal progress narrative. Saved as a Notion page under Digests & Briefs / NDIS Reports.
- **DIP (school) review** — the identical observation data re-grouped by **DIP domain** (Section 2.3). A saved view, not a separate build. Because the DIP review accepts existing school-held documentation, the accumulated evidence is directly consumable.

---

## 16. Database schema (logical) — full field reference

These are the **logical** structures and their fields. The **physical** definitions live in `decision-I-sqlite-schema.md` as SQLite DDL (the authoritative build spec — Section 3.0); the field tables here carry the rationale and the front-half detail. "Database / page / row / relation / select" below describe the logical model; physically these are SQLite tables, foreign keys, and `CHECK`-constrained text columns, surfaced through the Flask dashboard (and, optionally, mirrored to Notion). Where a field note references a live Notion property quirk (e.g. a property typo), that is historical front-half provenance — under SQLite the column is named cleanly per the schema doc.

### The logical grouping

This tree is the conceptual grouping of the store (and the layout an optional Notion report-mirror would use). It is **not** a Notion workspace requirement — the engine lives in local SQLite.

```
Health record (SQLite; Flask dashboard UI)
├── 📋 Appointments              (Encounters — evidence layer)
├── 🎯 Goal Pages                (6 NDIS + Medical + Other; roll-up views)
├── 🧭 Sub-targets               (the working pages; benchmark lives here)
├── 🗒️ Observations
├── 🧩 Strategies                (one row per component)
├── 📈 Strategy Observations     (strategy running log)
├── 📜 Benchmark Change Log
├── 📜 Strategy Change Log
├── 🔗 Findings
├── 🗳️ Candidates                (one typed propose → approve queue — Decision I, RESOLVED)
├── ✅ Health Actions
├── 👨‍⚕️ Providers
├── 📊 Agent Performance Log
├── 🗄️ Health Actions Archive
├── 📘 Health Summary            (static document, not a table)
└── 📄 Digests & Briefs          (generated-report collection: Weekly Digests / Pre-Appointment Briefs / NDIS Reports)
```

Outcome-layer schemas are specified in Section 3 (Sub-targets 3.2, Benchmark Change Log 3.3, Strategy Change Log 3.4, Findings 3.5, Observations 3.6, Strategies 3.7, Strategy Observations 3.8) and physically in `decision-I-sqlite-schema.md`. The remaining structures:

### Database 1: Appointments (Encounters)

| Field | Type | Notes |
|---|---|---|
| Title | Title | Auto: "Provider(s) – Date" |
| Providers | Multi-relation → Providers | **Authoritative, load-bearing provider link for ALL retrieval** (briefs, archive, query). Every provider present in a session is linked, including all attendees of a team meeting. |
| Meeting Type | Select | Individual / Multi-Provider Meeting / Review / Planning Meeting / Group Program |
| Appointment Date | Date | (Note: the live Notion property is spelled `Appointement Date` — code matches the typo; low-priority rename.) |
| Report Received Date | Date | When the email arrived |
| Type | Select | Appointment / Report Only / Phone Consult / Hospital / Other Medical / Family Note / Group Program |
| Status | Select | Draft / Confirmed / Not-approved / Archived (+ `not_approved_reason`). Four states — the DDL is authoritative; Not-approved is the retraction/rejection state the gated model needs. |
| Source Email | Select | Primary / Secondary / Both |
| Content Sources | Multi-select | Email Body / PDF Attachment / Docx Attachment / Scanned Image / Self-Submitted / Email Thread |
| Backfill | Checkbox | True if created during a historical run |
| Summary | Text | 2–3 sentence Claude-generated summary |
| Raw Notes | — | Full raw extract written to the **page body blocks** (no character limit). The Raw Notes *property* is not populated. |
| Gmail Link | URL | Permanent link to source email; used for deduplication |
| Sub-targets Touched | Multi-select | The fan-out funnel's considered set (Section 10) |
| Findings | Rollup | Findings produced from this encounter |
| Flags | Text | Serialised `self_review` JSON from extraction (corrections made + items flagged for user review). **Per-report self-review only** — candidate/change-approval data does NOT live here (Section 17). |

**Lead Provider is not used.** The Providers multi-relation is authoritative for all retrieval. "Last 3 appointments with provider X" queries the multi-relation (Appointments where Providers contains X, Status = Confirmed, sorted by date desc, take 3), so any provider can surface a meeting they attended. An optional "Report Author" attribution field is permitted in future, but no retrieval or archive logic may depend on it.

**Multi-provider meeting rule.** One Appointment record per meeting; all providers in the Providers multi-relation. Each extracted action is assigned to its specific provider in `Health Actions.Provider`. A physio's brief never surfaces actions assigned to the speech therapist from the same meeting (the brief reads `Health Actions.Provider`, not the meeting's full provider set).

### Database 2: Health Actions

| Field | Type | Notes |
|---|---|---|
| Title | Title | The action, written as a task |
| Source Appointment | Relation → Appointments | |
| Provider | Single relation → Providers | The specific owner of this action, even if from a team meeting |
| Sub-target | Relation → Sub-targets | Outcome-layer anchor (goal denormalised) |
| Strategy | Relation → Strategies | When the action enables a specific component |
| Assigned To | Select | Matt / Louise / Family / Provider / Doc / School / Other. Family = both parents addressed collectively. |
| Category | Select | Medical / OT / Speech / Physio / Other Allied Health / Admin / Equipment / Referral / Medication / NDIS / Meeting Action / Query Session |
| Priority | Select | High / Medium / Low |
| Status | Select | Open / In Progress / Done / Cancelled / Needs Triage |
| Due Date | Date | Only if explicitly stated in the report (hard due dates only) |
| Opened Date | Date | Auto-set on creation |
| Closed Date | Date | Set when Status → Done or Cancelled |
| NDIS Relevant | Checkbox | |
| Notes | Text | Context or updates |

`Needs Triage` is used exclusively during a historical run — excluded from all active views, briefs, digests, and bridge-task counts until triaged.

### Database 3: Goal Pages

A light roll-up page per goal (6 NDIS + Medical + Other). Body = a maintained per-sub-target digest (Section 3.1). Goal scope lives here and bounds Tier-2 adjacency. Fields: Title; Category; Plan Period; Goal Description (verbatim NDIS plan text, not FSSP-derived clinician summaries); Status (Active / Achieved / Modified / Discontinued); Sub-targets (relation, the children). **Supporting Providers is derived, not stored** — a goal/sub-target↔provider join table is omitted (27/06/2026); "who supports this" is a windowed query over `observations ∪ strategy_observations` source providers (Section 14), consistent with goals being roll-ups, not containers.

### Database 4: Providers

| Field | Type | Notes |
|---|---|---|
| Title | Title | Provider name / practice name |
| Aliases | Text | Comma-separated nicknames and initial forms (e.g. "Maddy, M. Tomlin"). Checked by the matcher and injected into the extraction provider list. |
| Type | Select | GP / Paed / Physio / OT / Speech / Psychology / Continence / Podiatrist / Dentist / Other Specialist / Hospital / NDIS support / School / Other. (No "Developmental Educator" option — dual-role providers filed under closest clinical type, dual role noted in Notes.) |
| Primary Email | Email | |
| Known Sender Emails | Multi-value text | All addresses that may send reports |
| Known Sender Domains | Text | Platform domains, e.g. "cliniko.com, halaxy.com" |
| Contact Phone | Phone | |
| Typical Report Format | Select | PDF / Email Body / Docx / Verbal Only |
| Appointment Frequency | Select | Weekly / Fortnightly / Monthly / Quarterly / Ad Hoc |
| Last Appointment | *(derived)* | Not stored — `MAX(appointment_date)` over this provider's appointments. |
| NDIS Funded | Checkbox | |
| Notes | Text | Portal logins, referral status, dual-role notes |

### Database 5: Agent Performance Log

Sender-detection audit trail with user feedback. Fields: Title; Logged Date; Sender Address; Sender Domain; Email Subject; Stage 1 Outcome (Known Sender / Domain Match / Keyword Match / No Match); Keyword Matched; Stage 2 Triggered; Stage 2 Outcome (Relevant–High / Relevant–Medium / Relevant–Low / Not Relevant); Stage 2 Reason; Final Decision (Auto-Processed / Flagged for Review / Skipped); Resulted In Record (relation → Appointments); Correct Decision (Yes / No / Unsure, user-completed); User Reasoning; Recommendation.

This log covers **sender detection only**. Outcome-layer agent performance (extraction quality, Pass 1 assessment, fan-out, candidate approve/reject outcomes) is captured separately — per-report self-review in the `Flags` field, plus the rationale/confidence fields on Observations (3.6) and Findings (3.5) and the candidate-decision record. A standing aggregation surface over that data is a Phase 5 build (see the outcome-layer performance/audit open item).

### Database 6: Health Actions Archive

Identical schema to Health Actions plus Archived Date and Archive Reason. Eligibility logic in Section 18 (archive).

### Digests & Briefs (page collection)

Not a database. Three sub-sections of child pages auto-created by the agent: Weekly Digests/ ("Week of YYYY-MM-DD"), Pre-Appointment Briefs/ ("Brief – Provider – Date"), NDIS Reports/ ("NDIS Report – Period – Generated Date").

---

## 17. The Candidates table — propose → approve (Decision I, RESOLVED 27/06/2026)

The two-layer propose→approve flow for **benchmark changes, promotions, strategy diffs, and corrections** is cross-cutting: one report can spawn candidates against many sub-targets, and weekly clustering spawns more. It **cannot** live in the appointments-scoped `flags` field (that is per-report extraction self-review, cleared at draft confirmation — a different mechanism). It has its own home: **one typed `candidates` table**, structured rows, **grouped by sub-target** in the review UI. The review surface is the Flask Candidates page, built day one (Section 8.4).

**Resolved (full spec in `decision-I-sqlite-schema.md`):**

- **(a)** One `candidates` table, **not** per-type tables, typed by a `change_class` enum: `benchmark-change` / `benchmark-correction` / `benchmark-revert` / `assessment-correction` / `adjacent-promotion` / `spin-out` / `strategy-diff` / `strategy-status-correction`. Each row also carries `origin` (system / manual).
- **(b)** Schema: the typed `change_class`; one primary target (sub-target / observation / strategy / strategy-obs); proposed `from_value → to_value`; a Haiku-written `reason`; source finding/observation IDs and triggering rule; `confidence`; lifecycle `status` (pending / approved / rejected / withdrawn) with typed `reject_reason_class` and `correction_reason_class`; `decided_by` / `decided_at`; a `backfill` flag; and a back-link to the change-log entry it produced.
- **(c)** Distinct from `flags` — two separate surfaces, confirmed.
- **(d)** On approval the handler writes **both** the mutation and (where a benchmark or strategy component actually moves) its Change Log entry — **except** the two in-place corrections (`assessment-correction`, `strategy-status-correction`), which mutate the derived value in place and write **no** log entry, because the approved candidate row *is* their permanent audit.

This table is the spine of the **gated-change engine** (the three-tier edit map, the one cascade / three triggers, the four correction cases, and typed override-capture) — all specified in `decision-I-sqlite-schema.md`. The structured-rows-not-JSON constraint and the distinctness-from-`flags` constraint are load-bearing on the review surface.

---

## 18. Pipeline operations

### Content extraction

All sources route through `prepare_content()` in `extract.py`. Claude always receives clean labelled text — never raw files.

| Source | Path |
|---|---|
| Native PDF (text-based) | pdfplumber |
| Scanned PDF (image wrapper) | pdfplumber quality check → Tesseract OCR (pytesseract + Pillow pre-processing) |
| Phone image (jpg/png) | Pillow pre-processing → Tesseract OCR |
| Docx | python-docx |
| Email body | BeautifulSoup (HTML stripped) |
| Email thread | Per-message extraction, assembled with sender/date labels |

Output format:

```
EMAIL BODY:
[text]

ATTACHMENT (filename.pdf):
[text]

THREAD MESSAGE 2 – From: sender@domain.com – YYYY-MM-DD:
[text]
```

**OCR quality check.** After pdfplumber extraction, check output character density. If output is below threshold (very short text from a multi-page document), assume a scanned image PDF and re-route to Tesseract — prevents garbled native-PDF-misidentified-as-scanned output reaching Claude.

**Structured skills tables.** Session notes with skills grids (e.g. Not Attempted / Benefits from Assistance / Independent columns) may lose column relationships through OCR. If table structure is uncertain in raw output, the extraction prompt instructs Claude to describe what was observed in each skill area rather than assert specific column placements — do not misattribute an X marker to the wrong column. A skill marked Independent is stronger evidence than one marked Benefits from Assistance, and is weighed accordingly in assessment.

### Extraction self-review (single pass)

Extraction and self-review happen in one Sonnet call — no separate Haiku review pass. Sonnet checks its output against a structured checklist before returning, then includes a `self_review` block in the JSON response. The serialised `self_review` JSON is written to the **Flags** field on the Appointment record (this is per-report self-review only; it is not the candidate/change-approval surface — Section 17).

**Sonnet auto-corrects and reports as FYI (`corrections_made`):**

- Speculative *action* language ("consider", "potential to", "may", "could", "in future") that is a one-off task → deleted, moved to the appointment Summary field. **Exception:** speculative language proposing an ongoing approach to a goal is a **strategy**, not noise — routed to strategy capture, not deleted (Section 7.1).
- Summary > 3 sentences → truncated
- Observation anchored to a **non-existent** sub-target (not in the injected sub-target list) → re-routed: to the correct existing sub-target where the finding has a clear direct subject, otherwise recorded as `Adjacent` on an Adjacent-watch / `Other/Unclassified` sub-target — never deleted (capture-broadly). A valid but un-benchmarked Adjacent-watch sub-target is **not** an error.
- Family member in a provider field → cleared
- Assigned To is Matt when the report addresses both parents → corrected to Family
- Priority inflation (>50% High) → weakest cases downgraded with reasoning

**Sonnet flags for user decision (`flags_for_review`):**

- First-name-only or combined provider names (cannot auto-correct)
- Unclear provider attribution in a multi-provider meeting
- Novel report format (low extraction confidence)

**Self-review checklist additions for the outcome layer:**

- Each observation's `Sub-target` belongs to the same goal as its denormalised `Goal`
- A fanned set sharing a Finding is a coherent *split* (fan-out sibling check, Section 4.3) — this runs at extraction and concerns the split itself. The **assessment**-coherence sibling check (Above/Regression contradiction on one finding) runs at **Pass 1** (confirmation), since grades don't exist at extraction.
- An `Adjacent` record exists only where the finding's direct subject is that adjacent area (Section 4.1) — not as a second copy of a finding with a benchmarked home

**JSON response structure (extraction — unassessed shells):**

```
{
  "appointment": { ...corrected... },
  "findings": [ ...each with fan_out_rationale + fan_out_confidence... ],
  "observations": [ ...each sub-target-anchored, UNASSESSED (assessment null; assessment_rationale + assessment_confidence are written later at Pass 1, at confirmation)... ],
  "strategy_observations": [ ... ],
  "actions": [ ...corrected... ],
  "sub_targets_touched": [ ... ],
  "self_review": {
    "corrections_made": [ { rule, original, action_taken, confidence } ],
    "flags_for_review": [ { type, item, extraction_used, suggested_action, confidence } ],
    "extraction_confidence": "high/medium/low",
    "corrections_count": N,
    "flags_count": N
  }
}
```

Original text is always preserved in `corrections_made` so a correction can be reversed. The dashboard extraction-review tab renders `flags_for_review` as interactive cards; `corrections_made` shown as read-only, collapsible FYI.

### Archive logic

Run in `archiver.py`. **Pure logic, no Claude call.** An action is eligible to archive when both:

1. Status is Done or Cancelled (Needs Triage is never archived — triage first)
2. Its source appointment is NOT within the **last 3 confirmed appointments for that action's own `Health Actions.Provider`**

"Last 3 confirmed appointments for provider X" = Appointments where `Providers` contains X AND Status = Confirmed, sorted by Appointment Date desc, take 3. The check is **per provider, not global** — an annual specialist retains closed actions far longer than a weekly physio. This is correct behaviour. Keyed off `Health Actions.Provider` and the Providers multi-relation — no Lead Provider.

---

## 19. Scheduled jobs, bridge task, Health Summary

### Scheduled jobs

| Job | Schedule |
|---|---|
| Email poll + ingest | Every 4 hours |
| Appointment scan (Google Calendar, 7-day look-ahead) | Daily 07:00 |
| Brief generation | **Sunday 07:00** (after weekend draft review) |
| Saturday sequence | Saturday 07:00 |
| Review reminder (if drafts still unconfirmed) | Saturday 09:00 |
| Staleness + promotion-clustering review | Weekly |

**Brief timing.** Pre-appointment briefs do not run on the daily/Saturday job. They run **Sunday morning**, after the primary user has had the weekend to confirm draft records, so briefs are built from confirmed data. Force-brief via dashboard or email trigger if needed sooner.

**Saturday sequence (in order):**

1. Weekly health digest → save to Notion
2. Archive eligibility check → move qualifying actions
3. Draft record summary (corrections made + flags needing review, per draft)
4. Performance review page → dashboard
5. Email: health digest → both users
6. Email: draft review summary + performance review link → primary user only
7. Bridge task → main Notion task DB (post-archive counts, excluding Needs Triage)

### Bridge task

Written to the primary user's existing Notion task database each Saturday.

```
Title:    "Health actions weekly review"
Job:      Personal  |  Project: Home
Status:   2. To Do  |  When: 2. Monday
Due Date: (empty)
Notes:    "X open, Y overdue, Z upcoming. [digest link]"
```

Counts exclude Needs Triage actions.

### Health Summary

A static, curated Notion page (not a database) — biographical overview, formal diagnoses, key medical events, developmental history, current medications/equipment, current providers and roles, NDIS plan history, what works / what doesn't, and things new providers should know. Written manually before Phase 3 go-live from existing NDIS plans, specialist letters, and school reports; Claude drafts a structured summary, the primary user edits into the final version. Not extracted programmatically.

Included as standing context in: the pre-appointment brief prompt, the query engine system prompt, the NDIS/DIP report prompt, and the new-provider brief. (Stored as a static curated document local to the system — not engine data; a single authored record, manually maintained.)

**Agent behaviour:** never overwrites. When extraction identifies a new diagnosis, significant medical event, or milestone not already in the summary, it flags it as a suggested addition for user approval via the dashboard. (The ASD Level 2 diagnosis was added this way — user-approved, not agent-written. Report recommendations / intervention strategies go to the Health Summary "What works" section, not the extraction context, since they are strategy and would risk being mis-extracted as actions.)

**New-provider brief (Health Summary + selected sub-targets).** A dashboard button → Claude Sonnet produces a clean one-to-two-page clinical handover document, saved to Digests & Briefs. Tone: concise, professional, written for a clinician reading it for the first time. Two parts:

- **Who Tom is** — the Health Summary reformatted (biographical overview, diagnoses, history, what works).
- **Where Tom is on the relevant areas** — current-state on a **manually selected set of sub-targets** (current benchmark + active strategies + recent trajectory per selected sub-target). The selection is a generation-time input (a multi-select of sub-targets), **not** a stored provider relation — so onboarding a new OT, you pick the sub-targets that OT will work on, and the brief carries Tom's history plus exactly those current states.

This manual-selection path is the general-purpose **curation** capability (a focused custom brief for any provider, any sub-target set), and it is what gives the new-provider case "full flexibility" — it needs no derived history, so the brand-new-provider edge case (Section 14) is just the manual path with an empty rotation. Phase 4 brief-builder feature; zero schema impact (selection is a list of sub-target ids passed to the generator).

---

## 20. Model assignments

| Task | Model |
|---|---|
| Report extraction + fan-out + attribution + strategy-vs-noise + self-review (unassessed shells) | claude-sonnet-* (latest) |
| Pass 1 per-record assessment (at confirmation; scoped to touched sub-targets) | claude-haiku-* (latest) |
| Regression / progression / addition (Pass 2) | **No Claude call — pure logic** |
| Strategy set-diff (Pass 2 match) | claude-haiku-* (latest) |
| Promotion clustering (weekly) | claude-haiku-* (latest) |
| Staleness detection | **No Claude call — pure logic** |
| Candidate reason-summary | claude-haiku-* (latest) |
| Benchmark / strategy update on approval | claude-haiku-* (latest) |
| Goal-page roll-up digest | claude-haiku-* (latest) |
| Stage 2 sender detection | claude-haiku-* (latest) |
| Pre-appointment brief | claude-sonnet-* (latest) |
| Weekly health digest | claude-sonnet-* (latest) |
| Performance recommendations | claude-haiku-* (latest) |
| Query retrieval planning | claude-haiku-* (latest) |
| Query answer synthesis | claude-sonnet-* (latest) |
| Session write-back extraction | claude-haiku-* (latest) |
| NDIS / DIP report generation | claude-sonnet-* (latest) |
| Archive eligibility check | **No Claude call — pure logic** |

Always use the latest available version of the assigned tier. Do not hardcode version strings.

---

## 21. Build phases

Phase 1 (foundations) and Phase 1b (validated 3-report extraction) are complete: the front-half pipeline reads reports, matches providers, and runs single-pass self-review against three real reports (individual OT note, speech group session, multi-provider FSSP). The outcome layer is built from Phase 1c.

**Phase 1c — Goal-centric restructure (stand up the SQLite store).** Create the local SQLite database and stand up the outcome-layer tables per `decision-I-sqlite-schema.md`: **Sub-targets as the working record** (goal/DIP/NDIS-outcome tags), Goal Pages (6 NDIS + Medical + Other, roll-up), Benchmark Change Log, Strategy Change Log, Findings, Observations, Strategy Observations, Strategies (one row per component), the typed **Candidates** table, Health Actions (re-anchored to sub-target), Appointments (+ `Sub-targets Touched`), Providers, Archive. Enforce the append-only change-log triggers and the `CHECK` constraints. Seed the **36-row sub-target spine** (Decision A) two-anchored: year-ago FSSP Baseline + the 13/06 hand-written benchmark as latest-confirmed. Seed Other's 4 candidate domains as Adjacent-watch (Sleep seeded Active), the 5 Medical watch domains, and the 2 holding pens. Stand up the day-one **Flask Candidates review page** and the nightly off-box backup. *Both Phase 1c blockers are now closed (Decision A 25/06, Decision I 27/06); the structural build is unblocked.* The five gap-blank seed values (Section 25) gate the **data load** (1d), not this structural build — the spine can be stood up with those five rows benchmark-blank and filled before the load. No MCP connection is involved (engine is local SQLite, not Notion).

**Phase 1d — Engine rework + historical data load.** Build the entry flow and the engine behind the confirmation gate (Section 6): extraction produces **unassessed observation shells** (fan-out + per-sub-target materiality, Section 4.1, + attribution); **Pass 1 assessment runs at confirmation** as a scoped Haiku call using the shared `assess()`; **Pass 2 reconciliation** (pure logic) runs at confirmation and during the data load (recency + staleness + cadence analytics). The full gated-change cascade and the typed candidate flow (`decision-I-sqlite-schema.md`), including the Finding-grain wrong-fact correction (Section 6.1.1) and the renamed report-retraction trigger. Strategy two-pass capture (recognise+tag → set-diff writing a Strategy Observation per mention + change candidates), thin active-title injection, stated-only effectiveness, staleness flag, **strategy-lane two-anchor seed** (Section 8.2.1). Sibling-aware self-review across both running logs. Strategy-vs-noise self-review change. Safety-critical alert path (keyed off the capture-time severity screen, Section 6.2). Then the **historical data load** — both lanes two-anchored, oldest-first, sequential benchmark advancement, via direct report feed; reviewed on the Flask Candidates page; re-validate against the 3 test reports. One-off manual brief mock-up as a structure check.

**Dashboard view-design step (before Phase 4; Candidates page in 1c).** The sub-target detail page and the goal roll-up were free Notion affordances; on Flask/SQLite they are real builds (templated filtered queries over the store). Design the three sibling views together — the **Candidates review page** (built day-one in 1c), the **sub-target detail page** (the benchmark + embedded observation/strategy/history views the briefs and queries read), and the **goal roll-up** (including its storage choice: cached column vs regenerate-on-view) — before they are needed. Candidates page lands in 1c; the sub-target and roll-up views build into Phase 4.

**Phase 2 — Ingestion + ingestion backfill.** Sender detection (Stage 1 rules + Stage 2 Haiku), subject-pattern detection, deduplication, email thread handling, multi-provider record creation, draft creation, review notification email. Then the **email-identification backfill** over inbox history, refined via the performance-review loop. Distinct from the Phase 1d data load (Section 8.3).

**Phase 3 — Transition & end-to-end validation.** The knowledge base is already populated and tuned by this point: Providers, Goal Pages and Sub-targets are built/seeded in 1c and populated with a year of real data in 1d, and extraction tuning happens against the 1d data-load candidate queue — so Phase 3 is not a build phase but a transition gate. **(1)** Full **end-to-end integration check** of the path the 1d direct-feed could not exercise: a real email → sender detection → thread/chain assembly → dedup across both inboxes → extraction → fan-out → assessment → candidate → confirmation → brief, as one validated flow (email-chain handling, dedup, and detection-into-extraction are first tested here, not in 1d). **(2)** Write the **Health Summary** (manual content task, Section 19) if not already done, before outputs go live. *(The earlier Phase 3 step "sever the MCP connection" is now moot — with SQLite as the system of record (Section 3.0), engine data never enters Notion and there is no live MCP data connection to sever. If the optional Notion report-mirror is ever built, it uses a dedicated write-scoped token pushing generated reports only — see Section 23.)* Phases 4–6 run against the Pi's local store.

**Phase 4 — Outputs & dashboard core.** Goal-structured pre-appointment brief generator (with the forcing-function / parent-observation / live-capture design, Section 14.1), weekly digest, Saturday job sequence, bridge task, email delivery. Flask dashboard: status page, manual triggers (force ingest / force brief / NDIS report), backfill page with triage workflow.

**Phase 5 — Performance review & self-improving loop.** Interactive performance-review page; accept/reject recommendation workflow; settings.yaml write-back; Stage 2 prompt improvement; cron setup; error logging and silent-failure alerts. This is where the dashboard radio-button review surface lands (Section 8.4).

**Phase 6 — Query interface & session write-back.** Dashboard query page with two-step retrieval; source attribution; conversation history; end-of-session write-back approval panel (routing change-proposals through the candidate gate); NDIS/DIP query-report capability.

---

## 22. Feature flags

All major capabilities are gated in settings.yaml. Build everything; activate when ready.

```yaml
features:
  email_polling: false
  stage_2_detection: false
  pre_appointment_briefs: false
  weekly_digest: false
  performance_review: false
  backfill_mode: false            # historical data load / ingestion backfill
  query_interface: false
  session_writebacks: false       # enable after ~3 months of live data
  ndis_query_report: false        # enable when plan review approaches
```

Feature flags are checked at runtime, not import time. Any function implementing a gated capability checks the relevant flag and returns gracefully if disabled.

---

## 23. Key decisions, data isolation & conventions

### Data isolation (now largely moot under SQLite)

With **local SQLite on the Pi as the system of record** (Section 3.0, 27/06/2026), health data never enters Notion, so the original cross-role MCP-exposure risk no longer applies and there is no live MCP data connection to sever. The Pi agent reads and writes its local database **through code**, not through any MCP connector.

The earlier mitigation — *separate Notion account/workspace for Health Hub; connect via MCP for structural setup only; sever at Phase 3; Pi agent on a dedicated scoped token* — is **superseded** for the engine. It remains relevant only in the narrow optional case of the **one-way Notion report-mirror** (Section 3.0): if built, it pushes *generated reports only* (no raw clinical record) to a separate Health-Hub Notion space via a dedicated **write-scoped** token, and that — not the engine — would be the only Notion surface. Building the mirror reopens this isolation question for that surface alone; until then, isolation is achieved structurally by the engine simply not being in Notion.

### Selected key decisions

- **System of record is local SQLite on the Pi** — not Notion; engine ops are SQL-shaped and corrections need atomic recompute Notion can't do. Flask dashboard as UI; nightly off-box backup non-negotiable from day one; one-way Notion report-mirror optional/deferred.
- **Decision I — one typed Candidates table** — structured rows, grouped by sub-target, distinct from `flags`; the Candidates review page is day-one, the primary interface for the 1d data load. It anchors the gated-change engine (three-tier edit map; one cascade / three triggers; four correction cases; typed override-capture). Full spec: `decision-I-sqlite-schema.md`.
- **Decision A — 36-row sub-target spine** — 25 goal-area + 4 Other + 5 Medical + 2 holding pens; single NDIS-goal + single DIP-domain tag each; SSG goals are a projection lens, not new structure.
- **Goal-centric spine** — the durable, queryable object is the sub-target, not the appointment. Encounters remain the evidence layer.
- **Frameworks are projections** — NDIS annual, the DIP school review, and the termly SSG view are saved roll-ups over one dataset (DIP-domain + NDIS-outcome tags on each sub-target).
- **Capture broadly, assess tightly** — every finding mapping to a sub-target is recorded; the tight gate is on benchmark *change* (candidate → approved), not on recording.
- **Pass 2 is pure logic** — regression/progression/addition is deterministic arithmetic over dated assessments, not an LLM call; idempotent against approved state and gate-tight (active + confirmed observations only).
- **Strategies are a maintained inventory** — set-diff, two logs, stated-only effectiveness, human-only retirement-by-neglect; no Trial/Established flag.
- **Nothing auto-edits a benchmark** — all changes route through the candidate gate; over-fan produces visible candidates, not silent edits.
- **Lead Provider dropped** — Providers multi-relation is authoritative for all retrieval; archive keys off each action's own `Health Actions.Provider`.
- **Overdue = hard due dates only** — only explicit provider-stated deadlines; open count is the primary metric.
- **Two-anchored real data load** — year-ago FSSP Baseline + hand-written current benchmark; convergence is the validation signal; Pass 2 advances the benchmark sequentially during the load.

### Coding conventions

- All writes/inserts check for an existing record first (deduplication)
- All Claude API calls in try/except; errors logged to `logs/`
- Log files contain metadata only — never report text, names, or clinical content
- settings.yaml is the single source of truth — no magic strings in `src/`
- Prompts live in settings.yaml, read at runtime — never hardcoded in `src/`
- Extraction prompt injection uses `###PLACEHOLDER###` substitution, never `.format()`/f-strings (JSON braces in the prompt body)
- Gmail OAuth tokens in `config/` — in `.gitignore`
- Each module independently runnable with an `if __name__ == "__main__"` test block
- Dashboard routes must not block — long-running tasks (Claude API, bulk DB reads) run async or via a background thread
- Derived/gated values are never raw-edited — corrections route through the candidate gate; change logs are append-only (enforced by trigger). See the three-tier edit map in `decision-I-sqlite-schema.md`
- Feature flags checked at runtime, not import time

---

## 24. Technical dependencies & deployment

### Dependencies

| Library | Purpose |
|---|---|
| `sqlite3` (Python stdlib) | **System-of-record store** — no external dependency; the local health database |
| `google-auth`, `google-auth-oauthlib`, `google-api-python-client` | Gmail and Google Calendar API |
| `notion-client` (pinned 2.2.1) | **Optional** — only if the one-way Notion report-mirror is built (Section 3.0); not required for the engine |
| `anthropic` | Claude API |
| `pdfplumber` | Native PDF text extraction |
| `pytesseract` + `Pillow` | OCR for scanned PDFs, images, phone photos |
| `python-docx` | Docx extraction |
| `beautifulsoup4` | HTML email body stripping |
| `python-dotenv` | Secrets management |
| `schedule` | Job scheduling |
| `flask` | Local web dashboard (UI + Candidates review) |

System-level Pi install: `sudo apt install tesseract-ocr`.

### Deployment platform

Raspberry Pi 5 8GB (sourced from Core Electronics AU; Crucial X9 Pro 1TB SSD — supersedes the earlier Samsung T7). Tailscale for remote access; SSH key-only authentication. The Pi is live (the custom MCP server and OAuth/Tailscale-Funnel stack are deployed and validated). Full hardware spec, Pi security baseline, and the **build-environment migration from the Windows laptop to the Pi (via Remote Control)** live in **PRS · Pi & Agent Setup**.

The early Phase 1/1b development ran on a Windows laptop; the build is now **moving to the Pi as the primary development and deployment target** (worked through under PRS · Pi & Agent Setup). The Windows-specific notes below are retained as historical/fallback reference:

- **Tesseract on Windows:** UB-Mannheim installer; set `pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'` if not on PATH.
- **Gmail OAuth on Windows:** browser opens normally; token files are reusable on the Pi — copy `config/` across at migration.
- **Flask:** `http://localhost:5000` in dev; `--host=0.0.0.0` and the `healthagent.local` hostname are Pi-specific.
- **venv:** activate with `venv\Scripts\activate`.

**Pi migration (≈1 hour, deploying working code):** push repo / scp to Pi → copy `config/` including OAuth tokens → create venv and install deps → `sudo apt install tesseract-ocr` → run `test_pipeline.py` → set up cron (Phase 5).

### Estimated API cost

~30,000–35,000 tokens/week at steady state (slightly higher with query usage), roughly $15–25 AUD/year at current Sonnet/Haiku pricing. Higher during the data-load and tuning phases. The outcome-layer redesign keeps steady-state cost close to the front-half-only model — the expensive call stays at one Sonnet extraction per report; Pass 2 is logic, and time-based reviews run weekly (Section 6.5). Recompute the per-report profile at Phase 1d once it is real. Load the API account with ~$20 AUD to start.

---

## 25. Open decisions & deferred items

### Phase 1c blockers — BOTH CLOSED

- **Decision A — sub-target spine** — RESOLVED 25/06/2026 (Section 3.2.1): 36-row spine, single-tag rule, splits, SSG-as-lens, medical holding pen, DIP naming fix.
- **Decision I — candidate/change-approval schema + data layer** — RESOLVED 27/06/2026 (Section 17, Section 3.0): one typed Candidates table, SQLite system-of-record, the full gated-change engine. Spec: `decision-I-sqlite-schema.md`.

The **structural build (Phase 1c) is unblocked.** The remaining precondition is a *data-load* dependency, not a structural one:

- **Five gap-blank seed values** (precondition for the two-anchored data load, Phase 1d — not for standing up the spine). Seed-state still needed for **Fine Motor** (current level), **Continence-medical**, **Gastro**, **Dental**, **Growth** — data may be in unseen reports or the domain is genuinely quiet. The spine can be stood up in 1c with these five rows benchmark-blank; fill before the load.

### Open, non-blocking

- **Report retraction during the oldest-first data load** (Phase 1d runbook). Draft retraction is now trivial (assessment-behind-the-gate: a draft has nothing derived, so deletion replays nothing). The genuinely hard case is **confirmed-report retraction** — during the load, reports must be confirmed to advance benchmarks, so pulling a mid-sequence report means undoing state downstream observations were assessed against. The cascade handles the *mechanism* (the renamed "report retraction (draft = trivial; confirmed = cascade)" trigger); what remains is the *operational runbook for the ripple ordering*. Bounded, not closed; not blocking the 1c structural build.
- **`recompute_audit` home** — a lightweight per-observation recompute trail (live only): a dedicated small table vs a JSON column on the observation. Minor; decide at build.
- **Notion report-mirror — build in v1 or defer?** The one-way push of generated reports to Notion (mobile browse + share-a-report) is low-risk but still code to own. Current lean: **defer** — ship local-only, add the mirror only if mobile browse genuinely nags.
- **Goal roll-up storage** — the Haiku-maintained per-goal digest no longer has a Notion page body to live in; decide cached column (regenerated on change) vs regenerate-on-view. Folds into the dashboard view-design step (Phase 1d/4).
- **Outcome-layer performance aggregation surface** (Phase 5). Per-decision reasoning capture is resolved (typed override-capture, baked into the 1c schema). What remains is the standing aggregation/review surface consuming `flags` + assessment-reasoning + candidate-decision data — an extension of, or distinct from, the sender-detection Agent Performance Log. TBD at Phase 5.
- **Multi-source encounter reconciliation — timing residual only** (Phase 2/3). The core is resolved (Section 13.1): two sources of one encounter are matched to one draft encounter and reconciled before draft exit — bound to one Finding or marked corroboration-not-counted, so Pass 2 never double-counts; divergence flagged, never silently merged. The **residual** is the case where the first source was already *confirmed* before the second arrives — then the second is new evidence on a confirmed encounter (routes through the candidate gate), not a pre-draft reconciliation. Settle that timing rule so "reconcile before draft exit" is always achievable.
- **Manual-candidate entry UI** — the `origin='manual'` path exists in the schema (false-negative case: a true slow progression read as a defensible run of `At`); the dashboard affordance to raise one is a Phase 4/5 build.
- **Query-interface delivery** — built as designed (API pipeline: Haiku retrieval-plan → code fetch → Sonnet synthesis). A Pi-MCP-server + Claude.ai route is a deferred enhancement, reopened only if live query performance proves lacking (read-path only; write-back stays code-gated; reopens the Section 23 isolation question — explicit sign-off required).
- **LC "identify parts of objects" sub-target intent** — component-naming vs body-parts/spatial; captured broadly in the benchmark with an inline flag; confirm with the NDIS plan or speech pathologist when speech support resumes.
- Secondary (Louise's) Gmail OAuth authorisation — completed at setup.
- Dashboard authentication — home network only; a `users` table (admin/carer roles) sits alongside the schema for Flask auth/role-gating. Low priority.
- Session write-back activation timing — recommended ~3 months after go-live.

### Deferred to implementation planning (not design gaps)

- **"What is one finding"** — the delimitation rule for the Findings table (clinical claim vs sentence vs clause) is prompt-tuning, settled against real reports in Phase 1d.
- **Two-anchored seeding procedure** — the runbook for writing both anchors across the **36** sub-targets (is the year-ago FSSP hand-entered or machine-extracted?) is a Phase 1c/1d operational step.
- **Build-environment migration (Windows → Pi)** — moving the development environment to the Pi via Remote Control. Operationalised under **PRS · Pi & Agent Setup**.
- **Updated token-cost estimate** — recompute at Phase 1d once the per-report call profile is real.
