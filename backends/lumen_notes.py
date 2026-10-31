"""Ask mode on Lumen AI Chat: same ask(), different brain (the host's demo).

Lumen AI Chat is a hosted assistant API. An organization admin sets up an
"instance" in the Lumen Organization Portal (its model, its rules, its
sources). We open a session on that instance, send each question as a
message, and Lumen answers, cites its sources and keeps the transcript.

    GET  /ai_chat/instances                                  1 credit
    POST /ai_chat/instances/{id}/sessions                    2 credits
    POST /ai_chat/instances/{id}/sessions/{sid}/messages     5 credits  (the model runs here)
    GET  /ai_chat/instances/{id}/sessions/{sid}/messages     1 credit   (the transcript)

Credits are charged only on a 2xx. Every call needs two headers:
lumen-api-key and lumen-api-secret. Keep them in .env; never in a slide or a chat.
"""
from __future__ import annotations

import os
import time
from datetime import date

import httpx

from config import LUMEN_BASE_URL, LUMEN_INSTANCES, MAX_QUESTION

from .base import NotesAnswer, ReviewerError, Source

# The session is gone or unusable: open a new one and send again, once.
SESSION_LOST = {"SESSION_NOT_OWNED", "SESSION_NOT_FOR_INSTANCE", "AI_CHAT_SESSION_NOT_FOUND", "AI_CHAT_CONFLICT"}
# Not charged and usually brief: pause, then send again, once.
TRY_AGAIN = {429, 502, 503, 504}

FIXES = {
    "API_KEY_NOT_FOUND": "the Lumen API key is wrong. Check LUMEN_API_KEY in .env.",
    "API_SECRET_NOT_FOUND": "the Lumen API secret is wrong. Check LUMEN_API_SECRET in .env.",
    "INVALID_API_CREDENTIALS": "the Lumen key and secret don't match. Copy both again.",
    "ACCESS_DENIED": "this key has no AI Chat grant. Add it in the Organization Portal (Settings > API Keys).",
    "VIEW_ONLY_ACCESS": "this key's AI Chat grant is read-only. It needs write access to send messages.",
    "API_CREDITS_INSUFFICIENT": "out of API credits. Top up the organization's API credits.",
    "LC_INSUFFICIENT": "out of Lumen Credits (the message route needs a positive balance).",
    "ORG_SUBSCRIPTION_INACTIVE": "the organization's subscription is inactive.",
    "FEATURE_DISABLED": "AI Chat is switched off on this gateway. Use the staging URL, not live.",
    "AI_CHAT_NOT_CONFIGURED": "AI Chat has no model settings on this environment yet.",
    "AI_CHAT_REPLY_TIMEOUT": "Lumen took over 25 s to answer (not charged). Try a shorter question.",
}


def _code(r: httpx.Response) -> str:
    try:
        return str(r.json().get("error", {}).get("code", ""))
    except ValueError:
        return ""


def _fail(r: httpx.Response) -> ReviewerError:
    code = _code(r)
    fix = FIXES.get(code, "see the error code in the Lumen docs.")
    return ReviewerError(f"Lumen said {r.status_code} {code or ''}: {fix}".replace("  ", " "))


def _headers() -> dict:
    key, secret = os.getenv("LUMEN_API_KEY", ""), os.getenv("LUMEN_API_SECRET", "")
    if not key or not secret:
        raise ReviewerError("NOTES_BACKEND=lumen needs LUMEN_API_KEY and LUMEN_API_SECRET in .env.")
    return {"lumen-api-key": key, "lumen-api-secret": secret}


def _base() -> str:
    return LUMEN_BASE_URL.rstrip("/") + "/ai_chat"


def list_instances(http: httpx.Client | None = None) -> list[dict]:
    """The AI Chat instances this key may use (1 credit). Copy an InstanceID into .env."""
    http = http or httpx.Client(timeout=35)
    r = http.get(f"{_base()}/instances", headers=_headers())
    if r.status_code != 200:
        raise _fail(r)
    return r.json().get("Instances") or []


class LumenNotes:
    """One subject's questions, answered by that subject's Lumen AI Chat instance."""

    def __init__(self, subject: str, http: httpx.Client | None = None, pause: float = 3.0):
        self.instance = LUMEN_INSTANCES.get(subject, "")
        if not self.instance:
            env = "LUMEN_INSTANCE_" + subject.upper().replace("-", "_")
            raise ReviewerError(f"Set {env} in .env. List your instances with: python reviewer.py instances")
        self.headers = _headers()
        self.base = _base()
        self.title = f"Reviewer Agent - {subject} - {date.today()}"[:200]
        self.http = http or httpx.Client(timeout=35)  # Lumen gives up at 25 s; we wait a little longer
        self.pause = pause
        self.session_id: str | None = None  # opened on the first question, so setup costs nothing

    def _open(self) -> str:
        r = self.http.post(f"{self.base}/instances/{self.instance}/sessions",
                           headers=self.headers, json={"title": self.title})
        if r.status_code != 201:
            raise _fail(r)
        return r.json()["Session"]["id"]

    def _send(self, question: str) -> httpx.Response:
        if self.session_id is None:
            self.session_id = self._open()
        url = f"{self.base}/instances/{self.instance}/sessions/{self.session_id}/messages"
        return self.http.post(url, headers=self.headers, json={"message": question})

    def ask(self, question: str) -> NotesAnswer:
        if len(question) > MAX_QUESTION:  # Lumen would answer 400; refuse before paying for anything
            return NotesAnswer(text=f"Question too long. Keep it under {MAX_QUESTION:,} characters.")
        r = self._send(question)
        if _code(r) in SESSION_LOST:            # session lost: open a new one, once
            self.session_id = None
            r = self._send(question)
        elif r.status_code in TRY_AGAIN:        # not charged: pause, then try once more
            time.sleep(self.pause)
            r = self._send(question)
        if r.status_code != 200:
            raise _fail(r)
        a = r.json()["Answer"]
        return NotesAnswer(text=a.get("answer") or "",
                           sources=[Source(title=c) for c in a.get("citations") or []],
                           degraded=a.get("degradedSources") or [])

    def transcript(self, limit: int = 50) -> list[dict]:
        """What Lumen stored for this session, oldest first (1 credit)."""
        if self.session_id is None:
            return []
        r = self.http.get(f"{self.base}/instances/{self.instance}/sessions/{self.session_id}/messages",
                          headers=self.headers, params={"limit": limit})
        if r.status_code != 200:
            raise _fail(r)
        return r.json().get("Messages") or []
