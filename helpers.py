"""Small helpers you can read but don't need to change.

    load_notes(folder)          one subject folder -> a list of Claude document blocks
    notes_message(notes, text)  the notes first, then your text, as one user message
    page_count(folder)          the most pages any PDF in the folder has
    print_with_pages(answer)    print an answer with its sources and pages
    load_step(name)             import 01_ask.py or 02_quiz.py by name
"""
from __future__ import annotations

import base64
import importlib
import sys
from pathlib import Path

from agno.models.message import Message
from pypdf import PdfReader

NOTE_TYPES = {".pdf", ".md", ".txt"}


def load_notes(folder: Path, citations: bool = True) -> list[dict]:
    """Turn every note in one subject folder into a Claude document block.

    Each block carries the file name as its title, so a citation comes back
    saying which file (and, for a PDF, which page) it quotes.

    The last block gets a cache_control marker. Claude caches everything up to
    that marker: the rules plus all the notes. A second question, even a
    different one, then reads the notes from the cache instead of paying for
    them again. That only works because notes_message() puts the notes BEFORE
    the question; anything after the marker is never cached.

    citations=False is for the quiz: structured output and citations can't
    share a request.
    """
    blocks = []
    for path in sorted(folder.iterdir()):  # same order every time, so the cached prefix matches
        if path.suffix.lower() not in NOTE_TYPES:
            continue
        if path.suffix.lower() == ".pdf":
            source = {"type": "base64", "media_type": "application/pdf",
                      "data": base64.standard_b64encode(path.read_bytes()).decode("ascii")}
        else:
            source = {"type": "text", "media_type": "text/plain",
                      "data": path.read_text(encoding="utf-8")}
        block = {"type": "document", "source": source, "title": path.name}
        if citations:
            block["citations"] = {"enabled": True}
        blocks.append(block)
    if not blocks:
        raise SystemExit(f"No notes in {folder}. Add a .pdf, .md or .txt file.")
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def notes_message(notes: list[dict], text: str) -> Message:
    """One user message: all the notes first, then the question (or quiz request) last."""
    return Message(role="user", content=[*notes, {"type": "text", "text": text}])


def page_count(folder: Path) -> int:
    """The most pages in any PDF in this folder (a quiz page must be 1 to this)."""
    counts = [len(PdfReader(p).pages) for p in folder.glob("*.pdf")]
    return max(counts, default=1)


def print_with_pages(answer) -> None:
    """Print a NotesAnswer the long way: the text, then every source with its page and quote."""
    print(answer.text.strip())
    for s in answer.sources:
        page = f" p.{s.page}" if s.page else ""
        quote = " ".join(s.quote.split())[:70]
        print(f"   - {s.title}{page}: \"{quote}\"")


def load_step(name: str):
    """Import a workshop file such as 01_ask.py.

    `import 01_ask` is a syntax error (names can't start with a digit), so we
    import it by name. If you ran that file directly, reuse the running copy.
    """
    main = sys.modules.get("__main__")
    if main is not None and Path(getattr(main, "__file__", "") or "").stem == name:
        return main
    return importlib.import_module(name)
