# Project Memory design

The user chose Project Memory, delegated architecture and technology choices, and explicitly authorized development, testing and a public GitHub push. Execute without further design or publication approval. New standalone repository on `feat/project-memory`; existing projects remain untouched.

## Product story

I return to multiple repositories and repeatedly reconstruct decisions and current status. Old failure emails can be mistaken for current failures. I need answers with source revisions, timestamps, and explicit uncertainty. Start with StockLedger and ProcureFlow, then allow additional public repositories and personal notes.

## Architecture

Python 3.12+, FastAPI, Pydantic, SQLAlchemy. SQLite is the portable personal default; PostgreSQL/pgvector is the container profile and runs the same repository contract tests. A modular monolith separates domain, application orchestration, adapters, and HTTP/UI composition. No runtime shell commands and no autonomous write tools.

Immutable document revisions and chunks carry project, source URL, commit/content hash, observed time and active status. Repeated imports are idempotent; a new revision replaces the active revision atomically. Project-scoped lexical BM25 and dense retrieval combine with reciprocal-rank fusion. Ollama BGE-M3 supplies real multilingual embeddings; the installed Qwen model supplies schema-validated cited claims. An explicit extractive mode works without a model and never claims generated or semantic results. An unavailable configured model produces a visible fallback/warning.

Live CI data uses a fixed GitHub API origin, validated repository identities, configured workflow names and the current default-branch commit. Missing checks are unknown; in-progress checks are pending; historical failures cannot override current-head results. Live status is deterministic application data, separate from generated document summaries. No claim about production deployment follows from CI success.

## Boundaries and safety

Single owner, project-scoped knowledge. Password required outside explicit demo mode; hashed opaque eight-hour sessions with revocation. Same-origin mutation checks, bounded bodies, bounded upstream responses, request timeouts, no open CORS, CSP, no untrusted HTML rendering. Imported content is data, never instructions or authorization. Only public GitHub imports, read-only API, no arbitrary URLs or local filesystem imports. Personal notes can be deleted, removing stored chunks. Secrets and runtime databases are ignored by git and omitted from images. Demo samples are labelled as recorded examples.

## User experience

Turkish responsive workspace: project switcher, cited question/answer panel, source revisions, note creation/deletion, repository sync, current checks and query feedback. Clearly show demo/live, lexical/semantic and extractive/LLM mode. Sources link to exact GitHub revisions; the answer displays excerpt citations and caveats. Keyboard-accessible controls, readable mobile layout, reduced motion.

## Alternatives

PostgreSQL-only would block easy Windows use where Docker is absent; support SQLite as the default with a PostgreSQL adapter. A CI dashboard alone would not justify an LLM, so deterministic CI reconciliation complements document RAG. A large multi-agent framework and GPU server add no demonstrated first-version value. Provider ports allow future replacement; no framework dependency is required to implement bounded orchestration.

## Fine-tuning decision

Do not train by default. First measure a lexical baseline, hybrid retrieval, cited generation, unanswerable questions, and historical/current CI reconciliation. Add tuning only for a measured, repeatable deficiency with reviewed training data and a separate held-out evaluation set. No such dataset exists at project start. Record this decision and the experiment results honestly.

## Acceptance

- End-to-end project creation, note import/update, source display, search, answers, feedback and deletion with durable storage.
- Correct current-head reconciliation for successful, failed, pending, missing and unavailable checks.
- Real SQLite and PostgreSQL/pgvector contract verification; local real Ollama embeddings/generation verification, separately labelled from deterministic tests.
- Regression tests for project isolation, stale revisions, invalid citations, hostile source instructions, missing evidence, upstream failures, session expiry/revocation and origin/body limits.
- Browser tests for primary flows, mobile layout and basic accessibility; Docker build/start/restart/persistence check on Linux CI.
- Reproducible evaluation dataset and results, architecture decisions, threat model, runbook, job-signal mapping, public repository and successful CI for the delivered commit.
