<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/ab-logo-white.png">
    <img src="assets/ab-logo-dark.png" alt="Agent Builders Philippines" width="300">
  </picture>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/lumen-logo-white.png">
    <img src="assets/lumen-logo-dark.png" alt="Lumen" width="150">
  </picture>
</p>

# Reviewer Agent: build-along template

**Agent Builders PH · Episode 3 · Fri, Nov 20, 2026.** A study reviewer that answers **only from your notes**, names its sources, and quizzes you. It runs on **Lumen AI Chat**: you write the API calls in plain Python, a guard that refuses any answer without a source, and a checker that turns Lumen's quiz into something Python can grade.

```
python reviewer.py ask "Ano ang ATP?" --subject bio

📘 ATP is adenosine triphosphate, the molecule cells use to store and spend energy...
📎 bio-week5.pdf
```

You build it in the session by filling in **seven `TODO`s** in two files.

📘 **Follow [MODULE.md](MODULE.md)**, the step-by-step module.

## Setup in five commands (Windows PowerShell)

```powershell
uv venv --python 3.12
.venv\Scripts\activate
uv pip install -r requirements.txt
copy .env.example .env          # then paste the Lumen key, secret and 3 instance IDs from the host
python check.py
```

macOS / Linux: `source .venv/bin/activate` and `cp .env.example .env`. No uv? `python -m venv .venv` and `pip install -r requirements.txt` work too.

You need Python 3.11 or newer (3.12 recommended), [uv](https://docs.astral.sh/uv/), and the Lumen AI Chat key, secret and three instance IDs the host sends you. No other API key. `check.py` should end with `✅ setup ok · next: phase 1 of 3`.

## The three phases

| Phase | File you edit | TODOs | Check |
|---|---|---|---|
| 1. Ask | `01_ask.py` | 1 to 4: headers, open a session, send a message, the guard | `python check.py 1` |
| 2. Quiz | `02_quiz.py` | 1 to 3: the Quiz form, parse Lumen's JSON, Python grades | `python check.py 2` |
| 3. Test | nothing new | run all 10 cases in `cases.json` | `python check.py 3` |

`check.py` prints **PASS**, **FAIL** (with the one thing to fix) or **TODO** (not written yet). The offline checks use a fake Lumen, so they cost nothing; each live check says about how many credits it uses.

**Prefer clicking?** Run `python app.py` and open http://127.0.0.1:8766. You get the same agent in your browser: ask on a yellow pad, take a quiz, or read what Lumen stored. Until you finish the TODOs, it tells you which one to do next.

**Behind?** Copy the matching file from `solutions/` and keep going: `copy solutions\01_ask.py 01_ask.py`.

**Two rules for the room:** nobody pastes an API key into the group chat, and nobody loads notes that aren't theirs.
