"""The Reviewer Agent in your browser. You don't need to edit this file.

    python app.py            # then open http://127.0.0.1:8766

A small local web page on top of the same code as reviewer.py: pick a
subject, ask a question (Lumen AI Chat answers from that subject's notes),
take a quiz, or read what Lumen stored in the transcript. In the template it
shows which TODO to finish next, and it picks up your edits to 01_ask.py and
02_quiz.py as soon as you save them.

The quiz answers stay in Python: the page gets each right answer only after
you pick a letter, the same as in the terminal.

Plain Python standard library: no web framework to install. It listens on
127.0.0.1 only, so nobody else on the Wi-Fi can reach it.
"""
from __future__ import annotations

import csv
import importlib
import json
import mimetypes
import os
import sys
import threading
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from config import QUIZ_LOG, SUBJECTS, subject_dir
from helpers import ReviewerError, load_step
from reviewer import ask_once, make_notes

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui" / "index.html"
PORT = int(os.getenv("REVIEWER_PORT", "8766"))
NOTE_TYPES = {".pdf", ".md", ".txt"}
LOCK = threading.Lock()            # one Lumen call at a time
SESSIONS: dict[str, object] = {}   # one Lumen conversation per subject, reused
QUIZZES: dict[str, dict] = {}      # quiz id -> the Quiz and your answers so far (never sent whole)
SEEN: dict[str, float] = {}        # workshop file -> when it last changed


# --------------------------------------------------------------------------- what the page shows

def notes_in(subject: str) -> list[dict]:
    return [{"name": p.name, "kind": "PDF" if p.suffix.lower() == ".pdf" else "text"}
            for p in sorted(subject_dir(subject).iterdir()) if p.suffix.lower() in NOTE_TYPES]


def quiz_history() -> list[dict]:
    if not QUIZ_LOG.exists():
        return []
    with QUIZ_LOG.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return list(reversed(rows))[:12]


def state() -> dict:
    return {"subjects": [{"name": s, "notes": notes_in(s)} for s in SUBJECTS], "history": quiz_history()}


def reload_if_edited() -> None:
    """Pick up your edits to 01_ask.py and 02_quiz.py without restarting the app."""
    for name in ("01_ask", "02_quiz"):
        changed = (ROOT / f"{name}.py").stat().st_mtime
        if SEEN.setdefault(name, changed) != changed:
            SEEN[name] = changed
            importlib.reload(load_step(name))
            SESSIONS.clear()  # rebuild the conversations from the new code
            print(f"Reloaded {name}.py")


def friendly(e: Exception) -> str:
    if isinstance(e, (ReviewerError, NotImplementedError)):
        return str(e)
    if isinstance(e, httpx.HTTPError):
        return f"Can't reach Lumen ({type(e).__name__}). Check your internet connection and LUMEN_BASE_URL."
    return f"{type(e).__name__}: {e}"


def notes_for(subject: str):
    if subject not in SESSIONS:
        SESSIONS[subject] = make_notes(subject)
    return SESSIONS[subject]


# --------------------------------------------------------------------------- the web server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, code: int = 200) -> None:
        self.send(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", code)

    def body_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    # GET ---------------------------------------------------------------
    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            return self.send(UI.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/state":
            try:
                return self.send_json(state())
            except Exception as e:
                traceback.print_exc()
                return self.send_json({"error": friendly(e)}, 500)
        if path.startswith("/note/"):  # /note/<subject>/<file>: open the note the host gave Lumen
            parts = path.split("/")
            if len(parts) == 4 and parts[2] in SUBJECTS:
                file = subject_dir(parts[2]) / Path(parts[3]).name
                if file.is_file() and file.suffix.lower() in NOTE_TYPES:
                    ctype = "text/plain; charset=utf-8" if file.suffix.lower() != ".pdf" else "application/pdf"
                    return self.send(file.read_bytes(), ctype)
        if path.startswith("/assets/"):
            file = ROOT / "assets" / Path(path).name
            if file.is_file():
                return self.send(file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        self.send_json({"error": "not found"}, 404)

    # POST --------------------------------------------------------------
    def do_POST(self):
        routes = {"/api/ask": self.ask, "/api/transcript": self.transcript,
                  "/api/quiz/start": self.quiz_start, "/api/quiz/answer": self.quiz_answer}
        route = routes.get(urlparse(self.path).path)
        if route is None:
            return self.send_json({"error": "not found"}, 404)
        try:
            reload_if_edited()
            route(self.body_json())
        except Exception as e:  # show the problem on the page, and the details in the terminal
            if not isinstance(e, (ReviewerError, NotImplementedError, httpx.HTTPError)):
                traceback.print_exc()
            self.send_json({"error": friendly(e)}, 500)

    def subject_of(self, req: dict) -> str | None:
        subject = req.get("subject", "")
        if subject not in SUBJECTS:
            self.send_json({"error": "Pick a subject first."}, 400)
            return None
        return subject

    def ask(self, req: dict):
        subject = self.subject_of(req)
        question = (req.get("question") or "").strip()
        if subject is None:
            return
        if not question:
            return self.send_json({"error": "Type a question first."}, 400)
        with LOCK:
            reply, answer = ask_once(notes_for(subject), subject, question)
        refused = answer is None or reply.startswith("⚠️")
        self.send_json({
            "refused": refused,
            "reply": reply,
            "text": "" if refused else answer.text.strip(),
            "sources": [] if refused else [s.title for s in answer.sources],
            "degraded": [] if answer is None else answer.degraded,
        })

    def transcript(self, req: dict):
        subject = self.subject_of(req)
        if subject is None:
            return
        with LOCK:
            messages = notes_for(subject).transcript()
        self.send_json({"messages": [{"role": m.get("role", "?"), "content": str(m.get("content", ""))} for m in messages]})

    def quiz_start(self, req: dict):
        subject = self.subject_of(req)
        if subject is None:
            return
        step = load_step("02_quiz")
        focus = step.last_missed(subject)
        with LOCK:
            quiz = step.write_quiz(notes_for(subject), focus)
        quiz_id = uuid.uuid4().hex
        QUIZZES[quiz_id] = {"subject": subject, "quiz": quiz, "answers": {}, "missed": []}
        self.send_json({
            "id": quiz_id,
            "subject": subject,
            "focus": len(focus),
            # The questions and choices only. The right letters stay here in Python.
            "questions": [{"question": q.question, "a": q.a, "b": q.b, "c": q.c} for q in quiz.questions],
        })

    def quiz_answer(self, req: dict):
        entry = QUIZZES.get(req.get("id", ""))
        if entry is None:
            return self.send_json({"error": "That quiz has ended. Start a new one."}, 400)
        n, letter = int(req.get("n", -1)), str(req.get("letter", "")).strip().lower()
        questions = entry["quiz"].questions
        if not 0 <= n < len(questions) or letter not in ("a", "b", "c"):
            return self.send_json({"error": "Pick a, b or c."}, 400)
        if n in entry["answers"]:
            return self.send_json({"error": "You already answered that one."}, 400)
        q = questions[n]
        correct = load_step("02_quiz").is_correct(letter, q)  # your TODO 3 grades it
        entry["answers"][n] = correct
        if not correct:
            entry["missed"].append(q.question)
        done = len(entry["answers"]) == len(questions)
        score = sum(entry["answers"].values())
        if done:
            load_step("02_quiz").log_result(entry["subject"], score, len(questions), entry["missed"])
            QUIZZES.pop(req["id"], None)
        self.send_json({"correct": correct, "answer": q.answer, "answer_text": getattr(q, q.answer),
                        "why": q.why, "source": q.source, "done": done, "score": score, "total": len(questions)})


def main() -> None:
    for name in ("01_ask", "02_quiz"):
        load_step(name)
        SEEN[name] = (ROOT / f"{name}.py").stat().st_mtime
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Reviewer Agent is running at {url}  (Lumen AI Chat)")
    print("Press Ctrl+C to stop.")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
