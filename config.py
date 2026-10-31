"""Settings, read once from .env. Every other file imports from here."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Emoji and Taglish print fine in any Windows terminal.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

MODEL = os.getenv("REVIEWER_MODEL", "claude-sonnet-5-5")

NOTES_DIR = ROOT / "notes"
SUBJECTS = ["bio", "econ", "ph-history"]  # one folder each in notes/
QUIZ_LOG = ROOT / "quiz_log.csv"

# Lumen AI Chat rejects messages over 4,000 characters. We refuse them before
# any API call, on both backends, so a long paste never costs anything.
MAX_QUESTION = 4000

# Which brain answers Ask mode: "claude" (default) or "lumen" (the host's demo).
NOTES_BACKEND = os.getenv("NOTES_BACKEND", "claude").strip().lower()

# Lumen AI Chat (host only). One instance per subject, set up in the Organization Portal.
LUMEN_BASE_URL = os.getenv("LUMEN_BASE_URL", "https://api.staging.nonlive.lumen.bayanichain.tech")
LUMEN_INSTANCES = {
    "bio": os.getenv("LUMEN_INSTANCE_BIO", ""),
    "econ": os.getenv("LUMEN_INSTANCE_ECON", ""),
    "ph-history": os.getenv("LUMEN_INSTANCE_PH_HISTORY", ""),
}


def subject_dir(subject: str) -> Path:
    if subject not in SUBJECTS:
        raise SystemExit(f"Unknown subject {subject!r}. Pick one of: {', '.join(SUBJECTS)}")
    return NOTES_DIR / subject
