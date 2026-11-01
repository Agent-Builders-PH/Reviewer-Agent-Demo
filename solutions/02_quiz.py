"""Phase 2: Quiz. Lumen writes the quiz; Python checks it and grades it.

    python 02_quiz.py bio

Lumen AI Chat replies in plain text. There's no setting that forces a
shape on the reply, so we ask for JSON in the prompt, then Python does the
strict part: pull the JSON out, check it against the Quiz form (pydantic),
and ask once more if it doesn't fit. Python, not the model, compares your
letter with the answer, so the grading never drifts. Each result goes into
quiz_log.csv, and the next quiz starts with the questions you missed.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from config import QUIZ_LOG
from helpers import ReviewerError, extract_json, load_step

QUIZ_SIZE = 5


# ---------------------------------------------------------------- TODO 1
class Question(BaseModel):
    question: str
    a: str
    b: str
    c: str
    answer: Literal["a", "b", "c"]
    source: str = Field(description="The note the answer comes from")
    why: str = Field(description="One line")

    # Given: accept "A" or " b " from the model, but nothing outside a, b and c.
    @field_validator("answer", mode="before", check_fields=False)
    @classmethod
    def _letter(cls, v):
        return v.strip().lower() if isinstance(v, str) else v


class Quiz(BaseModel):
    questions: list[Question]


# The shape we ask Lumen for. One example question, written by Python, so the keys always match the form.
EXAMPLE = {"questions": [{"question": "...", "a": "...", "b": "...", "c": "...", "answer": "a",
                          "source": "the note it comes from", "why": "one short line"}]}

QUIZ_PROMPT = f"""Write a {QUIZ_SIZE}-question practice quiz using ONLY facts in your sources.
Reply with JSON only: no other words, no markdown, no code fences.
Use exactly this shape, with {QUIZ_SIZE} items in "questions":
{json.dumps(EXAMPLE)}
Each question has three choices, a, b and c, and exactly one right answer.
"answer" is the letter of the right choice: "a", "b" or "c".
Never use trick wording, "all of the above" or "none of the above"."""


# ---------------------------------------------------------------- TODO 2
def parse_quiz(reply: str) -> Quiz:
    """Turn Lumen's text reply into a checked Quiz. Raises ValueError if it doesn't fit."""
    return Quiz.model_validate_json(extract_json(reply))


# ---------------------------------------------------------------- TODO 3
def is_correct(letter: str, q: Question) -> bool:
    """Python grades, not the model: compare the typed letter with the right one."""
    return letter.strip().lower() == q.answer


# ---------------------------------------------------------------- given: ask for the quiz, check it
def quiz_problem(quiz: Quiz) -> str | None:
    """None when the quiz is usable, otherwise what is wrong with it."""
    if len(quiz.questions) != QUIZ_SIZE:
        return f"{len(quiz.questions)} questions instead of {QUIZ_SIZE}"
    return None


def write_quiz(notes, focus: list[str] | None = None) -> Quiz:
    """Ask the subject's Lumen instance for a quiz, check it in Python, and ask once more if it is off."""
    if not {"answer", "source"} <= set(Question.model_fields):
        raise ReviewerError("Question has no answer or source field yet. Finish TODO 1 in 02_quiz.py.")
    prompt = QUIZ_PROMPT
    if focus:
        prompt += "\nStart with these topics, which I got wrong last time:\n" + "\n".join(f"- {q}" for q in focus)
    problem = ""
    for _ in range(2):  # each try is one Lumen message: 5 credits
        reply = notes.ask(prompt).text
        try:
            quiz = parse_quiz(reply)
        except (ValueError, ValidationError) as e:
            problem = f"the reply didn't fit the Quiz form ({str(e).splitlines()[0][:80]})"
            continue
        problem = quiz_problem(quiz)
        if problem is None:
            return quiz
    raise ReviewerError(f"Lumen's quiz failed the check twice: {problem}. Run it again; if it repeats, "
                        "ask the host to check the quiz line in the instance's rules (instance_rules.md).")


# ---------------------------------------------------------------- given: quiz_log.csv
LOG_FIELDS = ["date", "subject", "score", "missed"]


def last_missed(subject: str, log: Path = QUIZ_LOG) -> list[str]:
    """The questions missed in this subject's most recent quiz."""
    if not log.exists():
        return []
    with log.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("subject") == subject]
    return [q for q in (rows[-1]["missed"].split(" | ") if rows else []) if q]


def log_result(subject: str, score: int, total: int, missed: list[str], log: Path = QUIZ_LOG) -> None:
    new = not log.exists() or log.stat().st_size == 0
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"date": date.today().isoformat(), "subject": subject,
                    "score": f"{score}/{total}", "missed": " | ".join(missed)})


# ---------------------------------------------------------------- given: one question at a time
def run_quiz(subject: str, notes=None, ask=input, say=print, log: Path = QUIZ_LOG) -> tuple[Quiz, int]:
    """Show one question, wait for a, b or c, grade it, then show why and the source."""
    notes = notes or load_step("01_ask").LumenNotes(subject)
    focus = last_missed(subject, log)
    say(f"Writing your {subject} quiz..." + (f" (starting with {len(focus)} you missed last time)" if focus else ""))
    quiz = write_quiz(notes, focus)
    score, missed = 0, []
    for n, q in enumerate(quiz.questions, start=1):
        say(f"\nQ{n}. {q.question}\n   a) {q.a}\n   b) {q.b}\n   c) {q.c}")
        letter = ""
        while letter not in ("a", "b", "c"):
            letter = ask("Your answer (a, b or c): ").strip().lower()
        if is_correct(letter, q):
            score += 1
            say("✅ Tama!")
        else:
            missed.append(q.question)
            say(f"❌ The answer is {q.answer}) {getattr(q, q.answer)}")
        say(f"   Why: {q.why} ({q.source})")
    say(f"\nScore: {score}/{len(quiz.questions)}. Saved to {log.name}.")
    log_result(subject, score, len(quiz.questions), missed, log)
    return quiz, score


def main(argv: list[str]) -> int:
    import httpx
    if not argv:
        print("Usage: python 02_quiz.py bio|econ|ph-history")
        return 2
    try:
        run_quiz(argv[0])
    except (ReviewerError, NotImplementedError) as e:
        print(f"❌ {e}")
        return 1
    except httpx.HTTPError as e:
        print(f"❌ Can't reach Lumen ({type(e).__name__}). Check your internet connection and LUMEN_BASE_URL.")
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nQuiz stopped. Nothing was saved.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
