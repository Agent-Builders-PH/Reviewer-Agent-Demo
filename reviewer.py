"""The Reviewer Agent CLI: ask | quiz | chat.

    python reviewer.py ask "Ano ang ATP?" --subject bio
    python reviewer.py quiz bio
    python reviewer.py chat --subject bio          # type a question, or "quiz me"
    python reviewer.py instances                   # host only: list Lumen AI Chat instances

NOTES_BACKEND in .env picks who answers Ask questions: claude (default) or
lumen. --backend lumen does the same for one run. Quiz always runs on Claude
with the local notes, because Lumen replies in free text, not a Quiz form.

The router is plain Python: a message starting with "quiz me" runs the quiz,
anything else is a question. Beginners can read it, and it never misroutes.
"""
from __future__ import annotations

import sys

from backends.base import NotesAnswer, NotesBackend, ReviewerError
from config import MAX_QUESTION, NOTES_BACKEND, SUBJECTS
from helpers import load_step


def make_backend(subject: str, backend: str | None = None) -> NotesBackend:
    """claude -> ClaudeNotes (your Agno agent); lumen -> LumenNotes (Lumen AI Chat)."""
    name = (backend or NOTES_BACKEND).lower()
    if name == "claude":
        from backends.claude_notes import ClaudeNotes
        return ClaudeNotes(subject)
    if name == "lumen":
        from backends.lumen_notes import LumenNotes
        return LumenNotes(subject)
    raise ReviewerError(f"NOTES_BACKEND must be claude or lumen, not {name!r}.")


def ask_once(backend: NotesBackend, subject: str, question: str) -> tuple[str, NotesAnswer | None]:
    """One question through the guard. Returns what to print, and the raw answer (None if refused early)."""
    question = question.strip()
    if not question:
        return "Type a question first.", None
    if len(question) > MAX_QUESTION:  # refused here, before any API call, on both backends
        return f"⚠️ Question too long ({len(question):,} characters). Keep it under {MAX_QUESTION:,}.", None
    answer = backend.ask(question)
    return load_step("01_ask").answer_or_refuse(answer, subject), answer


def chat(subject: str, backend_name: str | None = None) -> int:
    backend = make_backend(subject, backend_name)
    brain = "Lumen AI Chat" if type(backend).__name__ == "LumenNotes" else "Claude"
    print(f"Reviewer Agent · {subject} notes · Ask: {brain} · Quiz: Claude")
    print('Type a question, "quiz me", or "exit".' + (' "transcript" shows what Lumen stored.' if brain != "Claude" else ""))
    while True:
        try:
            message = input(f"\n{subject}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if message.lower() in ("exit", "quit", "bye"):
            return 0
        try:
            if message.lower().startswith("quiz me"):
                load_step("02_quiz").run_quiz(subject)
            elif message.lower() == "transcript" and hasattr(backend, "transcript"):
                for m in backend.transcript():
                    print(f"  {m.get('role', '?'):>9}: {' '.join(str(m.get('content', '')).split())[:100]}")
            else:
                print(ask_once(backend, subject, message)[0])
        except (ReviewerError, NotImplementedError) as e:
            print(f"❌ {e}")


def pop_option(argv: list[str], name: str, default: str | None = None) -> str | None:
    if name in argv:
        i = argv.index(name)
        value = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
        return value
    return default


def main(argv: list[str]) -> int:
    argv = list(argv)
    subject = pop_option(argv, "--subject", "bio")
    backend = pop_option(argv, "--backend")
    command = argv.pop(0) if argv else ""
    try:
        if command == "ask" and argv:
            print(ask_once(make_backend(subject, backend), subject, " ".join(argv))[0])
        elif command == "quiz":
            load_step("02_quiz").run_quiz(argv[0] if argv else subject)
        elif command == "chat":
            return chat(subject, backend)
        elif command == "instances":
            from backends.lumen_notes import list_instances
            found = list_instances()
            print("No AI Chat instances yet. Create one in the Lumen Organization Portal." if not found else "")
            for i in found:
                print(f"{i.get('InstanceID')}  {i.get('Name')}  [{i.get('Status')}]  {i.get('Description') or ''}")
        else:
            print(__doc__)
            print(f"Subjects: {', '.join(SUBJECTS)}")
            return 2
    except (ReviewerError, NotImplementedError) as e:
        print(f"❌ {e}")
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nStopped.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
