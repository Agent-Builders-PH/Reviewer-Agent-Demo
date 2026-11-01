"""Setup check and phase checks for the Reviewer Agent. Run it after every phase.

    python check.py              # setup (1 Lumen credit), plus the offline checks for every phase
    python check.py 1            # Phase 1: offline checks, then 2 live questions (about 13 credits)
    python check.py 2            # Phase 2: offline checks, then one live quiz (about 8 credits)
    python check.py 3            # Phase 3: offline checks, then all 10 cases (about 53 credits)
    python check.py 3 --offline  # skip the live part (no credits)

Each line says PASS, FAIL (with the one thing to fix) or TODO (not written yet).
The offline checks talk to a fake Lumen inside this file, so they cost nothing.
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


# ---------------------------------------------------------------- a fake Lumen (no network, no credits)

class FakeLumen:
    """Answers each request with the next (status, body) from a script, and records what was sent."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def handle(self, request):
        import httpx
        body = json.loads(request.content) if request.content else None
        self.calls.append(SimpleNamespace(method=request.method, path=request.url.path, json=body,
                                          headers=request.headers, params=dict(request.url.params)))
        if not self.script:
            raise AssertionError("one call too many: the fake Lumen ran out of answers")
        status, reply = self.script.pop(0)
        return httpx.Response(status, json=reply)

    def client(self):
        import httpx
        return httpx.Client(transport=httpx.MockTransport(self.handle))


def fake_env():
    import config
    # Import 01_ask.py with the REAL settings first. It copies LUMEN_API_KEY and
    # LUMEN_API_SECRET when it is imported; importing it while these fakes are in
    # place would keep the fake key for the rest of the run (live checks: 401).
    step("01_ask")
    return mock.patch.multiple(config, LUMEN_API_KEY="key-123", LUMEN_API_SECRET="secret-456",
                               LUMEN_INSTANCES={"bio": "inst-bio", "econ": "inst-econ", "ph-history": "inst-ph"})


def patched_ask():
    """01_ask.py imported the key and secret by name, so patch them there too."""
    s = step("01_ask")
    return mock.patch.multiple(s, LUMEN_API_KEY="key-123", LUMEN_API_SECRET="secret-456")


ANSWER = {"Answer": {"sessionID": "s1", "answer": "ATP is the cell's energy currency.",
                     "citations": ["bio-week5.pdf"], "degradedSources": []}}


def fake_answer(text="ATP is the cell's energy currency.", sources=("bio-week5.pdf",), degraded=()):
    from helpers import NotesAnswer, Source
    return NotesAnswer(text=text, sources=[Source(title=t) for t in sources], degraded=list(degraded))


SAMPLE_QUIZ = {"questions": [
    {"question": "What is ATP?", "a": "energy currency", "b": "a sugar", "c": "a membrane", "answer": "a", "source": "bio-week5.pdf", "why": "why-0"},
    {"question": "Where is glycolysis?", "a": "matrix", "b": "cytoplasm", "c": "cristae", "answer": "b", "source": "bio-week5.pdf", "why": "why-1"},
    {"question": "What are cristae?", "a": "DNA", "b": "fluid", "c": "membrane folds", "answer": "c", "source": "bio-week5.pdf", "why": "why-2"},
    {"question": "Which gas is used last?", "a": "oxygen", "b": "carbon dioxide", "c": "nitrogen", "answer": "A", "source": "bio-week5.pdf", "why": "why-3"},
    {"question": "Muscle fermentation makes?", "a": "ethanol", "b": "lactic acid", "c": "glucose", "answer": "b", "source": "bio-week5.pdf", "why": "why-4"},
]}


class ScriptedNotes:
    """Stands in for LumenNotes in the quiz checks: returns the next reply text, records each prompt."""

    subject = "bio"

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def send(self, prompt):
        self.prompts.append(prompt)
        return fake_answer(text=self.replies.pop(0))

    ask = send


class Exploding:
    """A backend that fails the test if anything calls it."""

    def ask(self, question):
        raise AssertionError("Lumen was called; long questions must be refused before any API call")


def drive_quiz(subject: str, answers: str, log: Path, notes):
    """Run the quiz loop with scripted letters. Returns (quiz, score, printed text, text seen before each answer)."""
    printed, seen = [], []

    def say(*parts):
        printed.append(" ".join(str(p) for p in parts))

    letters = iter(answers)

    def ask(prompt):
        seen.append("\n".join(printed))
        return next(letters)

    quiz, score = step("02_quiz").run_quiz(subject, notes, ask=ask, say=say, log=log)
    return quiz, score, "\n".join(printed), seen


def hidden_until_typed(quiz, seen) -> str | None:
    """None when no question's answer (its 'why' line) was printed before its letter was typed."""
    for i, q in enumerate(quiz.questions):
        before = seen[i] if i < len(seen) else ""
        if q.why and f"Why: {q.why}" in before:
            return f"Q{i + 1}'s answer was printed before a letter was typed"
    return None


def require_quiz_fields():
    if not {"answer", "source"} <= set(step("02_quiz").Question.model_fields):
        todo("this check needs TODO 1 (answer and source in Question) first")


# ---------------------------------------------------------------- Phase 0: setup

@offline(0)
def python_and_packages():
    assert sys.version_info >= (3, 11), f"Python {sys.version.split()[0]} is too old; use 3.11 or newer (3.12 recommended)"
    for pkg in ("httpx", "pydantic", "python-dotenv"):
        try:
            importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            raise AssertionError(f"{pkg} isn't installed. Activate .venv, then: uv pip install -r requirements.txt")
    print(f"      Python {sys.version.split()[0]}, httpx {importlib.metadata.version('httpx')}")


@offline(0)
def env_and_settings():
    assert (ROOT / ".env").exists(), "No .env yet. Run: copy .env.example .env, then paste what the host sent you"
    import config
    assert config.LUMEN_API_KEY and config.LUMEN_API_SECRET, \
        "paste the Lumen key and secret from the host after LUMEN_API_KEY= and LUMEN_API_SECRET= in .env"
    assert config.LUMEN_API_KEY != config.LUMEN_API_SECRET, "LUMEN_API_KEY and LUMEN_API_SECRET are the same; copy each one again"
    missing = [s for s, i in config.LUMEN_INSTANCES.items() if not i]
    assert not missing, "paste the instance IDs from the host in .env; missing: " + \
        ", ".join("LUMEN_INSTANCE_" + s.upper().replace("-", "_") for s in missing)
    for s in config.SUBJECTS:
        folder = config.subject_dir(s)
        assert folder.is_dir() and any(folder.iterdir()), f"notes/{s}/ is missing or empty"
    print(f"      key, secret and 3 instance IDs set; gateway {config.LUMEN_BASE_URL.split('//')[-1]}")


@offline(0)
def lumen_key_works():
    """1 credit: list the instances with this key (written here, so it works before TODO 1)."""
    import httpx
    import config
    from helpers import expect
    try:
        r = httpx.get(f"{config.AI_CHAT}/instances", timeout=35,
                      headers={"lumen-api-key": config.LUMEN_API_KEY, "lumen-api-secret": config.LUMEN_API_SECRET})
    except httpx.HTTPError as e:
        raise AssertionError(f"can't reach Lumen ({type(e).__name__}). Check your internet connection and LUMEN_BASE_URL")
    found = expect(r, 200).get("Instances") or []
    ids = {i.get("InstanceID") for i in found}
    wrong = [s for s, i in config.LUMEN_INSTANCES.items() if i not in ids]
    print(f"      this key can use {len(found)} instance(s) (1 credit)")
    assert found, "this key sees no AI Chat instances yet. Tell the host"
    assert not wrong, "not in this key's instances: " + ", ".join(wrong) + ". Copy those instance IDs again"


# ---------------------------------------------------------------- Phase 1: Ask (01_ask.py)

@offline(1)
def todo1_headers():
    with fake_env(), patched_ask():
        h = step("01_ask").lumen_headers()
    if not h:
        todo("TODO 1: return the two Lumen headers in lumen_headers()")
    assert h.get("lumen-api-key") == "key-123", 'add "lumen-api-key": LUMEN_API_KEY'
    assert h.get("lumen-api-secret") == "secret-456", 'add "lumen-api-secret": LUMEN_API_SECRET'
    assert len(h) == 2, "only the two lumen- headers"


@offline(1)
def todo2_open_session():
    lumen = FakeLumen((201, {"Session": {"id": "sess-9", "organizationID": "org"}}))
    with fake_env(), patched_ask():
        sid = step("01_ask").open_session(lumen.client(), "inst-bio", "Reviewer Agent - bio")
    assert lumen.calls, "open_session() should POST to /ai_chat/instances/{id}/sessions"
    c = lumen.calls[0]
    assert c.method == "POST", "opening a session is a POST"
    assert c.path.endswith("/ai_chat/instances/inst-bio/sessions"), f"wrong path: {c.path}"
    assert c.headers.get("lumen-api-key") == "key-123", "send headers=lumen_headers()"
    assert (c.json or {}).get("title"), 'send json={"title": title}'
    assert sid == "sess-9", 'return r.json()["Session"]["id"] (through expect(r, 201))'


@offline(1)
def todo3_send_message():
    lumen = FakeLumen((200, {"Answer": {"sessionID": "s1", "answer": "ATP is energy.",
                                        "citations": ["bio-week5.pdf", "Bio glossary"], "degradedSources": ["old-notes"]}}))
    with fake_env(), patched_ask():
        a = step("01_ask").send_message(lumen.client(), "inst-bio", "s1", "Ano ang ATP?")
    assert lumen.calls, "send_message() should POST the question"
    c = lumen.calls[0]
    assert c.method == "POST" and c.path.endswith("/ai_chat/instances/inst-bio/sessions/s1/messages"), f"wrong call: {c.method} {c.path}"
    assert c.json == {"message": "Ano ang ATP?"}, 'send json={"message": question}'
    assert a.text == "ATP is energy.", 'text comes from Answer["answer"]'
    assert [s.title for s in a.sources] == ["bio-week5.pdf", "Bio glossary"], 'one Source per string in Answer["citations"]'
    assert a.degraded == ["old-notes"], 'degraded comes from Answer["degradedSources"]'


@offline(1)
def todo3_handles_errors():
    from helpers import LumenError
    lumen = FakeLumen((403, {"error": {"code": "API_CREDITS_INSUFFICIENT", "message": "x"}}))
    with fake_env(), patched_ask():
        try:
            step("01_ask").send_message(lumen.client(), "inst-bio", "s1", "Ano?")
        except LumenError as e:
            assert "credits" in str(e)
            return
        except (KeyError, TypeError):
            pass
    raise AssertionError("use expect(r, 200) so a Lumen error becomes a clear message, not a KeyError")


@offline(1)
def todo4_no_source_no_answer():
    guard = step("01_ask").answer_or_refuse
    refusal = guard(fake_answer(text="ATP is energy.", sources=()), "bio")
    if not refusal.startswith("⚠️ Not in your bio notes"):
        todo("TODO 4: in answer_or_refuse, return the refusal when there are no sources")
    assert guard(fake_answer(text="Not in your notes."), "bio").startswith("⚠️ Not in your bio notes"), \
        "refuse when Lumen says Not in your notes, even if a source came back"
    ok = guard(fake_answer(), "bio")
    assert ok.startswith("📘") and "📎 bio-week5.pdf" in ok, "an answer with a source should print 📘 and 📎 lines"


@live(1)
def two_questions_on_lumen():
    from reviewer import ask_once
    notes = step("01_ask").LumenNotes("bio")
    first, a = ask_once(notes, "bio", "Ano ang ATP?")
    second, _ = ask_once(notes, "bio", "Sino si Rizal?")
    for reply in (first, second):
        for line in reply.splitlines()[:3]:
            print(f"      {line[:100]}")
    print("      (about 7 credits: 1 session, 1 question; no Bio notes match Rizal, so that one cost nothing)")
    assert a is not None and a.sources and not first.startswith("⚠️"), \
        "Lumen sent no citations, so your guard refused. Tell the host: the Bio instance may have no sources"
    assert second.startswith("⚠️ Not in your bio notes"), \
        "Lumen answered a question the notes don't cover. Tell the host: the instance needs instance_rules.md"


# ---------------------------------------------------------------- Phase 2: Quiz (02_quiz.py)

@offline(2)
def todo1_question_fields():
    fields = step("02_quiz").Question.model_fields
    if "answer" not in fields or "source" not in fields:
        todo('TODO 1: add answer: Literal["a", "b", "c"] and source: str to Question in 02_quiz.py')
    assert set(typing.get_args(fields["answer"].annotation)) == {"a", "b", "c"}, 'answer should be Literal["a", "b", "c"]'
    assert fields["source"].annotation is str, "source should be a str"


@offline(2)
def todo2_parse_quiz():
    s = step("02_quiz")
    require_quiz_fields()
    reply = "Here is your quiz:\n```json\n" + json.dumps(SAMPLE_QUIZ) + "\n```"
    try:
        quiz = s.parse_quiz(reply)
    except NotImplementedError:
        raise
    assert isinstance(quiz, s.Quiz), "parse_quiz() should return a Quiz"
    assert len(quiz.questions) == 5 and quiz.questions[3].answer == "a", "use Quiz.model_validate_json(extract_json(reply))"
    for bad in ("Not in your notes.", '{"questions": [{"question": "x"}]}'):
        try:
            s.parse_quiz(bad)
        except ValueError:
            continue
        raise AssertionError(f"parse_quiz({bad[:30]!r}) should raise, not return a quiz")


@offline(2)
def todo3_python_grades():
    s = step("02_quiz")
    require_quiz_fields()
    q = s.Quiz.model_validate(SAMPLE_QUIZ).questions[0]  # the right answer is a
    assert s.is_correct("a", q) is True, "is_correct('a', q) should be True when q.answer is 'a'"
    assert s.is_correct(" A ", q) is True, "ignore spaces and capitals: compare letter.strip().lower()"
    assert s.is_correct("b", q) is False, "is_correct('b', q) should be False when q.answer is 'a'"


@offline(2)
def quiz_loop_retries_hides_answers_and_logs():
    s = step("02_quiz")
    require_quiz_fields()
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "quiz_log.csv"
        notes = ScriptedNotes("Sorry, here goes: not json", json.dumps(SAMPLE_QUIZ))
        quiz, score, printed, seen = drive_quiz("bio", "aaaaa", log, notes)
        assert len(notes.prompts) == 2, "a reply that isn't a Quiz should be asked for once more"
        assert score == 2, f"answering a,a,a,a,a should score 2/5; got {score}"
        problem = hidden_until_typed(quiz, seen)
        assert problem is None, problem
        rows = log.read_text(encoding="utf-8").splitlines()
        assert len(rows) == 2 and rows[1].split(",")[2] == "2/5", "one row should be added to quiz_log.csv"
        assert s.last_missed("bio", log)[0] == "Where is glycolysis?", "the next quiz should start with the missed questions"
        again = ScriptedNotes(json.dumps(SAMPLE_QUIZ))
        drive_quiz("bio", "abcab", log, again)
        assert "Where is glycolysis?" in again.prompts[0], "the next quiz prompt should list the missed questions"


@live(2)
def one_real_quiz():
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "quiz_log.csv"
        quiz, score, printed, seen = drive_quiz("bio", "abcab", log, step("01_ask").LumenNotes("bio"))
        for i, q in enumerate(quiz.questions, 1):
            print(f"      Q{i} [{q.answer}] {q.question[:70]}  ({q.source[:30]})")
        print(f"      score {score}/5 (scripted letters) · about 7 credits")
        problem = hidden_until_typed(quiz, seen)
        assert problem is None, problem


# ---------------------------------------------------------------- Phase 3: the session, the router, the 10 cases

@offline(3)
def long_questions_refused_before_any_call():
    from reviewer import ask_once
    reply, answer = ask_once(Exploding(), "bio", "Ano ang ATP? " * 350)
    assert answer is None and reply.startswith("⚠️ Question too long"), "a 4,500-character question should be refused"


@offline(3)
def router_sends_quiz_me_to_the_quiz():
    import reviewer
    quizzes, asked = [], []
    notes = SimpleNamespace(ask=lambda q: asked.append(q) or fake_answer(), transcript=lambda: [])
    with mock.patch.object(reviewer, "make_notes", lambda subject: notes), \
         mock.patch.object(step("02_quiz"), "run_quiz", lambda subject, n=None: quizzes.append(subject)), \
         mock.patch("builtins.input", side_effect=["Quiz me please", "Ano ang ATP?", "exit"]), \
         mock.patch("builtins.print"):
        reviewer.chat("bio")
    assert quizzes == ["bio"], '"quiz me" should run the quiz'
    assert asked == ["Ano ang ATP?"], "anything else should go to notes.ask()"


@offline(3)
def session_reopens_and_retries():
    from helpers import ReviewerError
    s = step("01_ask")
    with fake_env(), patched_ask(), mock.patch.object(s, "instance_for", lambda subject: "inst-bio"):
        # a lost session is reopened once
        lumen = FakeLumen((201, {"Session": {"id": "s1"}}), (403, {"error": {"code": "SESSION_NOT_OWNED"}}),
                          (201, {"Session": {"id": "s2"}}), (200, ANSWER))
        a = s.LumenNotes("bio", http=lumen.client(), pause=0).ask("Ano ang ATP?")
        assert a.text.startswith("ATP") and lumen.calls[-1].path.endswith("/sessions/s2/messages")
        # a timeout (504, not charged) is retried once, in the same session
        lumen = FakeLumen((201, {"Session": {"id": "s1"}}), (504, {"error": {"code": "AI_CHAT_REPLY_TIMEOUT"}}), (200, ANSWER))
        notes = s.LumenNotes("bio", http=lumen.client(), pause=0)
        notes.send("hello")
        assert len(lumen.calls) == 3
        # the next message reuses the session: no new session, 1 call
        lumen.script.append((200, ANSWER))
        notes.send("hello again")
        assert len(lumen.calls) == 4 and lumen.calls[-1].path.endswith("/sessions/s1/messages"), "reuse the open session"
        # out of credits is not retried, and says so plainly
        lumen = FakeLumen((201, {"Session": {"id": "s1"}}), (403, {"error": {"code": "API_CREDITS_INSUFFICIENT"}}))
        try:
            s.LumenNotes("bio", http=lumen.client(), pause=0).send("hello")
            raise AssertionError("out of credits should raise")
        except ReviewerError as e:
            assert "credits" in str(e) and len(lumen.calls) == 2


@offline(3)
def notes_travel_with_the_question():
    """Python picks the matching notes, keeps the message under 2,000 characters, and checks the sources."""
    import notes as notes_py
    s = step("01_ask")

    def reply(text):
        return (200, {"Answer": {"sessionID": "s1", "answer": text, "citations": [], "degradedSources": []}})

    with fake_env(), patched_ask(), mock.patch.object(s, "instance_for", lambda subject: "inst-bio"):
        lumen = FakeLumen((201, {"Session": {"id": "s1"}}),
                          reply("ATP is the cell's energy currency.\nSource: bio-week5.pdf, p.1"),
                          reply("ATP powers everything. Source: made-up-notes.pdf, p.9"))
        n = s.LumenNotes("bio", http=lumen.client(), pause=0)
        a = n.ask("Ano ang ATP?")
        sent = lumen.calls[-1].json["message"]
        assert "[bio-week5.pdf p.1]" in sent and sent.rstrip().endswith("Question: Ano ang ATP?"), \
            "the message should carry the labeled notes, the rules, then the question"
        assert len(sent) <= notes_py.MAX_MESSAGE, f"the message is {len(sent)} characters; Lumen's limit is 2,000"
        assert [(x.title, x.page) for x in a.sources] == [("bio-week5.pdf", 1)] and "Source" not in a.text, \
            "the Source line should become a source, and leave the answer text"
        b = n.ask("Ano ang ATP? Paki-explain.")
        assert not b.sources, "a source that names notes we never sent must not count"
        calls = len(lumen.calls)
        c = n.ask("Sino si Rizal?")
        assert len(lumen.calls) == calls and c.text == "Not in your notes.", \
            "nothing in the Bio notes matches Rizal: refuse without calling Lumen"


def run_case(case: dict, sessions: dict, log: Path):
    """Run one case on Lumen. Returns (problem or None, text to show)."""
    from reviewer import ask_once
    subject, kind = case["subject"], case["check"]
    if subject not in sessions:
        sessions[subject] = step("01_ask").LumenNotes(subject)
    notes = sessions[subject]

    if kind in ("quiz", "quiz_no_key"):
        quiz, score, printed, seen = drive_quiz(subject, "abcab", log, notes)
        problem = hidden_until_typed(quiz, seen)
        if problem is None and kind == "quiz_no_key" and "answer key" in seen[0].lower():
            problem = "an answer key was printed"
        return problem, f"{len(quiz.questions)} questions, score {score}/5"

    if kind == "too_long":
        text = (case["input"] * (case["repeat_to"] // len(case["input"]) + 1))[:case["repeat_to"]]
        reply, _ = ask_once(Exploding(), subject, text)
        return (None if reply.startswith("⚠️ Question too long") else "not refused"), reply

    reply, a = ask_once(notes, subject, case["input"])
    text = (a.text if a else "").lower()
    if kind == "refusal":
        return (None if reply.startswith(f"⚠️ Not in your {subject} notes") else "should refuse: the notes don't cover this"), reply
    if reply.startswith("⚠️"):
        return "no source came back, so the guard refused", reply
    problem = None
    if kind == "disagree" and not ("23" in text and "26" in text and "disagree" in text):
        problem = 'should give both dates (23 and 26) and say the handouts "disagree"'
    elif kind == "names_injection" and "answer key" not in text:
        problem = "should describe the answer-key line as text in the notes"
    elif kind == "says":
        if not all(w in text for w in case["words"]) or (case["any"] and not any(w in text for w in case["any"])):
            problem = f"expected the answer to mention {case['words'] + case['any'][:3]}"
    elif kind == "transcript":
        stored = notes.transcript()
        said = [str(m.get("content", "")) for m in stored]
        if not any(case["input"] in m for m in said) or not any(m.get("role") == "assistant" for m in stored):
            problem = "the transcript should hold the question and Lumen's answer"
        reply += f"\n(transcript: {len(stored)} messages)"
    return problem, reply


@live(3)
def all_cases_pass():
    cases = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
    sessions, passed = {}, 0
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "quiz_log.csv"
        for case in cases:
            try:
                problem, shown = run_case(case, sessions, log)
            except Exception as e:  # one broken case shouldn't hide the others
                problem, shown = f"{type(e).__name__}: {e}", ""
            passed += problem is None
            mark = "PASS" if problem is None else "FAIL"
            print(f"      {mark} #{case['id']:<2} {case['subject']:<10} {case['pass_when'][:58]}")
            if case["id"] <= 5 or problem:
                for line in str(shown).splitlines()[:5]:
                    print(f"             {line[:100]}")
            if problem:
                print(f"             -> {problem}")
    print(f"      {passed} of {len(cases)} cases pass (about 52 credits)")
    assert passed == len(cases), f"{len(cases) - passed} case(s) failed; see the FAIL lines above"


# ---------------------------------------------------------------- runner

NEXT = {
    1: "open 01_ask.py and start at TODO 1",
    2: "open 02_quiz.py and start at TODO 1",
    3: "python check.py 3 runs all 10 cases",
}


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
    no_live = "--offline" in argv
    phases = sorted({int(a) for a in argv if a.isdigit()})
    results: dict[int, list[str]] = {}
    shown = [0, 1, 2, 3] if not phases else [0] + phases
    for phase in shown:
        print(f"\nPhase {phase}" + (" (setup)" if phase == 0 else ""))
        for p, fn in OFFLINE:
            if p != phase:
                continue
            if fn is lumen_key_works and (no_live or any(r != "pass" for r in results.get(0, []))):
                print("  skip  lumen key works: fix the lines above first" if not no_live else "  skip  lumen key works (--offline)")
                continue
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
        print("✅ phase 3 of 3 passes · 10 of 10 cases · done!")
    return 0 if first_open is None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
