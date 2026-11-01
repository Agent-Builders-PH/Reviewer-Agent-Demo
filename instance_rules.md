# Setting up each Lumen AI Chat instance

Your code sends the notes and the rules with every question (see `notes.py`), so each instance needs only two settings. The host sets them once per instance (Bio, Econ, PH History) in the Lumen Organization Portal:

**Lumen Assistant → the instance's ⋮ menu → Edit persona**, then fill in the two fields below and click **Save Changes**.

## 1. Persona

Copy everything inside the box. It's the same text for all three instances:

```text
You are a study reviewer for students. Each message contains excerpts from the student's own study notes, labeled with the file name and page, followed by a question or a request for a practice quiz. Answer only from the notes in the message, and follow the format the message asks for.
```

## 2. Out-of-scope Reply

```text
Not in your notes.
```

## Why these two

| Setting | Why |
|---|---|
| Persona | Every message passes the instance's scope check first, and the check compares it with the persona. A persona like "a Reviewer Agent for Biology" blocks messages that carry notes and instructions. This one says that's exactly what messages will contain |
| Out-of-scope Reply | When a message doesn't fit, Lumen answers with this text. `answer_or_refuse()` refuses any answer without a source anyway, so this only makes the wording match |

The rules themselves (answer only from the notes, say when two notes disagree, name the source) travel in every message: `ASK_RULES` in `notes.py` and `QUIZ_PROMPT` in `02_quiz.py`.
