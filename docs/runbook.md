# Runbook

## Configuration

Start from the checkout root. Default origin is `http://127.0.0.1:4180`; if changing the port, update `PM_ORIGIN` too. `localhost` and `127.0.0.1` are different origins. CLI binds loopback by default. Containers listen internally on all interfaces but publish loopback only.

For personal data, disable demo mode, set a unique password and use an empty personal database. Switching modes does not silently delete recorded demo sources. Create a new database or explicitly remove sources for a clean workspace.

## Models

Ollama must already run and contain the configured models. Set `PM_MODEL_BACKEND=ollama` or use `--ollama`, then sync sources/add notes to generate vectors. Re-sync after replacing the embedding model; old digest vectors are excluded. Model download/start is never automatic.

Default BGE-M3 threshold 0.4 was calibrated on the published development split. Calibrate for other models/corpora. Extractive mode works without Ollama. Generation failures visibly fall back to excerpts; sync embedding failures preserve the prior snapshot.

Host Ollama must be reachable from Docker. Linux's loopback binding may need host-network configuration; extractive containers require no model server. Do not expose an unauthenticated model endpoint publicly.

## GitHub

Enter `owner/repository` and expected workflow display names (such as `CI`, `Docker validation`). Sync selects at most 12 README/docs Markdown files; it does not clone code, read local paths or ingest private repos. A truncated tree fails before data mutation. Selection scope appears after sync.

Unauthenticated public requests have rate limits. An optional read token belongs only in ignored configuration. 403/429 errors surface as upstream failures. A displayed status applies to its observed SHA/time; refresh for current evidence.

## Backup

SQLite: stop the app or use SQLite's backup API, then copy `data/memory.db` and protect the backup. For Docker, stop this app and copy its database from the named volume. Restore while stopped, preserve UID10001 ownership and verify known sources after restart.

PostgreSQL: use `pg_dump`/`pg_restore`, include the vector extension, and test restore in a disposable owned database. Test contracts create/drop only their `pm_test_<uuid>` schemas. `docker compose stop` preserves volumes; `down -v` deletes this project's data and is used only for disposable CI.

## Diagnose

- 403: use the exact configured origin and verify proxy/HTTPS configuration.
- 401: log in; sessions expire after eight hours and logout revokes the active session.
- 429: login failures wait one minute; at most two heavy operations run concurrently.
- No semantic evidence: current digest lacks indexed chunks or relevance is below threshold. Sync/edit sources.
- Unknown GitHub state: inspect expected names, missing runs and the observed SHA.
- Empty answer: add supporting information and inspect retrieval; a larger model cannot supply missing project evidence.

Limits: one owner/worker, 20 UI-created projects, 200 active UI-created sources/project, 100,000 characters/source, 1,000 characters/question. These are personal-use bounds, not enterprise scalability claims. No background notifications, automatic deployment or schema upgrade system is enabled.
