"""The Reviewer Agent CLI: ask | quiz | chat | instances.

    python reviewer.py ask "Ano ang ATP?" --subject bio
    python reviewer.py quiz bio
    python reviewer.py chat --subject bio          # type a question, "quiz me" or "transcript"
    python reviewer.py instances                   # the Lumen AI Chat instances your key can use (1 credit)

Every answer and every quiz comes from the subject's Lumen AI Chat instance.
The router is plain Python: a message starting with "quiz me" runs the quiz,
anything else is a question. Beginners can read it, and it never misroutes.
"""
from __future__ import annotations

import sys

import httpx

from config import MAX_QUESTION, SUBJECTS
from helpers import NotesAnswer, ReviewerError, load_step


def make_notes(subject: str):
    return load_step("01_ask").LumenNotes(subject)


def ask_once(notes, subject: str, question: str) -> tuple[str, NotesAnswer | None]:
    """One question through the guard. Returns what to print, and the raw answer (None if refused early)."""
    question = question.strip()
    if not question:
        return "Type a question first.", None
    if len(question) > MAX_QUESTION:  # refused here, before any API call
        return f"⚠️ Question too long ({len(question):,} characters). Keep it under {MAX_QUESTION:,}.", None
    answer = notes.ask(question)
    return load_step("01_ask").answer_or_refuse(answer, subject), answer


def show_transcript(notes) -> None:
    messages = notes.transcript()
    if not messages:
        print("Nothing yet: ask a question first.")
    for m in messages:
        print(f"  {m.get('role', '?'):>9}: {' '.join(str(m.get('content', '')).split())[:100]}")


def chat(subject: str) -> int:
    notes = make_notes(subject)
    print(f"Reviewer Agent · {subject} notes · Lumen AI Chat")
    print('Type a question, "quiz me", "transcript" (what Lumen stored), or "exit".')
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
                load_step("02_quiz").run_quiz(subject, notes)
            elif message.lower() == "transcript":
                show_transcript(notes)
            else:
                print(ask_once(notes, subject, message)[0])
        except (ReviewerError, NotImplementedError) as e:
            print(f"❌ {e}")
        except httpx.HTTPError as e:
            print(f"❌ Can't reach Lumen ({type(e).__name__}). Check your internet connection.")


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
    command = argv.pop(0) if argv else ""
    try:
        if command == "ask" and argv:
            print(ask_once(make_notes(subject), subject, " ".join(argv))[0])
        elif command == "quiz":
            quiz_subject = argv[0] if argv else subject
            load_step("02_quiz").run_quiz(quiz_subject)
        elif command == "chat":
            return chat(subject)
        elif command == "instances":
            found = load_step("01_ask").list_instances(httpx.Client(timeout=35))
            if not found:
                print("No AI Chat instances yet. The host creates them in the Lumen Organization Portal.")
            for i in found:
                print(f"{i.get('InstanceID')}  {i.get('Name')}  [{i.get('Status')}]  {i.get('Description') or ''}")
        else:
            print(__doc__)
            print(f"Subjects: {', '.join(SUBJECTS)}")
            return 2
    except (ReviewerError, NotImplementedError) as e:
        print(f"❌ {e}")
        return 1
    except httpx.HTTPError as e:
        print(f"❌ Can't reach Lumen ({type(e).__name__}). Check your internet connection and LUMEN_BASE_URL.")
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nStopped.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
