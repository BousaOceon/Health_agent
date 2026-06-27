"""Phase 1c seed data — the 36-row sub-target spine + 8 goal pages.

Source of truth: "Decision A — sub-target spine (36 rows), 25/06/2026" + the
13/06 hand-written benchmarks pulled from the (legacy) Notion NDIS Goals DB.

Seeding rules agreed for 1c:
- 17 "carry" sub-targets: 13/06 benchmark line lifted from Notion verbatim.
- 8 "carved": the 5 setting-splits use the fuller Notion text as the benchmark
  and the Decision-A split wording as scope_line; the 3 behaviour carves (split
  from the single "Manage big behaviours" line) use the Decision-A carved text.
- current_benchmark / benchmark_as_of live on the row (2026-06-13). The
  benchmark_change_log is NOT seeded here — both anchors (FSSP Baseline + 13/06)
  are written in Phase 1d so the append-only log stays chronologically correct
  (avoids a double-Baseline). FSSP Baseline is deferred to the start of 1d.
- 5 gap-blanks (Fine Motor / Continence / Gastro / Dental / Growth) + Sleep +
  Dysphagia seed benchmark-blank; filled before the 1d data load.
- ndis_outcome_domain is left NULL for every row — Decision A resolved NDIS-goal
  + DIP + SSG only; the NDIS Outcomes Framework tag is a later projection task.
"""

BENCH_DATE = "2026-06-13"

# DIP domains (the 6 canonical Victorian DIP Functional Needs domains)
DIP_SELF_CARE = "Self-Care"
DIP_COMMUNICATION = "Communication"
DIP_INTERPERSONAL = "Interpersonal Interactions"   # naming fix (not "...& Relationships")
DIP_GENERAL_TASKS = "General Tasks & Demands"
DIP_MOBILITY = "Mobility"
DIP_LEARNING = "Learning & Applying Knowledge"

# SSG lens
SSG_IND = "Independence"
SSG_PART = "Participation"
SSG_ER = "Emotional Regulation"


# ---------------------------------------------------------------------------
# Goal pages (6 NDIS + Medical + Other)
# ---------------------------------------------------------------------------

GOAL_PAGES = [
    {
        "id": "goal_self_care", "title": "Self-Care Independence", "category": "NDIS",
        "plan_period": "2025-2026", "status": "Active",
        "scope": "Tom's independence in daily living and personal care — dressing, toileting, "
                 "hand hygiene, eating and drinking, and personal safety awareness — across home and school.",
        "goal_description": "Louise and Matt would like for Tom to continue to develop his self-care skills.\n\n"
            "Plan targets (2025-2026):\n"
            "- Learn strategies to assist him in developing personal safety awareness.\n"
            "- Participate in 50% of dressing tasks e.g. pulling nappy or socks up.\n"
            "- Progress with his toileting independence and notify unfamiliar adults when he requires a nappy change.\n"
            "- Wash and dry his hands independently.\n"
            "- Drink from an open cup.\n"
            "- Safely chew larger pieces of harder foods, requiring less assistance for safe swallowing.\n\n"
            "FSSP interpretation (June 2025):\n"
            "- Hand washing independence includes being able to manipulate bathroom taps at school and home.\n"
            "- Toileting progress may need to account for any underlying medical factors influencing toileting.",
    },
    {
        "id": "goal_lang_comm", "title": "Language and Communication", "category": "NDIS",
        "plan_period": "2025-2026", "status": "Active",
        "scope": "Tom's expressive and receptive language, speech clarity, social use of language, and "
                 "functional communication across settings. Note: for Tom, the barrier to expressive tasks is "
                 "often articulation (word length and sound complexity) rather than underlying knowledge or comprehension.",
        "goal_description": "Louise and Matt would like for Tom to continue to develop his language and communication skills.\n\n"
            "Plan targets (2025-2026):\n"
            "- Use spoken language to join in with other children or let them know when he needs his space at kinder.\n"
            "- Identify parts of objects.\n"
            "- Follow 3 step commands.\n"
            "- Recall recent events with minimal prompting.\n"
            "- Improve his speech clarity.\n"
            "- Use 'mine' and 'me' when referring to himself most of the time.",
    },
    {
        "id": "goal_play", "title": "Play Skills", "category": "NDIS",
        "plan_period": "2025-2026", "status": "Active",
        "scope": "Tom's social and play development — tolerance of peers, reciprocal and cooperative play, "
                 "play repertoire (including sensory and pretend play), and safety awareness within play and social environments.",
        "goal_description": "Louise and Matt would like for Tom to continue to develop his social and play skills.\n\n"
            "Plan targets (2025-2026):\n"
            "- Tolerate others playing in his immediate space without wanting to move away.\n"
            "- Scan his environment to ensure safety (with prompts from adults as required).\n"
            "- Engage in age-appropriate play skills such as reciprocal play with others at kindergarten.\n"
            "- Be comfortable to engage in new sensory styles of play such as playdoh and paints.\n\n"
            "FSSP interpretation (June 2025) - what developing these skills may include:\n"
            "- Developing pretend play skills.\n"
            "- Engaging in reciprocal interactions with a small group of peers, including shared aims and responding to others' ideas.\n"
            "- Playing games with peers involving simple rules.\n"
            "- Responding to requests from others during play, including respecting personal space.",
    },
    {
        "id": "goal_feelings", "title": "Feelings and Emotions", "category": "NDIS",
        "plan_period": "2025-2026", "status": "Active",
        "scope": "Tom's emotional recognition, regulation, and coping; anxiety and distress responses; and the "
                 "supports and strategies that help him manage strong emotions across settings.",
        "goal_description": "Louise and Matt would like for Tom to continue to develop his emotional skills.\n\n"
            "Plan target (2025-2026):\n"
            "- Learn strategies to manage his big behaviours.\n\n"
            "FSSP interpretation (June 2025) - what managing big behaviours may include:\n"
            "- Relaxation strategies to aid anxiety (e.g. breathing, recognising stress vs calm).\n"
            "- Emotional literacy - differentiating between emotional states and physical sensations.\n"
            "- Coping strategies and behavioural alternatives in response to overload, frustration, or perceived lack of control.\n"
            "- Practical strategies for waiting.\n"
            "- Social learning skills (e.g. simple checklist for social interaction with a teacher).",
    },
    {
        "id": "goal_gross_motor", "title": "Gross Motor Skills", "category": "NDIS",
        "plan_period": "2025-2026", "status": "Active",
        "scope": "Tom's physical mobility, balance, coordination, stamina, and ball/object skills across home, "
                 "school, and community. Includes gross motor confidence and participation in physical/community activities.",
        "goal_description": "Louise and Matt would like for Tom to continue to develop his gross motor skills.\n\n"
            "Plan targets (2025-2026):\n"
            "- Walk independently and confidently across different grounds and terrains, and steps, without supports, and increase his stamina and range.\n"
            "- Develop his ball skills to catch and throw with increasing accuracy towards a target.\n"
            "- Continue to participate in community activities.\n\n"
            "FSSP interpretation (June 2025) - additional clinical context:\n"
            "- Terrain independence includes independent navigation of steps and stairs at home and at school, with supervision only.\n"
            "- Musculoskeletal integrity through legs and feet should be maintained, with orthotic devices reviewed as required.",
    },
    {
        "id": "goal_school", "title": "School Environment", "category": "NDIS",
        "plan_period": "2025-2026", "status": "Active",
        "scope": "Tom's comfort, endurance, independence, and safety within the school setting and other new or unfamiliar environments.",
        "goal_description": "Louise and Matt would like for Tom to continue to be more comfortable and independent in his school environment.\n\n"
            "Plan targets (2025-2026):\n"
            "- Build his fatigue levels.\n"
            "- Understand the dangers around him in new environments.",
    },
    {
        "id": "goal_medical", "title": "Medical", "category": "Medical",
        "plan_period": "", "status": "Active",
        "scope": "Tom remains generally healthy within the known limits of his diagnoses (Chromosome 18p deletion, "
                 "mosaic Trisomy 13, hypotonia, dysphagia). Sub-targets are watch/focus domains read on a status axis "
                 "(worsening/stable/improving), not a capability axis. A Severity flag drives escalation.",
        "goal_description": "Tom remains generally healthy within the known limits of his diagnoses. Medical sub-targets "
            "track watch/focus domains aligned to his specialists (dysphagia/airway, gastro, dental, growth, continence). "
            "Findings are screened for severity at capture even when un-benchmarked ('screened, not silent').",
    },
    {
        "id": "goal_other", "title": "Other", "category": "Other",
        "plan_period": "", "status": "Active",
        "scope": "Defined by exclusion: developmentally or clinically relevant findings not covered by a current goal area. "
                 "Candidate domains live here as Adjacent-watch sub-target rows; Other/Unclassified is the last-resort holding pen.",
        "goal_description": "Developmentally or clinically relevant findings not covered by a current NDIS goal area. "
            "Candidate domains accumulate as Adjacent-watch rows and may be promoted to Active (or spun out to their own "
            "goal page) once data concentrates; Unclassified is reviewed to be emptied.",
    },
]


# ---------------------------------------------------------------------------
# Sub-targets (36). Helper keeps rows readable.
# ---------------------------------------------------------------------------

def _st(id, title, goal_id, dip_domain, dip_activity, ssg, scope_line,
        benchmark=None, *, ndis=1, status="Active", severity=None):
    return {
        "id": id, "title": title, "goal_id": goal_id,
        "dip_domain": dip_domain, "ndis_outcome_domain": None,
        "ssg": ssg, "reporting_subgroup": dip_activity, "scope_line": scope_line,
        "current_benchmark": benchmark,
        "benchmark_as_of": BENCH_DATE if benchmark else None,
        "ndis": ndis, "status": status, "severity": severity,
    }


SUB_TARGETS = [
    # --- Self-Care (6) ---
    _st("st_personal_safety", "Personal safety awareness", "goal_self_care",
        DIP_SELF_CARE, "safety", None,
        "Knows what is dangerous — recognising/responding to known physical hazards (roads, hot, sharp) in "
        "everyday/home/community life; includes interoception-driven safety (helmets, pain, illness).",
        "Does not notice everyday hazards (roads, hot things, sharp objects) without prompting, and often ignores "
        "prompts - frequently must be physically stopped. Compounded by atypical interoception (unreliable "
        "pain/temperature/hunger recognition; has under-communicated serious illness). Refuses helmets."),
    _st("st_dressing", "Dressing", "goal_self_care",
        DIP_SELF_CARE, "dressing", None,
        "Independent dressing - putting on/removing clothing, shoes, socks. Plan target: participate in 50% of dressing tasks.",
        "Partial participation with setup and physical help. Can pull some loose pants down when the tie is undone for him "
        "(often needs help starting or positioning hands). Removes shoes if Velcro is undone; socks only sometimes, often "
        "needs hands positioned. Cannot remove shirt or jumper (arms or head), including zip/button tops. With stability "
        "support, can step into pants/shorts if an adult holds them and pull up to near the bottom, but not fully up. Once a "
        "top is in position can push an arm through but cannot position himself. Cannot put on shoes or socks."),
    _st("st_toileting", "Toileting", "goal_self_care",
        DIP_SELF_CARE, "toileting", None,
        "Toileting independence and notifying adults (including unfamiliar) of toileting needs.",
        "Remains in nappies day and night; working with continence physiotherapist (Sarah Henderson). Notifies a familiar "
        "adult of nappy-change need ~30-50% of the time; has occasionally asked to sit on the toilet unprompted but not "
        "regularly. Would never notify an unfamiliar adult. Sensory aversion affects personal care."),
    _st("st_hand_washing", "Hand washing", "goal_self_care",
        DIP_SELF_CARE, "washing", None,
        "Washing and drying hands independently, including manipulating taps at home and school.",
        "Needs support throughout. Can put hands under water; can use a soap dispenser only if it needs light pressure; "
        "usually needs help to rub hands together effectively. Will attempt drying only if the towel is supported (held or "
        "hanging) and needs help to dry effectively."),
    _st("st_open_cup", "Drinking from an open cup", "goal_self_care",
        DIP_SELF_CARE, "drinking", None,
        "Drinking from an open cup (vs a straw). Note dysphagia / choking risk with liquids.",
        "Always drinks with a straw; no open-cup use currently. Choking risk with liquids; modified diet; Paediasure supplement."),
    _st("st_chewing", "Chewing harder / resistive foods", "goal_self_care",
        DIP_SELF_CARE, "eating", None,
        "Safely chewing larger/harder foods with less assistance for safe swallowing. Dysphagia / choking risk.",
        "Dysphagia; modified-texture diet; choking risk with dry/crunchy foods and liquids; overfills mouth unless closely supervised."),

    # --- Language & Communication (6) ---
    _st("st_spoken_language", "Expressive spoken language - school", "goal_lang_comm",
        DIP_COMMUNICATION, "expressive", None,
        "Using spoken language to join in with peers or assert his need for space, at school.",
        "(Plan wording says \"at kinder\"; Tom is now in Grade 1 - read as \"at school\".) Uses spoken language but "
        "conversation is often one-sided, scripted, and focused on his interests; repetitive questioning/reassurance-seeking. "
        "Working on using language to advocate for personal space. No current 1:1 Speech (waitlist)."),
    _st("st_identify_parts", "Identify parts of objects", "goal_lang_comm",
        DIP_COMMUNICATION, "expressive", None,
        "Identifying parts of objects. [Open: component-naming vs body-parts/spatial - confirm with speech pathologist.]",
        "Identifies objects and their parts using commonly-used words, and knows body parts, top/bottom, and shapes. The "
        "usual barrier is the articulation difficulty of the word (length and sounds), not knowledge of the object. "
        "[Interpretation spans both component-naming and general object/part identification - plan intent unconfirmed without "
        "speech input, but knowledge appears sound regardless.]"),
    _st("st_3step_commands", "Following 3-step commands", "goal_lang_comm",
        DIP_COMMUNICATION, "interpreting", None,
        "Following 3-step commands, including new/unfamiliar ones.",
        "Follows 3-step commands for familiar, routine activities; struggles with new or unfamiliar commands."),
    _st("st_recall_events", "Recalling recent events", "goal_lang_comm",
        DIP_COMMUNICATION, "conversation", None,
        "Recalling/recounting recent events with minimal prompting.",
        "Strong recall for topics of interest; replays his day in play and drawings to process it. If asked about his day, "
        "often needs specific prompts to start, but is starting to give more detail once a discussion of that type is underway."),
    _st("st_speech_clarity", "Speech clarity / intelligibility", "goal_lang_comm",
        DIP_COMMUNICATION, "speaking", None,
        "Speech clarity / intelligibility, especially for unfamiliar listeners.",
        "Intelligibility, pronunciation and expressive clarity remain difficult for unfamiliar listeners; supplements with "
        "gestures, alternative words, visual supports. Improved after grommets (May 2022)."),
    _st("st_pronouns", "Pronoun use - me / mine", "goal_lang_comm",
        DIP_COMMUNICATION, "expressive", None,
        "Using 'mine' and 'me' to refer to himself most of the time.",
        "Uses \"my\" (e.g. \"my book\") and responds \"me\" to \"who did...?\" questions. Also refers to himself as \"Tom\" / \"Tom's\"."),

    # --- Play Skills (4) ---
    _st("st_tolerate_others", "Tolerating others in his space", "goal_play",
        DIP_INTERPERSONAL, "regulating", SSG_IND,
        "Tolerating others playing in his immediate space without moving away.",
        "Tolerates others in his space when an adult is close by; if the adult is further away he moves away. Tolerance "
        "depends on the play being calm, aligned with his interests, and with familiar people. Otherwise he moves away or "
        "shuts down, and may become angry and stop playing (including big feelings)."),
    _st("st_env_safety_scanning", "Environment safety scanning", "goal_play",
        DIP_SELF_CARE, "safety", None,
        "Notices what is around him - peripheral awareness of people/objects/movement while absorbed in play/activity.",
        "Needs active prompting; very unaware of surroundings beyond his immediate focus."),
    _st("st_reciprocal_play", "Reciprocal / turn-taking play", "goal_play",
        DIP_INTERPERSONAL, "forming relationships", SSG_IND,
        "Reciprocal/cooperative play with peers - turn-taking, shared aims, responding to others' ideas.",
        "Predominantly parallel play; rarely initiates peer interaction independently; engagement scaffolded by adult "
        "presence. Shared play with sister is structured/scripted. Beginning supported peer play (Story Champs, classroom)."),
    _st("st_sensory_play", "Sensory play", "goal_play",
        None, None, None,
        "Comfort engaging in new sensory styles of play (playdough, paints).",
        "Will finger-paint with sauce on his dinner plate and mush food like playdough, but very quickly asks for his hands "
        "to be cleaned. Enjoys some tactile materials (cotton wool, wool); sensory-seeking but also sensory-averse."),

    # --- Feelings & Emotions (3, carved from one "Manage big behaviours" line) ---
    _st("st_self_regulation", "Self-regulation & coping", "goal_feelings",
        DIP_GENERAL_TASKS, None, SSG_ER,
        "Recognising his own rising arousal/distress and using a coping strategy (escalation, meltdown, self-calming).",
        "Recognising his own rising distress and using a strategy; adult support for most regulation. Emerging: asks for a "
        "walk when dysregulating; rewarded for noticing a break is needed before escalating. Works: walk/reset, short "
        "enforced breaks, scripts/interests. Failure presentation: kicking, hitting, throwing, head-hitting "
        "(self-injurious - safety note)."),
    _st("st_change_tolerance", "Change & transition tolerance", "goal_feelings",
        DIP_GENERAL_TASKS, None, SSG_ER,
        "Coping with unexpected change and transitions (toward and away from preferred activities).",
        "Coping with unexpected change/transitions (toward and away from preferred activities). Supports: visual schedules, "
        "advance warning, red change card (success - places it at the change point), social stories. Emerging: accepts some "
        "changes once fixed/familiar (classroom TV). Struggles when class runs a different schedule to him."),
    _st("st_social_emotional", "Social-emotional understanding", "goal_feelings",
        DIP_INTERPERSONAL, None, None,
        "Understanding emotions in himself and others - naming emotions, reading cues, separating emotional from physical states.",
        "Responds to overt distress in others but absorbs intensity rather than understanding it; misses subtler cues. "
        "Emotional literacy (naming emotions, separating emotional states from physical sensations) an early FSSP focus."),

    # --- Gross Motor (4) ---
    _st("st_walk_terrain", "Walking - terrain & steps", "goal_gross_motor",
        DIP_MOBILITY, "moving", SSG_IND,
        "Walking confidently across different terrains and steps without support.",
        "Walks independently indoors in familiar, calm places (home, grandparents', his classroom when calm). Outdoors, "
        "walks independently only on even flat ground (path, compacted gravel, grass); holds an adult elsewhere, likely more "
        "from anxiety than physical limitation. Always uses a handrail or adult hand for steps, up and down. Manages access "
        "ramps independently. Steep hills or uneven ground require adult support."),
    _st("st_stamina_range", "Stamina & range - physical exertion", "goal_gross_motor",
        DIP_MOBILITY, "moving", None,
        "Physical exertion capacity - distance, active duration, recovery.",
        "Can walk up to ~2km slowly at his own pace with breaks, but is exhausted afterward and unable to do further "
        "activity. Playground play tolerated ~30-45 min (up to 1hr max). Balance bike/trike used for longer distances but "
        "total duration is similar. No stroller currently available; longer activities not possible without a significant break."),
    _st("st_catch_throw", "Catching & throwing", "goal_gross_motor",
        DIP_MOBILITY, "lifting/carrying", None,
        "Ball skills - catching and throwing with increasing accuracy toward a target.",
        "Can sometimes catch a large spiky ball at very close range (~1m). Throws small balls effectively several metres "
        "toward a broad target area, though not accurately."),
    _st("st_community_participation", "Community participation", "goal_gross_motor",
        DIP_MOBILITY, None, None,
        "Participation in community activities (constrained by stamina/mobility).",
        "Participates with adult support, constrained by stamina."),

    # --- School Environment (2, carved) ---
    _st("st_fatigue_tolerance", "Sustained participation / fatigue tolerance - school", "goal_school",
        DIP_GENERAL_TASKS, None, SSG_PART,
        "Sustained participation across the day/week - engagement endurance, across-week decline, non-physical-task fatigue.",
        "Attends 5 full days at South Geelong PS with Education Support staff, but requires regular breaks throughout the day. "
        "The number of breaks typically increases over the week, with Friday being less effective for learning than "
        "Monday/Tuesday. Hypotonia and low stamina contribute to fatigue across the day and during tasks (including meals)."),
    _st("st_danger_new_env", "Danger awareness - new / unfamiliar environments", "goal_school",
        DIP_SELF_CARE, "safety", None,
        "Coping with the unfamiliar - navigating/interpreting unfamiliar or busy settings (excursions, new rooms, transitions).",
        "Lacks confidence in busy/unfamiliar settings, especially mobility; does not notice hazards (roads, hot, sharp) and "
        "often ignores prompts, sometimes needing to be physically stopped; atypical interoception compounds this. Needs "
        "adult support to interpret surroundings and transitions. Uses visual schedules and \"red change card.\""),

    # --- Other (4: 3 Adjacent-watch + Sleep Active) ---
    _st("st_fine_motor", "Fine motor skills", "goal_other",
        DIP_MOBILITY, "fine motor skills", None,
        "Fine hand use - manipulation, grasp, tool use, pre-writing. Former NDIS goal; tracked informally. "
        "[Gap-blank: current level to be filled before the 1d data load.]",
        None, ndis=0, status="Adjacent-watch"),
    _st("st_cognition_learning", "Cognition / Learning", "goal_other",
        DIP_LEARNING, None, None,
        "Attention, processing speed, visual-spatial profile, and emerging academics. Deliberately broad - expected to split "
        "(attention/processing vs academics) once data accrues.",
        None, ndis=0, status="Adjacent-watch"),
    _st("st_routines_independence", "Routines & Task Independence", "goal_other",
        DIP_GENERAL_TASKS, None, SSG_IND,
        "Executive/routine/transition dimension - initiating, sequencing, and completing routine tasks independently "
        "(significant for an ASD profile).",
        None, ndis=0, status="Adjacent-watch"),
    _st("st_sleep_onset", "Sleep - independent onset", "goal_other",
        None, None, None,
        "Independent sleep onset - settling and falling asleep without adult presence. OT working active strategies. "
        "[Benchmark pending: seed before the 1d data load.]",
        None, ndis=0, status="Active"),

    # --- Medical (5) ---
    _st("st_dysphagia_airway", "Dysphagia / airway", "goal_medical",
        DIP_SELF_CARE, "health", None,
        "Swallowing safety and airway protection - choking risk, modified diet, aspiration. Read on a status axis. "
        "[Benchmark pending: seed before the 1d data load.]",
        None, ndis=0, status="Active", severity="Safety-critical"),
    _st("st_continence_medical", "Continence (medical)", "goal_medical",
        DIP_SELF_CARE, "toileting", None,
        "Medical/physiological continence (bladder & bowel) - the medical dimension under continence physio, distinct from "
        "the Self-Care toileting skill. [Gap-blank: fill before the 1d data load.]",
        None, ndis=0, status="Active", severity="None"),
    _st("st_gastro", "Gastrointestinal (gastro)", "goal_medical",
        None, None, None,
        "Gastrointestinal health - feeding, reflux, bowel function, nutrition intake. [Gap-blank: fill before the 1d data load.]",
        None, ndis=0, status="Active", severity="None"),
    _st("st_dental", "Dental", "goal_medical",
        None, None, None,
        "Dental and oral health - hygiene, decay risk, dental reviews. [Gap-blank: fill before the 1d data load.]",
        None, ndis=0, status="Active", severity="None"),
    _st("st_growth", "Growth", "goal_medical",
        None, None, None,
        "Growth and nutrition - weight, height, growth trajectory. [Gap-blank: fill before the 1d data load.]",
        None, ndis=0, status="Active", severity="None"),

    # --- Holding pens (2) ---
    _st("st_pen_unclassified", "Other / Unclassified", "goal_other",
        None, None, None,
        "Holding pen (last resort). Real findings matching no seeded sub-target land here with their verbatim anchor; "
        "reviewed to be emptied (promote a cluster, or confirm incidental).",
        None, ndis=0, status="Active"),
    _st("st_pen_medical_watch", "Other medical / watch", "goal_medical",
        None, None, None,
        "Medical holding pen for one-off/infrequent medical findings not in a seeded watch domain (ENT, ortho, one-offs). "
        "Pen findings run a capture-time severity screen ('screened, not silent'); drains at the paediatrician 6-monthly.",
        None, ndis=0, status="Active", severity="None"),
]


# ---------------------------------------------------------------------------
# Providers (migrated from the legacy Notion Providers DB, 13/06/2026)
# aliases: comma-separated (matcher reads this). known_sender_emails /
# known_sender_domains: Python lists -> JSON-encoded by the seeder.
# ---------------------------------------------------------------------------

_CTS = "Children's Therapy Services, 165 Myers St Geelong VIC 3220"
_SPLOSE_EMAIL = ["notifications@splose.com"]
_SPLOSE_DOMAIN = ["email.splose.com"]

PROVIDERS = [
    {"id": "prov_anna_harris", "title": "Dr Anna Harris", "type": "GP",
     "aliases": "Anna Harris, Dr Harris", "ndis_funded": 0,
     "primary_email": "", "known_sender_emails": [], "known_sender_domains": [],
     "typical_report_format": "", "notes": ""},
    {"id": "prov_brooke_doherty", "title": "Dr Brooke Doherty", "type": "Paed",
     "aliases": "Brooke Doherty, Dr Doherty", "ndis_funded": 0,
     "primary_email": "drbrookedoherty@gmail.com",
     "known_sender_emails": ["reception@g-pg.com.au"], "known_sender_domains": [],
     "typical_report_format": "", "notes": "Paediatrician."},
    {"id": "prov_heidi_hearps", "title": "Heidi Hearps", "type": "Speech",
     "aliases": "Heidi", "ndis_funded": 1,
     "primary_email": "heidi.hearps@childrenstherapyservices.com.au",
     "known_sender_emails": _SPLOSE_EMAIL, "known_sender_domains": _SPLOSE_DOMAIN,
     "typical_report_format": "PDF",
     "notes": "Developmental Educator + Speech Therapist. Type select has no Dev Educator option; set to Speech. " + _CTS},
    {"id": "prov_madelaine_tomlin", "title": "Madelaine Tomlin", "type": "OT",
     "aliases": "Maddy, Maddy Tomlin, M. Tomlin", "ndis_funded": 1,
     "primary_email": "maddy.tomlin@childrenstherapyservices.com.au",
     "known_sender_emails": _SPLOSE_EMAIL, "known_sender_domains": _SPLOSE_DOMAIN,
     "typical_report_format": "PDF", "notes": _CTS},
    {"id": "prov_kerry_britt", "title": "Kerry Britt", "type": "Physio",
     "aliases": "Kerry", "ndis_funded": 1,
     "primary_email": "Kerry.britt@childrenstherapyservices.com.au",
     "known_sender_emails": _SPLOSE_EMAIL, "known_sender_domains": _SPLOSE_DOMAIN,
     "typical_report_format": "PDF", "notes": _CTS},
    {"id": "prov_sarah_henderson", "title": "Sarah Henderson", "type": "Continence",
     "aliases": "Sarah", "ndis_funded": 1,
     "primary_email": "admin@barwonkids.au",
     "known_sender_emails": _SPLOSE_EMAIL, "known_sender_domains": [],
     "typical_report_format": "PDF", "notes": "Continence physiotherapist. Barwon Kids."},
    {"id": "prov_sally_barnard", "title": "Sally Barnard", "type": "Psychology",
     "aliases": "Sally", "ndis_funded": 1,
     "primary_email": "sally.barnard@childrenstherapyservices.com.au",
     "known_sender_emails": _SPLOSE_EMAIL, "known_sender_domains": _SPLOSE_DOMAIN,
     "typical_report_format": "PDF", "notes": _CTS},
    {"id": "prov_alex_trezise", "title": "Alex Trezise", "type": "Psychology",
     "aliases": "Alex", "ndis_funded": 1,
     "primary_email": "alex.trezise@childrenstherapyservices.com.au",
     "known_sender_emails": _SPLOSE_EMAIL, "known_sender_domains": _SPLOSE_DOMAIN,
     "typical_report_format": "PDF", "notes": _CTS},
    {"id": "prov_jennie_absalom", "title": "Jennie Absalom", "type": "Speech",
     "aliases": "Jennie, Jenny Absalom, Jen", "ndis_funded": 1,
     "primary_email": "jen.absalom@childrenstherapyservices.com.au",
     "known_sender_emails": _SPLOSE_EMAIL, "known_sender_domains": _SPLOSE_DOMAIN,
     "typical_report_format": "PDF", "notes": "Speech pathologist - assessment-only. " + _CTS},
    {"id": "prov_amanda_tribe", "title": "Amanda Tribe", "type": "OT",
     "aliases": "Amanda, A. Tribe", "ndis_funded": 1,
     "primary_email": "amanda.tribe@childrenstherapyservices.com.au",
     "known_sender_emails": _SPLOSE_EMAIL, "known_sender_domains": _SPLOSE_DOMAIN,
     "typical_report_format": "PDF", "notes": _CTS},
    {"id": "prov_hannah_chapman", "title": "Hannah Chapman", "type": "Speech",
     "aliases": "Hannah", "ndis_funded": 1,
     "primary_email": "",
     "known_sender_emails": _SPLOSE_EMAIL, "known_sender_domains": _SPLOSE_DOMAIN,
     "typical_report_format": "PDF", "notes": _CTS + " Story Champs sessions."},
]
