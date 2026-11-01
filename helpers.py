"""Small helpers you can read but don't need to change.

    NotesAnswer, Source    the answer shape: text, sources, offline sources
    ReviewerError          a problem you can fix; the CLI prints it plainly
    expect(r, status)      stop with a clear message when Lumen says no
    extract_json(text)     pull the {...} out of a reply that has extra words
    load_step(name)        import 01_ask.py or 02_quiz.py by name
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx


@dataclass
class Source:
    title: str                 # Lumen's citation string, e.g. the note's name


@dataclass
class NotesAnswer:
    text: str
    sources: list[Source] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)   # sources that were offline for this turn


class ReviewerError(Exception):
    """A problem you can fix (a bad key, no credits, a missing setting)."""


class LumenError(ReviewerError):
    """Lumen answered with an error. status is the HTTP code, code is Lumen's error code."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


# What each Lumen error code means for you, in one sentence.
FIXES = {
    "API_KEY_NOT_FOUND": "the Lumen API key is wrong. Check LUMEN_API_KEY in .env.",
    "API_SECRET_NOT_FOUND": "the Lumen API secret is wrong. Check LUMEN_API_SECRET in .env.",
    "INVALID_API_CREDENTIALS": "the Lumen key and secret don't match. Copy both again.",
    "ACCESS_DENIED": "this key has no AI Chat grant. Ask the host to add it.",
    "VIEW_ONLY_ACCESS": "this key's AI Chat grant is read-only. It needs write access to send messages.",
    "API_CREDITS_INSUFFICIENT": "this key is out of API credits. Ask the host for more.",
    "LC_INSUFFICIENT": "the organization is out of Lumen Credits. Tell the host.",
    "ORG_SUBSCRIPTION_INACTIVE": "the organization's subscription is inactive. Tell the host.",
    "SESSION_NOT_OWNED": "that session belongs to another key.",
    "SESSION_NOT_FOR_INSTANCE": "that session belongs to another instance.",
    "AI_CHAT_SESSION_NOT_FOUND": "that session doesn't exist.",
    "AI_CHAT_CONFLICT": "that session is archived.",
    "AI_CHAT_QUERY_TOO_LONG": "the question is too long. Keep it under 4,000 characters.",
    "VALIDATION_ERROR": "Lumen rejected the request body. Check the JSON you sent.",
    "FEATURE_DISABLED": "AI Chat is switched off on this gateway. Use the staging LUMEN_BASE_URL from .env.example.",
    "AI_CHAT_NOT_CONFIGURED": "AI Chat has no model settings on this environment yet. Tell the host.",
    "AI_CHAT_REPLY_TIMEOUT": "Lumen took over 25 seconds to answer (not charged). Try a shorter question.",
    "AI_CHAT_MODEL_RATE_LIMITED": "Lumen's model is busy (not charged). Wait a moment and try again.",
    "RATE_LIMIT_EXCEEDED": "too many requests at once (not charged). Wait a moment and try again.",
}


def expect(r: httpx.Response, status: int) -> dict:
    """Return the JSON body when Lumen answered with `status`; otherwise raise a clear LumenError.

    Every Lumen error body looks like {"error": {"code": "...", "message": "..."}}.
    """
    if r.status_code == status:
        return r.json()
    try:
        code = str(r.json().get("error", {}).get("code", ""))
    except ValueError:
        code = ""
    if r.status_code == 404 and not code:
        fix = "that instance doesn't exist. Check the instance ID in .env."
    else:
        fix = FIXES.get(code, "see the error code in the Lumen AI Chat docs.")
    raise LumenError(r.status_code, code, f"Lumen said {r.status_code}{' ' + code if code else ''}: {fix}")


def extract_json(text: str) -> str:
    """The {...} part of a reply. Models sometimes add a sentence or ```json fences around it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("the reply has no JSON object in it")
    return text[start:end + 1]


def load_step(name: str):
    """Import a workshop file such as 01_ask.py.

    `import 01_ask` is a syntax error (names can't start with a digit), so we
    import it by name. If you ran that file directly, reuse the running copy.
    """
    main = sys.modules.get("__main__")
    if main is not None and Path(getattr(main, "__file__", "") or "").stem == name:
        return main
    return importlib.import_module(name)
