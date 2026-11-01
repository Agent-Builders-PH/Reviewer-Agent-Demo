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

NOTES_DIR = ROOT / "notes"           # your notes, one folder per subject; sent with each question
SUBJECTS = ["bio", "econ", "ph-history"]
QUIZ_LOG = ROOT / "quiz_log.csv"

# A Lumen AI Chat message is at most 2,000 characters, and your notes travel in
# the same message as the question. So questions are capped at 500 characters,
# and refused before any API call: a long paste never costs anything.
MAX_QUESTION = 500

# Lumen AI Chat. The host sends you the key, the secret and one instance ID per subject.
LUMEN_BASE_URL = os.getenv("LUMEN_BASE_URL", "https://api.staging.nonlive.lumen.bayanichain.tech").rstrip("/")
LUMEN_API_KEY = os.getenv("LUMEN_API_KEY", "")
LUMEN_API_SECRET = os.getenv("LUMEN_API_SECRET", "")
LUMEN_INSTANCES = {
    "bio": os.getenv("LUMEN_INSTANCE_BIO", ""),
    "econ": os.getenv("LUMEN_INSTANCE_ECON", ""),
    "ph-history": os.getenv("LUMEN_INSTANCE_PH_HISTORY", ""),
}
AI_CHAT = LUMEN_BASE_URL + "/ai_chat"   # every route starts here


def subject_dir(subject: str) -> Path:
    if subject not in SUBJECTS:
        raise SystemExit(f"Unknown subject {subject!r}. Pick one of: {', '.join(SUBJECTS)}")
    return NOTES_DIR / subject


def instance_for(subject: str) -> str:
    from helpers import ReviewerError
    subject_dir(subject)
    instance = LUMEN_INSTANCES.get(subject, "")
    if not instance:
        env = "LUMEN_INSTANCE_" + subject.upper().replace("-", "_")
        raise ReviewerError(f"Set {env} in .env. The host sends you the instance IDs.")
    return instance
