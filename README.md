<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/ab-logo-white.png">
    <img src="assets/ab-logo-dark.png" alt="Agent Builders Philippines" width="320">
  </picture>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/lumen-logo-white.png">
    <img src="assets/lumen-logo-dark.png" alt="Lumen" width="150">
  </picture>
</p>

# Reviewer Agent: starter template

**Agent Builders PH · Episode 3.** Build a study reviewer that answers only from your notes, names its sources, and quizzes you. It runs on **Lumen AI Chat**: one assistant per subject holds the notes and the rules, and your Python code does the rest.

You'll write the Lumen AI Chat client **yourself**, in plain Python: open a session, send a question, and refuse any answer that cites nothing. Then Lumen writes a quiz, and Python checks it and grades it, so nothing depends on the model getting the format right.

📘 **Follow [MODULE.md](MODULE.md)**. It walks you through everything, from setup to all 10 test cases.

🧭 **Prefer a click-through checklist?** Open the **[walkthrough guide](https://claude.ai/artifact/TR1FqydJyPGugEDzrxRHrB)**. It has an interactive map of how the agent works, every step with copy buttons, and tick-boxes that remember your progress. A copy is also in this repo as [WALKTHROUGH.html](WALKTHROUGH.html). GitHub shows that file as source code, so open your local copy after cloning: `start WALKTHROUGH.html` (Windows) or `open WALKTHROUGH.html` (macOS).

🖥️ **Prefer a browser?** Run `python app.py` and open http://127.0.0.1:8766: the same agent on a yellow pad. Until your TODOs are done, it tells you which one to do next.

## Get started

```bash
uv venv --python 3.12
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
uv pip install -r requirements.txt

cp .env.example .env            # Windows: copy .env.example .env
python check.py                 # shows what's left to build
```

In `.env`, paste the Lumen AI Chat key, secret and three instance IDs the host sends you. That's the only key you need this episode.

## How this template works

The project structure is ready. The parts you build are marked **`TODO`**, numbered to match the module:

| TODO | File | Module section |
|---|---|---|
| 1 | `01_ask.py` → `lumen_headers` | §4 Phase 1: the two headers |
| 2 | `01_ask.py` → `open_session` | §4 open a session |
| 3 | `01_ask.py` → `send_message` | §4 send a question |
| 4 | `01_ask.py` → `answer_or_refuse` | §4 no source, no answer |
| 1 | `02_quiz.py` → `Question` | §5 Phase 2: the Quiz form |
| 2 | `02_quiz.py` → `parse_quiz` | §5 parse Lumen's reply |
| 3 | `02_quiz.py` → `is_correct` | §5 Python grades |
| none | `cases.json`, through `check.py` | §6 Phase 3: all 10 cases |

After each TODO, run the offline checks for that phase. They talk to a fake Lumen inside `check.py`: no credits, no cost:

```bash
python check.py 1 --offline     # PASS / FAIL (with a hint) / TODO
```

Drop `--offline` when a phase passes, and `check.py` asks the real Lumen instances (it says about how many credits). Behind by more than a phase? Copy the finished file from `solutions/` (MODULE §8).

When `python check.py 3` prints `10 of 10 cases pass`, you're done. 🎉

## Never commit secrets

`.env` is in `.gitignore`, and so is `quiz_log.csv`, your quiz history. Keep it that way, never paste a key in the group chat, and keep your own copy of this repo **private**.
