"""Ask mode on Claude, through Agno: documents + citations + prompt caching.

The agent itself is yours: you build it in 01_ask.py (TODOs 1 to 3).
This file wraps it so it answers in the shared NotesAnswer shape.
"""
from __future__ import annotations

from agno.run.base import RunStatus

from config import subject_dir
from helpers import load_notes, load_step

from .base import NotesAnswer, ReviewerError, Source


def read_citations(run) -> list[Source]:
    """Turn Claude's citations into Sources: file name, page, and the quoted text.

    Agno keeps every citation in run.citations.raw. A PDF gives a page_location
    (start_page_number is the page); a .md or .txt file gives a char_location,
    which has no page. Several quotes from the same page become one Source.
    """
    raw = (run.citations.raw if run.citations else None) or []
    sources: list[Source] = []
    seen = set()
    for c in raw:
        title = c.get("document_title") or "notes"
        page = c.get("start_page_number") if c.get("type") == "page_location" else None
        if (title, page) in seen:
            continue
        seen.add((title, page))
        sources.append(Source(title=title, page=page, quote=(c.get("cited_text") or "").strip()))
    return sources


def raise_if_failed(run) -> None:
    """Agno returns a failed call as a run with status ERROR. Turn it into a clear message."""
    if getattr(run, "status", None) != RunStatus.error:
        return
    text = str(run.content or "")
    if "401" in text or "authentication" in text:
        raise ReviewerError("Anthropic rejected the key (401). Check ANTHROPIC_API_KEY in .env.")
    if "credit balance" in text:
        raise ReviewerError("Your Anthropic account is out of credits. Add credits in the Claude Console.")
    if "429" in text or "rate_limit" in text:
        raise ReviewerError("Claude is rate-limiting this key (429). Wait a minute and try again.")
    raise ReviewerError(f"The Claude call failed: {text[:200]}")


class ClaudeNotes:
    """One subject's notes, answered by your Agno agent from 01_ask.py."""

    def __init__(self, subject: str):
        self.step = load_step("01_ask")
        self.notes = load_notes(subject_dir(subject))  # loaded once, sent with every question
        self.agent = self.step.make_ask_agent()
        if self.agent is None:
            raise ReviewerError("make_ask_agent() returned None. Finish TODO 2 in 01_ask.py.")

    def ask(self, question: str) -> NotesAnswer:
        run = self.step.ask_notes(self.agent, question, self.notes)
        if run is None:
            raise ReviewerError("ask_notes() returned None. Finish TODO 3 in 01_ask.py.")
        raise_if_failed(run)
        metrics = run.metrics
        return NotesAnswer(
            text=str(run.content or ""),
            sources=read_citations(run),
            cache_read=(metrics.cache_read_tokens or 0) if metrics else 0,
            cache_write=(metrics.cache_write_tokens or 0) if metrics else 0,
        )
