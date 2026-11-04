# Proje Hafızası · Project Memory

[![Validate](https://github.com/caglarhekimci/project-memory/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/caglarhekimci/project-memory/actions/workflows/ci.yml)
[![Docker validation](https://github.com/caglarhekimci/project-memory/actions/workflows/docker.yml/badge.svg?branch=main)](https://github.com/caglarhekimci/project-memory/actions/workflows/docker.yml)

**Return to a project with its decisions, sources and current checks in view.** A personal Turkish workspace with versioned knowledge, cited retrieval and commit-scoped GitHub status.

## The story

I work across multiple repositories. After a break I repeatedly reconstruct why a decision was made, what was implemented, and which test actually passed. An old GitHub failure email can make a fixed project look broken.

Project Memory keeps document revisions and personal notes, answers questions with source excerpts, and queries the current default-branch commit for fresh CI evidence. An architecture document describes intent; a CI run describes a particular commit. The interface keeps those kinds of evidence separate.

## Run locally

Install [uv](https://docs.astral.sh/uv/) and run from this checkout:

```powershell
uv sync --locked
uv run project-memory serve --demo
```

Open **http://127.0.0.1:4180**. The explicitly labelled demo password is `project-memory-demo`. Demo mode seeds recorded StockLedger and ProcureFlow examples; they are not live assertions. Source imports and the GitHub check button perform real read-only requests. Node.js is only needed for contributor checks, not the application.

With [Ollama](https://ollama.com/) running:

```powershell
ollama pull bge-m3
ollama pull qwen3.5:9b
uv run project-memory serve --demo --ollama
```

Choose a project → **Kaynaklar → Depodan güncelle** to index repository documents. New/edited notes are also embedded. Recorded demo seeds start with lexical excerpts; the interface warns when the current model has no indexed vectors. The application never downloads models automatically.

Both models ran locally on an RTX5070 with 12GB VRAM. This is evidence for that machine, not a minimum hardware guarantee. Other machines can use extractive mode; performance depends on hardware and context.

### Personal data

Copy `.env.example` to an ignored `.env`, set `PM_DEMO_MODE=false`, and supply your own `PM_APP_PASSWORD` (12+ characters). The demo password and `change-this…` placeholders are rejected in live mode. Start with `uv run project-memory serve`. SQLite lives in `data/` unless configured otherwise. Use a new database if you want no recorded demo sources.

Notes, source revisions, session digests and feedback remain in your configured database. Public GitHub imports need no token. An optional `PM_GITHUB_TOKEN` must have read access only and is never sent to a model. There are no paid model API calls in this implementation.

## Implemented

- Projects, public-repository connections, personal note creation/editing/deletion, durable storage and feedback.
- At most 12 selected Markdown files from README/docs, read at immutable commits. Prepare all content/embeddings before an atomic snapshot replacement.
- Immutable source history, active-revision retrieval and embedding-space refresh without creating a fictitious document revision.
- Turkish BM25 plus dense retrieval and reciprocal-rank fusion. SQLite computes cosine locally; PostgreSQL uses pgvector's cosine operator.
- Real Ollama BGE-M3 embeddings and Qwen generation, model-digest namespaces, bounded JSON claims and citation allowlisting. Short model-facing IDs map to stored chunk IDs.
- Explicit lexical/extractive fallback on model failure. Citation identity is validated; semantic truth still needs evaluation.
- Current-head reconciliation for configured workflow names. Missing/skipped/cancelled checks remain unknown; old failures cannot override current-head results.
- Owner authentication, hashed opaque sessions, rotation/revocation, same-origin writes, response/body limits and nonroot containers.
- Responsive Turkish UI, exact-revision links, keyboard dialogs and desktop/mobile accessibility tests.

## Docker

SQLite:

```sh
docker compose up --build -d --wait
```

PostgreSQL/pgvector:

```sh
docker compose -f compose.yaml -f compose.postgres.yaml up --build -d --wait
```

Both publish `127.0.0.1:4180` and preserve named volumes. PostgreSQL has no host port. Set `PM_DB_PASSWORD` for a personal live installation; its default is a disposable local-demo value. Do not run both configurations under one Compose project simultaneously. Host model access uses `host.docker.internal`; see the [runbook](docs/runbook.md).

## Architecture and evidence

- [Architecture and SOLID boundaries](docs/architecture.md)
- [Threat model](docs/threat-model.md)
- [Evaluation and recorded results](docs/evaluation.md)
- [Fine-tuning decision](docs/adr/0003-no-fine-tuning-without-measured-benefit.md)
- [Türkiye job-signal mapping](docs/job-signals.md)
- [Validation evidence](docs/validation.md)

The small fixed benchmark has 6 hand-authored documents and 15 questions. Lexical Recall@3 was **8/11**, calibrated hybrid Recall@3 **11/11**; all four unrelated questions returned no evidence. These numbers describe this fixture corpus, not arbitrary-repository accuracy.

## Contributor verification

```sh
uv sync --locked
npm ci
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
npm run check
npm run format:check
uv run pytest -m "not postgres" --cov=project_memory
uv run playwright install chromium
```

Set `RUN_BROWSER=1`, then run `uv run pytest tests/browser -q`. These tests use a real HTTP app and temporary SQLite. `BROWSER_BASE_URL` targets an existing disposable demo container. PostgreSQL contracts use `TEST_DATABASE_URL` and isolated, automatically removed `pm_test_<uuid>` schemas: `uv run pytest tests/test_memory.py -m postgres -v` against a test database you own.

```sh
uv run python scripts/evaluate.py --output test-results/lexical.json
uv run python scripts/calibrate.py
uv run python scripts/evaluate.py --models --generate --gate --output test-results/ollama.json
```

The last two require real local models. CI's deterministic/provider tests are distinct from the real-model experiment. CI also exercises both Docker storage modes, actual-container browser flows and persistence after container replacement.

## Scope

Single owner, one web worker. No deployment execution, shell tools, external messaging, production-readiness inference, private-repository ingestion or arbitrary remote URLs. No fine-tuned checkpoint, cross-encoder reranker, MCP server, OCR pipeline or multi-agent framework is claimed. Add them when a measured use case warrants the cost.
