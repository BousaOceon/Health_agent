"""All Notion API read/write operations."""
import json
import logging
import re
from datetime import date
from notion_client import Client
from src.config import NOTION_API_KEY, NOTION, settings

log = logging.getLogger(__name__)
notion = Client(auth=NOTION_API_KEY)

_RICH_TEXT_LIMIT = 1990  # Notion property limit per block


def _rt(text: str) -> list:
    """Build a rich_text array, truncating to Notion's limit."""
    if not text:
        return []
    return [{"text": {"content": str(text)[:_RICH_TEXT_LIMIT]}}]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def fetch_ndis_goals() -> dict:
    """Returns {goal_name: page_id} for all records in the NDIS Goals database."""
    results = notion.databases.query(database_id=NOTION["ndis_goals_db"])["results"]
    goals = {}
    for r in results:
        title_prop = r["properties"].get("Title", {}).get("title", [])
        if title_prop:
            name = title_prop[0]["plain_text"]
            goals[name] = r["id"]
    log.info("Loaded %d NDIS goals", len(goals))
    return goals


def fetch_goals_with_benchmarks_text(goals_map: dict) -> str:
    """Build the ###GOALS_WITH_BENCHMARKS### injection text.

    For each goal: Current Benchmark rich_text from Notion + valid sub_target
    options from settings.ndis_sub_targets, so the model sees both next to
    each other and can emit verbatim sub_target strings.
    """
    sub_targets_cfg = settings.get("ndis_sub_targets", {})
    parts = []
    for goal_name, page_id in goals_map.items():
        benchmark_text = ""
        try:
            page = notion.pages.retrieve(page_id=page_id)
            rt = page["properties"].get("Current Benchmark", {}).get("rich_text", [])
            benchmark_text = "".join(block["plain_text"] for block in rt)
        except Exception as e:
            log.warning("Could not fetch benchmark for goal %r: %s", goal_name, e)

        goal_sub_targets = sub_targets_cfg.get(goal_name, [])
        options_line = " | ".join(goal_sub_targets) if goal_sub_targets else "(no sub-targets defined)"

        parts.append(
            f"=== {goal_name} ===\n"
            f"{benchmark_text or '(benchmark not yet set)'}\n\n"
            f"Valid sub_target options (emit one verbatim): {options_line}"
        )
    return "\n\n".join(parts)


def fetch_provider_list_text() -> str:
    """Build the ###PROVIDER_LIST### injection text (canonical name | aliases | type)."""
    results = notion.databases.query(database_id=NOTION["providers_db"])["results"]
    lines = []
    for r in results:
        title_prop = r["properties"].get("Title", {}).get("title", [])
        name = title_prop[0]["plain_text"] if title_prop else ""
        if not name:
            continue
        aliases = [a["name"] for a in r["properties"].get("Aliases", {}).get("multi_select", [])]
        type_prop = r["properties"].get("Type", {}).get("select")
        provider_type = type_prop["name"] if type_prop else ""

        parts = [name]
        if aliases:
            parts.append(f"Aliases: {', '.join(aliases)}")
        if provider_type:
            parts.append(f"Type: {provider_type}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _goal_id(goals_map: dict, name: str) -> str | None:
    """Return page ID for a goal name, or None if not found."""
    if not name or not goals_map:
        return None
    match = goals_map.get(name)
    if not match:
        log.warning("Goal not found in goals map: %r", name)
    return match


def _normalize_name(name: str) -> str:
    """Strip honorifics and lowercase for matching."""
    name = name.strip()
    for prefix in ("Dr. ", "Dr ", "Mr. ", "Mr ", "Ms. ", "Ms ",
                   "Mrs. ", "Mrs ", "Prof. ", "Prof "):
        if name.lower().startswith(prefix.lower()):
            name = name[len(prefix):]
            break
    return name.strip().lower()


def _looks_like_combined(name: str) -> bool:
    """True if name appears to be a combined string of multiple people."""
    return bool(re.search(r',|\band\b|&', name, re.IGNORECASE))


def find_or_create_provider(name: str) -> str | None:
    """Return page ID of provider matching name, or create a stub.

    Matching order: (1) exact normalised title, (2) substring on title,
    (3) any alias. Combined-name strings are refused — the extraction prompt
    is the primary defence; notion_writer is the backstop.
    """
    if not name or not name.strip():
        return None

    if _looks_like_combined(name):
        log.warning(
            "find_or_create_provider got combined name %r — split before calling. Skipping.", name
        )
        return None

    name_norm = _normalize_name(name)
    all_providers = notion.databases.query(database_id=NOTION["providers_db"])["results"]

    for record in all_providers:
        title_prop = record["properties"].get("Title", {}).get("title", [])
        title = title_prop[0]["plain_text"] if title_prop else ""
        title_norm = _normalize_name(title)

        if title_norm == name_norm:
            return record["id"]
        if name_norm in title_norm or title_norm in name_norm:
            return record["id"]

        for alias_obj in record["properties"].get("Aliases", {}).get("multi_select", []):
            if _normalize_name(alias_obj.get("name", "")) == name_norm:
                return record["id"]

    page = notion.pages.create(
        parent={"database_id": NOTION["providers_db"]},
        properties={"Title": {"title": [{"text": {"content": name}}]}},
    )
    log.warning("Created provider stub (no match): %r — complete Type/Aliases in Notion", name)
    return page["id"]


def appointment_exists(appointment_date: str, gmail_link: str = "") -> bool:
    """Deduplicate on Gmail link first, then fall back to appointment date."""
    if gmail_link:
        results = notion.databases.query(
            database_id=NOTION["appointments_db"],
            filter={"property": "Gmail Link", "url": {"equals": gmail_link}},
        )["results"]
        if results:
            return True
    results = notion.databases.query(
        database_id=NOTION["appointments_db"],
        filter={"property": "Appointement Date", "date": {"equals": appointment_date}},
    )["results"]
    return bool(results)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def create_appointment(extracted: dict, goals_map: dict, gmail_link: str = "") -> str:
    """Create Appointment record. Returns page ID."""
    appt = extracted["appointment"]

    # Build provider relation from providers[] array (Fix 3: provider_name is title-only;
    # never written as an Appointment field — the multi-relation is the authority).
    provider_names = appt.get("providers") or []
    if not provider_names and appt.get("provider_name"):
        provider_names = [appt["provider_name"]]  # backwards compat for solo-session extractions
    seen_ids: set = set()
    provider_ids = []
    for pname in provider_names:
        pid = find_or_create_provider(pname)
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            provider_ids.append({"id": pid})

    goal_ids = []
    for goal_name in appt.get("goals_addressed", []):
        gid = _goal_id(goals_map, goal_name)
        if gid:
            goal_ids.append({"id": gid})

    properties = {
        "Title":               {"title": _rt(appt.get("title", ""))},
        "Appointement Date":   {"date": {"start": appt["appointment_date"]}},
        "Report Received Date":{"date": {"start": appt.get("report_received_date", date.today().isoformat())}},
        "Status":              {"select": {"name": "Draft"}},
        "Summary":             {"rich_text": _rt(appt.get("summary", ""))},
        "NDIS Relevant":       {"checkbox": bool(appt.get("ndis_relevant", False))},
        "Providers":           {"relation": provider_ids},
        "Goals Addressed":     {"relation": goal_ids},
    }
    if appt.get("appointment_type"):
        properties["Type"] = {"select": {"name": appt["appointment_type"]}}
    if appt.get("meeting_type"):
        properties["Meeting Type"] = {"select": {"name": appt["meeting_type"]}}
    if gmail_link:
        properties["Gmail Link"] = {"url": gmail_link}

    page = notion.pages.create(
        parent={"database_id": NOTION["appointments_db"]},
        properties=properties,
    )
    page_id = page["id"]
    log.info("Created appointment: %s", page_id)

    if extracted.get("self_review"):
        try:
            notion.pages.update(
                page_id=page_id,
                properties={"Flags": {"rich_text": _rt(json.dumps(extracted["self_review"]))}},
            )
        except Exception as e:
            log.warning("Could not write self_review to Flags (add rich_text Flags property to Appointments DB): %s", e)

    return page_id


def create_health_actions(extracted: dict, appointment_id: str, goals_map: dict) -> list:
    """Create Health Action records linked to appointment. Returns list of page IDs."""
    ids = []
    for action in extracted.get("actions", []):
        provider_id = find_or_create_provider(action.get("provider_name", ""))

        goal_id = _goal_id(goals_map, action.get("goal_link", ""))

        properties = {
            "Title":       {"title": _rt(action["title"])},
            "Notes":       {"rich_text": _rt(action.get("notes", ""))},
            "Category":    {"select": {"name": action.get("category", "Other Allied Health")}},
            "Status":      {"select": {"name": "Open"}},
            "Priority":    {"select": {"name": action.get("priority", "Medium")}},
            "Assigned To": {"select": {"name": action.get("assigned_to", "Family")}},
            "NDIS Relevant": {"checkbox": bool(action.get("ndis_relevant", False))},
            "Opened Date": {"date": {"start": action.get("opened_date", date.today().isoformat())}},
            "Source Appointment": {"relation": [{"id": appointment_id}]},
        }
        if provider_id:
            properties["Provider"] = {"relation": [{"id": provider_id}]}
        if goal_id:
            properties["Goal Link"] = {"relation": [{"id": goal_id}]}
        if action.get("due_date"):
            properties["Due Date"] = {"date": {"start": action["due_date"]}}

        page = notion.pages.create(
            parent={"database_id": NOTION["health_actions_db"]},
            properties=properties,
        )
        ids.append(page["id"])
        log.info("Created action: %s", action["title"])
    return ids


def create_goal_progress_notes(extracted: dict, appointment_id: str, goals_map: dict) -> list:
    """Create Goal Progress Note records. Returns list of page IDs."""
    ids = []
    for note in extracted.get("goal_progress_notes", []):
        goal_id = _goal_id(goals_map, note.get("goal_name", ""))
        if not goal_id:
            log.warning("Skipping goal progress note — goal not found: %r", note.get("goal_name"))
            continue

        provider_id = None
        if note.get("source") == "Appointment Report" and note.get("source_provider_name"):
            provider_id = find_or_create_provider(note["source_provider_name"])

        properties = {
            "Title":          {"title": _rt(note.get("title", ""))},
            "Note":           {"rich_text": _rt(note.get("note", ""))},
            "Source":         {"select": {"name": note.get("source", "Appointment Report")}},
            "Author":         {"select": {"name": note.get("author", "Provider")}},
            "Type":           {"select": {"name": note.get("type", "Observation")}},
            "NDIS Reportable":{"checkbox": bool(note.get("ndis_reportable", False))},
            "Date":           {"date": {"start": note.get("date", date.today().isoformat())}},
            "Goal":           {"relation": [{"id": goal_id}]},
            "Source Appointment": {"relation": [{"id": appointment_id}]},
        }
        if note.get("sub_target"):
            properties["Sub-target"] = {"select": {"name": note["sub_target"]}}
        if provider_id:
            properties["Source Provider"] = {"relation": [{"id": provider_id}]}

        page = notion.pages.create(
            parent={"database_id": NOTION["goal_progress_notes_db"]},
            properties=properties,
        )
        ids.append(page["id"])
        log.info("Created goal progress note: %s", note.get("goal_name"))
    return ids


def append_raw_notes_to_page(page_id: str, raw_content: str):
    """Write full raw content into the page body as paragraph blocks.
    Splits into 2000-char chunks to stay within Notion block limits.
    """
    if not raw_content:
        return
    chunk_size = 2000
    chunks = [raw_content[i:i + chunk_size] for i in range(0, len(raw_content), chunk_size)]
    blocks = [
        {"object": "block", "type": "paragraph",
         "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]}}
        for chunk in chunks
    ]
    # Notion allows max 100 blocks per append call
    for i in range(0, len(blocks), 100):
        notion.blocks.children.append(block_id=page_id, children=blocks[i:i + 100])
    log.info("Appended raw notes to page body (%d chars, %d blocks)", len(raw_content), len(blocks))


# ---------------------------------------------------------------------------
# Connectivity check
# ---------------------------------------------------------------------------

def verify_connectivity() -> bool:
    ok = True
    for key, db_id in NOTION.items():
        if not db_id or "page_id" in key:
            continue
        try:
            notion.databases.retrieve(database_id=db_id)
            print(f"  OK  {key}")
        except Exception as e:
            print(f"  FAIL {key}: {e}")
            ok = False
    return ok


if __name__ == "__main__":
    print("Testing Notion connectivity...")
    verify_connectivity()
    print("\nNDIS Goals:")
    for name, pid in fetch_ndis_goals().items():
        print(f"  {name}")
