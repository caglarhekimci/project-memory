# Validation evidence

## Local

Windows / CPython3.12.14, real SQLite-backed unit/API/provider tests, actual HTTP browser application, Ruff, mypy and JS syntax/format checks. Core suite: 61 passing tests, approximately 89.6% Python coverage. Browser checks run separately and include Chromium desktop/mobile flows, source injection rendering and axe WCAG A/AA scans for tested states. Final counts/run links are recorded after delivery checks below.

## Real models

Ollama BGE-M3 embeddings and Qwen3.5:9b generation ran on the local RTX5070. See [evaluation](evaluation.md) and raw JSON evidence. This is actual local inference, not fine-tuning or a production accuracy claim.

## Remote Docker/PostgreSQL

The Windows machine has no Docker executable. Delivered workflows exercise actual Linux containers for SQLite/PostgreSQL, nonroot identity, browser/accessibility flows and note/session persistence after replacement. PostgreSQL contracts use real vector storage/distance in owned disposable schemas. Remote results will be linked after workflows finish; local Docker execution is not claimed.
