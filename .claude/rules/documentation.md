# Documentation Rules

Good documentation lets a beginner set up, understand, and explain the project without help.

## 1. Where documentation lives

| File | Purpose | Update when... |
|------|---------|----------------|
| `README.md` | Install, run, API usage, structure | setup steps, API, or folders change |
| `CLAUDE.md` | One-page project overview | architecture or conventions change |
| `skills.md` | Step-by-step recipes | a common task changes |
| `docs/ARCHITECTURE.md` | Layers and request flow | modules are added or moved |
| `docs/PIPELINE.md` | STT → LLM → TTS internals | a model/provider or pipeline step changes |
| `docs/FRONTEND.md` | Hands-free web client | `client/` behaviour changes |
| `docs/CONFIGURATION.md` | Every env variable | a setting is added, removed, or changed |
| `docs/SECURITY.md` | Security measures | any protection changes |
| `docs/TESTING.md` | How to test | test layout or tooling changes |
| `docs/DECISIONS.md` | Why we chose X over Y | an important decision is made |
| `docs/PRESENTATION_GUIDE.md` | Demo script and Q&A | features change |
| `docs/TROUBLESHOOTING.md` | Known problems and fixes | a new problem is solved |
| `.claude/rules/*.md` | Rules for contributors | a convention changes |

## 2. Docs change with the code

- A change is not done until its docs are updated **in the same commit**.
- New setting → `app/config.py`, `.env.example`, **and** `docs/CONFIGURATION.md`.
- New error → `app/core/errors.py`, the error table in `README.md`, and a test.

## 3. Writing style

- Write for a beginner. Define jargon the first time you use it (e.g. "CORS: a browser rule that...").
- Short sentences. Use active voice: "The pipeline calls Groq", not "Groq is called by...".
- Prefer tables for reference information and numbered lists for steps.
- Every command is copy-pasteable and shown in a code block, with Windows variants
  where they differ (`copy` vs `cp`, `.venv\Scripts\activate`).
- Explain **why**, not only **what**. Decisions without reasons cannot be defended.

## 4. Code documentation

- Every module starts with a docstring describing its purpose and key decisions.
- Public functions have docstrings with `Raises:` when they raise errors.
- Comments explain intent and trade-offs, not syntax.
- The `/chat` route has `summary`, `description`, and `responses`, so `/docs` is useful on its own.

## 5. Decision records

Add a section to `docs/DECISIONS.md` for any choice a mentor might question:

```
## <Decision title>
**Decision:** what we chose.
**Alternatives:** what else we considered.
**Why:** the reasons.
**Trade-off:** what we gave up.
```

## 6. Accuracy

- Numbers in docs (test count, default limits, model names) must match the code.
- Check links when you rename or move files.
- Remove docs for features that no longer exist. Wrong docs are worse than none.

## 7. Diagrams

- Use plain-text (ASCII) diagrams in Markdown, so they show up everywhere and are easy to edit.
- Keep them small. One idea per diagram.

## 8. Markdown formatting

- One `#` title per file, then `##` sections.
- Use fenced code blocks with a language (```` ```bash ````, ```` ```python ````).
- Use relative links between docs (`[Pipeline](docs/PIPELINE.md)`).
