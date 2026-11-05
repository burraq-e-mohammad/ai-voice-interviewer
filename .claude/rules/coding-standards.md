# Coding Standards

These rules keep the code readable for beginners and consistent across files.
They are enforced by **ruff** (lint and format) and **mypy** (types), configured in `pyproject.toml`.

## 1. Clarity over cleverness

- Write code that a beginner can read top to bottom and understand.
- Prefer a plain `for` loop over a dense one-liner if the loop is easier to read.
- No metaprogramming, decorators-of-decorators, or "magic" unless it is clearly needed.
- One function does one thing. If a function needs the word "and" to describe it, split it.

## 2. Naming

- `snake_case` for variables, functions and modules; `PascalCase` for classes;
  `UPPER_CASE` for constants (e.g. `ALLOWED_AUDIO_TYPES`).
- Names describe meaning, not type: `audio_bytes`, not `data2`; `reply_text`, not `s`.
- Private attributes start with `_` (e.g. `self._model`) so it is clear they are internal.
- Booleans read like questions: `enable_docs`, `is_valid`.

## 3. Type hints (required)

- Every function has type hints for all parameters and its return value
  (mypy enforces this with `disallow_untyped_defs`).
- Use modern syntax: `str | None`, `list[Message]` (not `Optional`, `List`).
- Use `Any` only where something can be a real object *or* a test fake, and add a comment saying why.
- Use `Protocol` to describe "anything with method X" (see `app/services/pipeline.py`).

## 4. Comments and docstrings

- Comments explain **why**, not what. Bad: `# add 1`. Good: `# +1 so we can detect oversize files`.
- Every module starts with a docstring explaining its purpose and key decisions.
- Public functions have a docstring. If they raise errors, list them under `Raises:`.
- Do not leave commented-out code. Git remembers old versions.

## 5. Formatting

- Line length: 100 characters.
- Run `ruff format .` before committing. Never argue about formatting by hand.
- Imports are sorted automatically (`ruff check --fix .`): standard library, then
  third-party, then `app.*`.

## 6. Error handling

- Raise a specific `VoiceBotError` subclass from `app/core/errors.py`, never a bare `Exception`.
- Catch third-party exceptions at the service boundary and re-raise them as our own errors,
  with `raise ... from exc` so the original cause stays in the logs.
- Never silently swallow an exception (`except: pass` is forbidden).
- User-facing messages are friendly and contain no internal details.

## 7. Functions and classes

- Keep functions short (aim for under 30 lines).
- Pass dependencies in through `__init__` (dependency injection) instead of creating them
  inside methods. This is what makes testing with fakes possible.
- Heavy imports (`faster_whisper`, `piper`, `groq`) go inside the constructor, so tests
  that use fakes do not pay their import cost.

## 8. Logging

- Use `logger = logging.getLogger(__name__)` per module. Never use `print()` in `app/`.
- Use `%s` placeholders (`logger.info("x=%s", x)`), not f-strings, in log calls.
- Log sizes and timings, never secrets or user speech content.

## 9. Before every commit

```bash
ruff format . && ruff check . && mypy app && pytest
```
All four must pass.
