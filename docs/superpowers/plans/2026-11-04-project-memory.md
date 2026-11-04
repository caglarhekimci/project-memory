# Project Memory Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. The user delegated decisions and execution; do not add approval gates. One independent whole-branch review at the end.

**Goal:** A usable personal assistant that retrieves versioned project knowledge and reconciles live GitHub checks with cited evidence.

**Architecture:** Domain objects and ports are independent of HTTP, persistence and model APIs. SQLAlchemy adapters support SQLite and PostgreSQL/pgvector. A bounded application pipeline retrieves evidence, validates generated citations and exposes deterministic current-head CI facts.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy, PostgreSQL/pgvector or SQLite, httpx, Ollama, Jinja2, vanilla CSS/JS, pytest, Playwright, Docker, GitHub Actions, uv lock.

**Spec:** `docs/superpowers/specs/2026-11-04-project-memory-design.md`

## Global Constraints

- Single owner; all retrieval is project-scoped. No autonomous external writes.
- Imported sources are data, never instructions. Unknown citations fail closed.
- GitHub requests use a fixed origin and exact immutable commit refs.
- Fine-tuning requires measured benefit and held-out evaluation; no invented training evidence.
- Demo, offline tests, real local models, remote Docker and production are distinct evidence.

## Review Focus

- New document revisions and deleted files must not leave stale active chunks.
- A skipped/missing workflow or old failure must not become current-head success.
- Source content, paths and provider errors must not create script injection or token leaks.
- Embedding space changes must not mix incompatible vectors.
- Concurrent imports, expired sessions and database restart must preserve integrity.

## Task 1: Versioned memory and retrieval

Files: `src/project_memory/domain/`, `adapters/store.py`, `application/retrieval.py`, `application/ingestion.py`; `tests/test_memory.py`, `tests/test_retrieval.py`.
Interfaces: `MemoryStore` persists project-scoped source revisions, chunks, sessions, feedback; `Embedder` defines its embedding space. `Retriever.search(project_id, question, limit)` returns scored cited evidence.

- [ ] Write and run failing tests for immutable revisions/idempotency, inactive old chunks, isolation, source deletion, durable restart, lexical matching and hybrid ranking.
- [ ] Implement domain objects/ports, SQLAlchemy store, bounded markdown chunking and BM25/RRF retrieval.
- [ ] Run SQLite suite and record results; run same storage contracts on PostgreSQL in CI.
- [ ] Commit.

## Task 2: Public GitHub and model orchestration

Files: `adapters/github.py`, `adapters/ollama.py`, `application/answers.py`, `application/checks.py`; provider contract and answer tests.
Interfaces: GitHub adapter returns immutable repository documents and `CheckSnapshot`; generator returns cited claims validated against retrieved chunk identifiers.

- [ ] Write and run failing tests for exact-head check reconciliation, missing workflows, upstream failures, safe paths, response limits, invalid citations and unavailable models.
- [ ] Implement fixed-origin HTTP adapters, import workflow, local embedding/generation, bounded cited answers and extractive fallback.
- [ ] Run unit/provider tests; commit.

## Task 3: Authenticated usable workspace

Files: `web/`, `settings.py`, `bootstrap.py`, `cli.py`; API and browser tests.
Interfaces: JSON endpoints under `/api`; opaque session cookie; server-rendered shell plus static client. Explicit demo seed and model mode.

- [ ] Write and run failing API tests for auth, origin validation, project/note/search/answer/feedback flows and invalid inputs.
- [ ] Implement composition, auth, API, responsive Turkish workspace and CLI.
- [ ] Run real HTTP/browser flows, mobile and source-injection checks; commit.

## Task 4: Evaluation and delivery

Files: `evals/`, `scripts/`, `Dockerfile`, `compose.yaml`, `.github/workflows/`, `docs/`.

- [ ] Define held-out retrieval/abstention/current-head scenarios and pass gates before running experiments.
- [ ] Run reproducible offline evaluation and real local Ollama verification; publish only non-sensitive fixtures and measured results.
- [ ] Add nonroot image, persistent volume, PostgreSQL profile, repeatable Docker smoke and CI.
- [ ] Run lint/type checks/tests/security scan, browser tests and independent whole-branch review. Fix material findings with regression tests.
- [ ] Create public repository, push, observe CI/Docker result, fix failures, and verify public default branch matches the delivered commit.
