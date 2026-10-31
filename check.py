"""Setup check and phase checks for the Reviewer Agent. Run it after every phase.

    python check.py              # setup, plus the quick offline checks for every phase (free)
    python check.py 1            # Phase 1: offline checks, then a live check with Claude
    python check.py 2            # Phase 2: same
    python check.py 3            # Phase 3: offline checks, then all 10 cases in cases.json
    python check.py 3 --offline  # skip the live part (no Claude calls, no cost)
    python check.py 3 --backend lumen   # host only: cases 1-3, 6, 7, 10 on Lumen AI Chat (~36 credits)

Each line says PASS, FAIL (with the one thing to fix) or TODO (not written yet).
Live quiz checks write to a scratch log, so your own quiz_log.csv is never touched.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import sys
import tempfile
import traceback
import typing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AGNO_PIN = "3.1.3"
PLACEHOLDER = "sk-ant-your-key-here"
OFFLINE, LIVE = [], []


def offline(phase: int):
    def register(fn):
        OFFLINE.append((phase, fn))
        return fn
    return register


def live(phase: int):
    def register(fn):
        LIVE.append((phase, fn))
        return fn
    return register


class Todo(Exception):
    pass


def todo(message: str):
    raise Todo(message)


def step(name: str):
    from helpers import load_step
    return load_step(name)


# ---------------------------------------------------------------- fakes (no API calls)

def fake_answer(text="ATP is the cell's energy currency.", sources=(("bio-week5.pdf", 1),), degraded=()):
    from backends.base import NotesAnswer, Source
    return NotesAnswer(text=text, sources=[Source(title=t, page=p) for t, p in sources], degraded=list(degraded))


class Exploding:
    """A backend that fails the test if anything calls it."""

    def ask(self, question):
        raise AssertionError("the backend was called; long questions must be refused before any API call")


def sample_quiz():
    Question, Quiz = step("02_quiz").Question, step("02_quiz").Quiz
    rows = [("What is ATP?", "energy currency", "a sugar", "a membrane", "a", 1),
            ("Where is glycolysis?", "matrix", "cytoplasm", "cristae", "b", 3),
            ("What are cristae?", "DNA", "fluid", "membrane folds", "c", 2),
            ("Which gas is used last?", "oxygen", "carbon dioxide", "nitrogen", "a", 2),
            ("Muscle fermentation makes?", "ethanol", "lactic acid", "glucose", "b", 3)]
    return Quiz(subject="bio", questions=[
        Question(question=q, a=a, b=b, c=c, answer=ans, page=p, why=f"why-{i}")
        for i, (q, a, b, c, ans, p) in enumerate(rows)])


def drive_quiz(subject: str, answers: str, log: Path):
    """Run the quiz loop with scripted letters. Returns (quiz, score, printed text, text seen before each answer)."""
    printed, seen = [], []

    def say(*parts):
        printed.append(" ".join(str(p) for p in parts))

    letters = iter(answers)

    def ask(prompt):
        seen.append("\n".join(printed))
        return next(letters)

    quiz, score = step("02_quiz").run_quiz(subject, ask=ask, say=say, log=log)
    return quiz, score, "\n".join(printed), seen


def hidden_until_typed(quiz, seen) -> str | None:
    """None when no question's answer (its 'why' line) was printed before its letter was typed."""
    for i, q in enumerate(quiz.questions):
        before = seen[i] if i < len(seen) else ""
        if q.why and q.why in before:
            return f"Q{i + 1}'s answer was printed before a letter was typed"
    return None


# ---------------------------------------------------------------- Phase 0: setup

@offline(0)
def python_and_packages():
    assert sys.version_info >= (3, 11), f"Python {sys.version.split()[0]} is too old; use 3.11 or newer (3.12 recommended)"
    try:
        have = importlib.metadata.version("agno")
    except importlib.metadata.PackageNotFoundError:
        raise AssertionError("agno isn't installed. Activate .venv, then: uv pip install -r requirements.txt")
    assert have == AGNO_PIN, f"agno {have} is installed; this module is pinned to {AGNO_PIN}. Run: uv pip install -r requirements.txt"
    for pkg in ("anthropic", "pydantic", "httpx", "pypdf", "python-dotenv"):
        importlib.metadata.version(pkg)
    print(f"      Python {sys.version.split()[0]}, agno {have}")


@offline(0)
def env_and_notes():
    assert (ROOT / ".env").exists(), "No .env yet. Run: copy .env.example .env, then paste your key"
    from config import NOTES_BACKEND, SUBJECTS, subject_dir
    key = os.getenv("ANTHROPIC_API_KEY", "")
    assert key and key != PLACEHOLDER, "ANTHROPIC_API_KEY in .env is empty or still the placeholder"
    for s in SUBJECTS:
        folder = subject_dir(s)
        assert folder.is_dir() and any(folder.iterdir()), f"notes/{s}/ is missing or empty"
    print(f"      notes: {', '.join(SUBJECTS)}; NOTES_BACKEND={NOTES_BACKEND}")


@offline(0)
def anthropic_key_works():
    import anthropic
    from config import MODEL
    try:
        anthropic.Anthropic().models.retrieve(MODEL)  # free: no tokens
    except anthropic.AuthenticationError:
        raise AssertionError("Anthropic rejected the key (401). Create a new key in the Claude Console")
    except anthropic.NotFoundError:
        raise AssertionError(f"This key can't use {MODEL}. Check REVIEWER_MODEL in .env")
    except anthropic.APIConnectionError:
        raise AssertionError("Can't reach api.anthropic.com. Check your internet connection")


# ---------------------------------------------------------------- Phase 1: Ask (01_ask.py)

@offline(1)
def todo1_ask_rules():
    rules = step("01_ask").ASK_RULES
    if "TODO" in rules:
        todo("TODO 1: write the four ASK_RULES lines in 01_ask.py")
    low = rules.lower()
    for words, hint in (("only", "answer ONLY from the attached notes"),
                        ("not in your notes", "reply exactly: Not in your notes."),
                        ("disagree", "when two notes disagree, give both and say so"),
                        ("short", "keep answers short")):
        assert words in low, f"ASK_RULES needs a line that says: {hint}"


@offline(1)
def todo2_ask_agent():
    from agno.agent import Agent
    from agno.models.anthropic import Claude
    from config import MODEL
    s = step("01_ask")
    agent = s.make_ask_agent()
    assert isinstance(agent, Agent), "make_ask_agent() should return an Agent"
    assert isinstance(agent.model, Claude), "use model=Claude(...)"
    assert agent.model.id == MODEL, f"use Claude(id=MODEL); got {agent.model.id!r}"
    assert agent.model.cache_system_prompt, "add cache_system_prompt=True to Claude(...)"
    assert agent.instructions == s.ASK_RULES, "pass instructions=ASK_RULES"
    assert agent.output_schema is None, "the Ask agent has no output_schema (that would switch citations off)"


@offline(1)
def todo3_send_notes_then_question():
    from agno.models.message import Message
    calls = []
    fake = SimpleNamespace(run=lambda *a, **k: calls.append((a, k)) or "the run")
    notes = [{"type": "document", "title": "n1.pdf"}, {"type": "document", "title": "n2.md"}]
    out = step("01_ask").ask_notes(fake, "Ano ang ATP?", notes)
    if not calls:
        todo("TODO 3: call agent.run(...) in ask_notes()")
    args, kwargs = calls[0]
    msg = args[0] if args else kwargs.get("input")
    assert isinstance(msg, Message), "send notes_message(notes, question), not the bare question"
    assert msg.content[:2] == notes, "the notes go first: notes_message(notes, question)"
    assert msg.content[-1].get("text") == "Ano ang ATP?", "the question goes last: notes_message(notes, question)"
    assert out == "the run", "return the run from ask_notes()"


@offline(1)
def todo4_no_source_no_answer():
    guard = step("01_ask").answer_or_refuse
    refusal = guard(fake_answer(text="ATP is energy.", sources=()), "bio")
    if not refusal.startswith("⚠️ Not in your bio notes"):
        todo("TODO 4: in answer_or_refuse, return the refusal when there are no sources")
    assert guard(fake_answer(text="Not in your notes."), "bio").startswith("⚠️ Not in your bio notes"), \
        "refuse when Claude says Not in your notes, even if a source came back"
    ok = guard(fake_answer(), "bio")
    assert ok.startswith("📘") and "📎 bio-week5.pdf · p.1" in ok, "an answer with a source should print 📘 and 📎 lines"


@live(1)
def ask_twice_with_pages_and_cache():
    from backends.claude_notes import ClaudeNotes
    backend = ClaudeNotes("bio")
    first = backend.ask("Ano ang ATP?")
    second = backend.ask("Saan nangyayari ang glycolysis?")
    for a in (first, second):
        pages = ", ".join(f"{s.title} p.{s.page}" for s in a.sources) or "no sources"
        print(f"      {a.text.strip().splitlines()[0][:80]}")
        print(f"        sources: {pages} | cache read {a.cache_read:,}, wrote {a.cache_write:,}")
    assert any(s.title == "bio-week5.pdf" and s.page and 1 <= s.page <= 3 for s in first.sources), \
        "the ATP answer should cite bio-week5.pdf with a page"
    assert second.cache_read > 0, "the second question should read the notes from the cache"


# ---------------------------------------------------------------- Phase 2: Quiz (02_quiz.py)

@offline(2)
def todo1_question_fields():
    fields = step("02_quiz").Question.model_fields
    if "answer" not in fields or "page" not in fields:
        todo('TODO 1: add answer: Literal["a", "b", "c"] and page: int to Question in 02_quiz.py')
    assert set(typing.get_args(fields["answer"].annotation)) == {"a", "b", "c"}, \
        'answer should be Literal["a", "b", "c"]'
    assert fields["page"].annotation is int, "page should be an int"


@offline(2)
def todo2_quiz_agent():
    from agno.models.anthropic import Claude
    from config import MODEL
    s = step("02_quiz")
    agent = s.make_quiz_agent()
    if agent.output_schema is None:
        todo("TODO 2: pass output_schema=Quiz to the quiz agent")
    assert agent.output_schema is s.Quiz, "output_schema should be Quiz"
    assert isinstance(agent.model, Claude) and agent.model.id == MODEL, "use model=Claude(id=MODEL)"


@offline(2)
def todo3_python_grades():
    s = step("02_quiz")
    if "answer" not in s.Question.model_fields:
        todo("TODO 3 needs TODO 1 first")
    q = sample_quiz().questions[0]  # the right answer is a
    assert s.is_correct("a", q) is True, "is_correct('a', q) should be True when q.answer is 'a'"
    assert s.is_correct(" A ", q) is True, "ignore spaces and capitals: compare letter.strip().lower()"
    assert s.is_correct("b", q) is False, "is_correct('b', q) should be False when q.answer is 'a'"


@offline(2)
def quiz_loop_hides_answers_and_logs():
    s = step("02_quiz")
    if "answer" not in s.Question.model_fields:
        todo("this check needs TODO 1 first")
    with tempfile.TemporaryDirectory() as tmp, mock.patch.object(s, "write_quiz", lambda subject, focus=None: sample_quiz()):
        log = Path(tmp) / "quiz_log.csv"
        quiz, score, printed, seen = drive_quiz("bio", "aaaaa", log)
        assert score == 2, f"answering a,a,a,a,a should score 2/5; got {score}"
        problem = hidden_until_typed(quiz, seen)
        assert problem is None, problem
        rows = log.read_text(encoding="utf-8").splitlines()
        assert len(rows) == 2 and rows[1].split(",")[2] == "2/5", "one row should be added to quiz_log.csv"
        assert s.last_missed("bio", log)[0] == "Where is glycolysis?", "the next quiz should start with the missed questions"


@live(2)
def one_real_quiz():
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "quiz_log.csv"
        quiz, score, printed, seen = drive_quiz("bio", "abcab", log)
        for i, q in enumerate(quiz.questions, 1):
            print(f"      Q{i} p.{q.page} [{q.answer}] {q.question[:70]}")
        print(f"      score {score}/5 (scripted letters), {len(log.read_text(encoding='utf-8').splitlines()) - 1} row logged")
        assert len(quiz.questions) == 5
        problem = hidden_until_typed(quiz, seen)
        assert problem is None, problem


# ---------------------------------------------------------------- Phase 3: the guard, the swap, the 10 cases

@offline(3)
def long_questions_refused_before_any_call():
    from reviewer import ask_once
    reply, answer = ask_once(Exploding(), "bio", "Ano ang ATP? " * 350)
    assert answer is None and reply.startswith("⚠️ Question too long"), "a 4,500-character question should be refused"


@offline(3)
def router_sends_quiz_me_to_the_quiz():
    import reviewer
    quizzes, asked = [], []
    backend = SimpleNamespace(ask=lambda q: asked.append(q) or fake_answer())
    with mock.patch.object(reviewer, "make_backend", lambda subject, name=None: backend), \
         mock.patch.object(step("02_quiz"), "run_quiz", lambda subject: quizzes.append(subject)), \
         mock.patch("builtins.input", side_effect=["Quiz me please", "Ano ang ATP?", "exit"]), \
         mock.patch("builtins.print"):
        reviewer.chat("bio")
    assert quizzes == ["bio"], '"quiz me" should run the quiz'
    assert asked == ["Ano ang ATP?"], "anything else should go to backend.ask()"


@offline(3)
def lumen_client_against_a_fake_server():
    import httpx
    from backends import lumen_notes
    from backends.base import ReviewerError

    def server(script):
        calls = []

        def handle(request: httpx.Request):
            calls.append((request.method, request.url.path))
            assert request.headers.get("lumen-api-key") == "k" and request.headers.get("lumen-api-secret") == "s"
            status, body = script.pop(0)
            return httpx.Response(status, json=body)
        return httpx.Client(transport=httpx.MockTransport(handle)), calls

    answer = {"Answer": {"sessionID": "s2", "answer": "ATP is energy.", "citations": ["Bio Week 5"], "degradedSources": []}}
    env = {"LUMEN_API_KEY": "k", "LUMEN_API_SECRET": "s"}
    with mock.patch.dict(os.environ, env), mock.patch.object(lumen_notes, "LUMEN_INSTANCES", {"bio": "inst-1"}):
        # 1. a lost session is reopened once
        http, calls = server([(201, {"Session": {"id": "s1"}}),
                              (403, {"error": {"code": "SESSION_NOT_OWNED"}}),
                              (201, {"Session": {"id": "s2"}}),
                              (200, answer)])
        a = lumen_notes.LumenNotes("bio", http=http, pause=0).ask("Ano ang ATP?")
        assert a.text == "ATP is energy." and a.sources[0].title == "Bio Week 5", "parse Answer.answer and Answer.citations"
        assert [c[0] for c in calls] == ["POST"] * 4 and calls[-1][1].endswith("/sessions/s2/messages")
        # 2. a timeout (504, not charged) is retried once
        http, calls = server([(201, {"Session": {"id": "s1"}}),
                              (504, {"error": {"code": "AI_CHAT_REPLY_TIMEOUT"}}),
                              (200, answer)])
        assert lumen_notes.LumenNotes("bio", http=http, pause=0).ask("Ano?").text == "ATP is energy."
        # 3. out of credits is NOT retried, and says so plainly
        http, calls = server([(201, {"Session": {"id": "s1"}}),
                              (403, {"error": {"code": "API_CREDITS_INSUFFICIENT"}})])
        try:
            lumen_notes.LumenNotes("bio", http=http, pause=0).ask("Ano?")
            raise AssertionError("out of credits should raise")
        except ReviewerError as e:
            assert "credits" in str(e) and len(calls) == 2
        # 4. a long question never reaches Lumen
        http, calls = server([])
        lumen_notes.LumenNotes("bio", http=http).ask("x" * 4001)
        assert calls == []


def run_case(case: dict, backends: dict, backend_name: str, log: Path):
    """Run one case. Returns (problem or None, text to show)."""
    from reviewer import ask_once, make_backend
    subject = case["subject"]
    if subject not in backends:
        backends[subject] = make_backend(subject, backend_name)
    backend, lumen = backends[subject], backend_name == "lumen"
    kind = case["check"]

    if kind in ("quiz", "quiz_no_key"):
        quiz, score, printed, seen = drive_quiz(subject, "abcab", log)
        problem = hidden_until_typed(quiz, seen)
        if problem is None and len(quiz.questions) != 5:
            problem = f"{len(quiz.questions)} questions"
        if problem is None and kind == "quiz_no_key" and "answer key" in seen[0].lower():
            problem = "an answer key was printed"
        return problem, f"{len(quiz.questions)} questions, pages {[q.page for q in quiz.questions]}, score {score}/5"

    if kind == "too_long":
        text = (case["input"] * (case["repeat_to"] // len(case["input"]) + 1))[:case["repeat_to"]]
        reply, _ = ask_once(Exploding(), subject, text)
        return (None if reply.startswith("⚠️ Question too long") else "not refused"), reply

    if kind == "cache_read":
        answers = [ask_once(backend, subject, case["input"])[1] for _ in range(case["times"])]
        last = answers[-1]
        if last is None:
            return "refused", ""
        return (None if last.cache_read > 0 else "no cache reads on the second run"), \
            f"cache read {last.cache_read:,} tokens on run {case['times']}"

    reply, a = ask_once(backend, subject, case["input"])
    titles = [s.title for s in (a.sources if a else [])]
    text = (a.text if a else "").lower()
    problem = None
    if kind == "refusal":
        if not reply.startswith(f"⚠️ Not in your {subject} notes"):
            problem = "should refuse: the notes don't cover this"
    elif not titles or reply.startswith("⚠️"):
        problem = "no source came back, so the guard refused"
    elif lumen:  # Lumen cites source names, not pages, so its checks are looser
        if kind == "both_handouts" and "disagree" not in text:
            problem = 'should say the handouts "disagree"'
        if kind == "names_injection" and "answer key" not in text:
            problem = "should describe the answer-key line"
    elif kind == "source_page":
        if not any(s.title == case["file"] and s.page and case["pages"][0] <= s.page <= case["pages"][1] for s in a.sources):
            problem = f"no source from {case['file']} p.{case['pages'][0]}-{case['pages'][1]}"
    elif kind == "both_handouts":
        if not set(case["files"]) <= set(titles):
            problem = f"needs one source from each handout; got {titles}"
        elif "disagree" not in text:
            problem = 'should say the handouts "disagree"'
    elif kind in ("source_file", "names_injection"):
        if case["file"] not in titles:
            problem = f"no source from {case['file']}; got {titles}"
        elif kind == "names_injection" and "answer key" not in text:
            problem = "should describe the answer-key line as text in the notes"
    elif kind == "any_handout":
        if not set(case["files"]) & set(titles):
            problem = f"no source from either handout; got {titles}"
    return problem, reply


@live(3)
def all_cases_pass():
    backend_name = BACKEND
    cases = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
    if backend_name == "lumen":
        cases = [c for c in cases if c["lumen"]]
        print("      Lumen AI Chat answers Ask; cases 1-3, 6, 7, 10 only (about 36 credits)")
    backends, passed = {}, 0
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "quiz_log.csv"
        for case in cases:
            try:
                problem, shown = run_case(case, backends, backend_name, log)
            except Exception as e:  # one broken case shouldn't hide the others
                problem, shown = f"{type(e).__name__}: {e}", ""
            passed += problem is None
            mark = "PASS" if problem is None else "FAIL"
            print(f"      {mark} #{case['id']:<2} {case['subject']:<10} {case['pass_when'][:58]}")
            if case["id"] <= 5 or problem:
                for line in str(shown).splitlines()[:6]:
                    print(f"             {line[:100]}")
            if problem:
                print(f"             -> {problem}")
    print(f"      {passed} of {len(cases)} cases pass")
    assert passed == len(cases), f"{len(cases) - passed} case(s) failed; see the FAIL lines above"


# ---------------------------------------------------------------- runner

NEXT = {
    1: "open 01_ask.py and start at TODO 1",
    2: "open 02_quiz.py and start at TODO 1",
    3: "python check.py 3 runs all 10 cases",
}
BACKEND = "claude"


def run(name: str, fn) -> str:
    try:
        fn()
    except Todo as t:
        print(f"  TODO  {name}: {t}")
        return "todo"
    except NotImplementedError as e:
        print(f"  TODO  {name}: {e}")
        return "todo"
    except AssertionError as e:
        print(f"  FAIL  {name}: {e}")
        return "fail"
    except SystemExit as e:
        print(f"  FAIL  {name}: {e}")
        return "fail"
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        where = next((f"{Path(f.filename).name}:{f.lineno}" for f in reversed(tb)
                      if str(ROOT) in f.filename and "check.py" not in f.filename), "")
        print(f"  FAIL  {name}: {type(e).__name__}: {e} {where}".rstrip())
        return "fail"
    print(f"  PASS  {name}")
    return "pass"


def main(argv: list[str]) -> int:
    global BACKEND
    no_live = "--offline" in argv
    if "--backend" in argv:
        i = argv.index("--backend")
        BACKEND = argv[i + 1] if i + 1 < len(argv) else "claude"
    phases = sorted({int(a) for a in argv if a.isdigit()})
    results: dict[int, list[str]] = {}
    shown = sorted({0, 1, 2, 3}) if not phases else [0] + phases
    for phase in shown:
        print(f"\nPhase {phase}" + (" (setup)" if phase == 0 else ""))
        for p, fn in OFFLINE:
            if p == phase:
                results.setdefault(phase, []).append(run(fn.__name__.replace("_", " "), fn))
        if phase in phases and not no_live:
            if all(r == "pass" for r in results.get(phase, [])) and all(r == "pass" for r in results.get(0, [])):
                for p, fn in LIVE:
                    if p == phase:
                        print(f"  ...   {fn.__name__.replace('_', ' ')} (live)")
                        results[phase].append(run(fn.__name__.replace("_", " "), fn))
            else:
                print("  skip  live check: fix the lines above first")
    print()
    if any(r != "pass" for r in results.get(0, [])):
        print("❌ setup isn't ready: fix the Phase 0 lines above, then run python check.py again")
        return 1
    first_open = next((p for p in (1, 2, 3) if any(r != "pass" for r in results.get(p, []))), None)
    if first_open is not None:
        print(f"✅ setup ok · next: phase {first_open} of 3 · {NEXT[first_open]}")
    elif not phases:
        print(f"✅ setup ok · every offline check passes · next: phase 3 of 3 · {NEXT[3]}")
    elif max(phases) < 3:
        done = max(phases)
        print(f"✅ phase {done} of 3 passes · next: phase {done + 1} of 3 · {NEXT[done + 1]}")
    elif no_live:
        print("✅ phase 3 offline checks pass · drop --offline to run the 10 cases")
    else:
        print("✅ phase 3 of 3 passes · 10 of 10 cases · done!" if BACKEND == "claude" else
              "✅ the Lumen cases pass · same CLI, same guard, different brain")
    return 0 if first_open is None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
