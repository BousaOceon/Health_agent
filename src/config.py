"""Loads settings.yaml and .env; provides a single config object for all modules."""
import os
import yaml
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

_settings_path = Path(__file__).parent.parent / "config" / "settings.yaml"

with open(_settings_path) as f:
    settings = yaml.safe_load(f)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
GMAIL_PRIMARY_CREDENTIALS = os.getenv("GMAIL_PRIMARY_CREDENTIALS")
GMAIL_SECONDARY_CREDENTIALS = os.getenv("GMAIL_SECONDARY_CREDENTIALS")
GMAIL_PRIMARY_ADDRESS = os.getenv("GMAIL_PRIMARY_ADDRESS")
GMAIL_SECONDARY_ADDRESS = os.getenv("GMAIL_SECONDARY_ADDRESS")
OUTBOUND_EMAIL_PRIMARY = os.getenv("OUTBOUND_EMAIL_PRIMARY")
OUTBOUND_EMAIL_SECONDARY = os.getenv("OUTBOUND_EMAIL_SECONDARY")

NOTION = settings["notion"]
FEATURES = settings["features"]
