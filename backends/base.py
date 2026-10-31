"""One answer shape for both backends.

ClaudeNotes and LumenNotes both return a NotesAnswer, so the guard and the CLI
never care which brain answered. That is the whole trick behind NOTES_BACKEND.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Source:
    title: str                 # the file name, or Lumen's citation string
    page: int | None = None    # PDFs on the Claude path only
    quote: str = ""            # the exact text Claude cited, when we have it


@dataclass
class NotesAnswer:
    text: str
    sources: list[Source] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)   # Lumen: sources that were offline
    cache_read: int = 0        # Claude: prompt tokens read from the cache
    cache_write: int = 0       # Claude: prompt tokens written to the cache


class NotesBackend(Protocol):
    def ask(self, question: str) -> NotesAnswer: ...


class ReviewerError(Exception):
    """A problem the user can fix (a bad key, no credits, a missing setting). The CLI prints it plainly."""
