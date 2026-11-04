# Validation evidence

## Local

Windows / CPython3.12.14, real SQLite-backed unit/API/provider tests, actual HTTP browser application, Ruff, mypy and JS syntax/format checks. Final core suite: **63 passing tests, 90.53% Python coverage**. Browser suite: **8 passing cases**, including Chromium desktop/mobile flows, source injection rendering, mobile logout and axe WCAG A/AA scans for tested states. Python runtime pip-audit strict and npm audit reported no known vulnerabilities.

One independent read-only whole-branch review identified out-of-order concurrent sync and an inaccurate hybrid label. Both received failing regression tests and were fixed before publication. The complete affected/core/browser suites then passed. The reviewer did not independently rerun model or Docker experiments; those have separate evidence.

## Real models

Ollama BGE-M3 embeddings and Qwen3.5:9b generation ran on the local RTX5070. See [evaluation](evaluation.md) and raw JSON evidence. This is actual local inference, not fine-tuning or a production accuracy claim.

An additional real HTTP/browser flow imported **10 Markdown documents at one immutable StockLedger commit**, produced an actual hybrid/LLM answer, and retrieved current-head results for both StockLedger and ProcureFlow. Screenshots come from that running application. [Recorded live integration](evidence/live-integration.json). The temporary Windows server and database were cleaned up successfully after the final run.

## Remote Docker/PostgreSQL

The Windows machine has no Docker executable. Workflows exercise actual Linux containers for SQLite/PostgreSQL, nonroot identity, browser/accessibility flows and note/session persistence after replacement. PostgreSQL contracts use real vector storage/distance in owned disposable schemas. The live [Validate results](https://github.com/caglarhekimci/project-memory/actions/workflows/ci.yml) and [Docker results](https://github.com/caglarhekimci/project-memory/actions/workflows/docker.yml) are the source of truth for each pushed SHA. Local Docker execution is not claimed.
