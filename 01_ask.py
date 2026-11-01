"""Phase 1: Ask. Questions answered by Lumen AI Chat, only from your notes, with sources.

    python 01_ask.py "Ano ang ATP?"
    python 01_ask.py "Kailan ang Sigaw?" --subject ph-history

Lumen AI Chat is a hosted assistant. The host set up one *instance* per
subject in the Lumen Organization Portal: its model, its rules and its
sources (the files in notes/). You talk to it with four HTTP calls:

    GET  /ai_chat/instances                                   list instances   1 credit
    POST /ai_chat/instances/{id}/sessions                     open a session   2 credits
    POST /ai_chat/instances/{id}/sessions/{sid}/messages      ask a question   5 credits
    GET  /ai_chat/instances/{id}/sessions/{sid}/messages      the transcript   1 credit

You write the calls (TODOs 1 to 3) and the guard (TODO 4): no source, no answer.
"""
from __future__ import annotations

import sys
import time
from datetime import date

import httpx

from config import AI_CHAT, LUMEN_API_KEY, LUMEN_API_SECRET, MAX_QUESTION, instance_for
from helpers import LumenError, NotesAnswer, Source, expect


# ---------------------------------------------------------------- TODO 1
def lumen_headers() -> dict:
    """The two headers every Lumen call needs. Both values come from .env."""
    # TODO 1: return a dict with two headers:
    #   "lumen-api-key"    -> LUMEN_API_KEY
    #   "lumen-api-secret" -> LUMEN_API_SECRET
    raise NotImplementedError("TODO 1: return the two Lumen headers in lumen_headers()")


# ---------------------------------------------------------------- given: list instances
def list_instances(http: httpx.Client) -> list[dict]:
    """The AI Chat instances your key may use (1 credit)."""
    r = http.get(f"{AI_CHAT}/instances", headers=lumen_headers())
    return expect(r, 200).get("Instances") or []


# ---------------------------------------------------------------- TODO 2
def open_session(http: httpx.Client, instance_id: str, title: str) -> str:
    """Open a conversation on one instance (2 credits). Returns the session ID."""
    # TODO 2: POST to f"{AI_CHAT}/instances/{instance_id}/sessions"
    #   with headers=lumen_headers() and json={"title": title}.
    # Lumen answers 201 with {"Session": {"id": ..., ...}}:
    #   body = expect(r, 201)          <- turns any error into a clear message
    #   return body["Session"]["id"]
    raise NotImplementedError("TODO 2: open a session in open_session()")


# ---------------------------------------------------------------- TODO 3
def send_message(http: httpx.Client, instance_id: str, session_id: str, question: str) -> NotesAnswer:
    """Ask one question in the session (5 credits). Returns the answer and its sources."""
    # TODO 3: POST to f"{AI_CHAT}/instances/{instance_id}/sessions/{session_id}/messages"
    #   with headers=lumen_headers() and json={"message": question}.
    # Lumen answers 200 with {"Answer": {"answer": ..., "citations": [...], "degradedSources": [...]}}:
    #   a = expect(r, 200)["Answer"]
    #   return NotesAnswer(
    #       text=a.get("answer") or "",
    #       sources=[Source(title=c) for c in a.get("citations") or []],
    #       degraded=a.get("degradedSources") or [],
    #   )
    raise NotImplementedError("TODO 3: send the question in send_message()")


# ---------------------------------------------------------------- TODO 4
def answer_or_refuse(a: NotesAnswer, subject: str) -> str:
    """No source, no answer: refuse when Lumen cites nothing, even if it wrote something."""
    # TODO 4: if there are no sources, or the text starts with "Not in your notes",
    #   return f"⚠️ Not in your {subject} notes. No guess."
    # (two lines: an if, and a return)

    # Given: print the answer, then one 📎 line per source.
    lines = [f"📘 {a.text.strip()}"]
    lines += [f"📎 {s.title}" for s in a.sources]
    if a.degraded:
        lines.append("⚠️ Some sources were offline: " + ", ".join(a.degraded))
    return "\n".join(lines)


# ---------------------------------------------------------------- given: one subject's conversation
SESSION_LOST = {"SESSION_NOT_OWNED", "SESSION_NOT_FOR_INSTANCE", "AI_CHAT_SESSION_NOT_FOUND", "AI_CHAT_CONFLICT"}
TRY_AGAIN = {429, 502, 503, 504}   # none of these are charged


class LumenNotes:
    """One subject's conversation with its Lumen instance.

    The session opens on the first question (so building this costs nothing)
    and is reused after that, so Lumen keeps the whole conversation.
    """

    def __init__(self, subject: str, http: httpx.Client | None = None, pause: float = 3.0):
        self.subject = subject
        self.instance = instance_for(subject)
        lumen_headers()  # stops here with TODO 1's message if it isn't done yet
        self.http = http or httpx.Client(timeout=35)   # Lumen gives up at 25 s; we wait a little longer
        self.pause = pause
        self.session_id: str | None = None

    def _send(self, message: str) -> NotesAnswer:
        if self.session_id is None:
            self.session_id = open_session(self.http, self.instance, f"Reviewer Agent - {self.subject} - {date.today()}")
        return send_message(self.http, self.instance, self.session_id, message)

    def ask(self, message: str) -> NotesAnswer:
        if len(message) > MAX_QUESTION:  # Lumen would answer 400; refuse before paying for anything
            return NotesAnswer(text=f"Question too long. Keep it under {MAX_QUESTION:,} characters.")
        try:
            return self._send(message)
        except LumenError as e:
            if e.code in SESSION_LOST:      # the session is gone: open a new one, once
                self.session_id = None
            elif e.status in TRY_AGAIN:     # not charged: pause, then try once more
                time.sleep(self.pause)
            else:
                raise
            return self._send(message)

    def transcript(self, limit: int = 50) -> list[dict]:
        """What Lumen stored in this session, oldest first (1 credit)."""
        if self.session_id is None:
            return []
        r = self.http.get(f"{AI_CHAT}/instances/{self.instance}/sessions/{self.session_id}/messages",
                          headers=lumen_headers(), params={"limit": limit})
        return expect(r, 200).get("Messages") or []


# ---------------------------------------------------------------- run it
def main(argv: list[str]) -> int:
    from helpers import ReviewerError
    from reviewer import ask_once

    subject = "bio"
    if "--subject" in argv:
        i = argv.index("--subject")
        subject = argv[i + 1] if i + 1 < len(argv) else ""
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print('Usage: python 01_ask.py "Ano ang ATP?" [--subject bio|econ|ph-history]')
        return 2
    try:
        notes = LumenNotes(subject)
        reply, _ = ask_once(notes, subject, " ".join(argv))
    except (ReviewerError, NotImplementedError) as e:
        print(f"❌ {e}")
        return 1
    except httpx.HTTPError as e:
        print(f"❌ Can't reach Lumen ({type(e).__name__}). Check your internet connection and LUMEN_BASE_URL.")
        return 1
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
