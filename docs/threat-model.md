# Threat model and data handling

| Boundary | Control | Remaining limitation |
| --- | --- | --- |
| Owner session | Eight-hour opaque cookie, SHA-256 digest at rest, rotation and revocation | A stolen cookie works until revoked/expired |
| Cross-site writes | Exact configured Origin, SameSite=Strict, no CORS | Same-origin compromise remains dangerous |
| Parsing/concurrency | 256KiB ASGI limit before JSON parsing, bounded fields, two heavy operations | Throttling/quotas are process-local |
| Source import | Public GitHub only, validated repo, fixed API origin, immutable refs | Public content can be hostile or false |
| Model context | Untrusted excerpts; no tools, credentials or executable instructions | Prompting/citations cannot guarantee truth |
| Browser output | textContent/Jinja escaping, safe GitHub links, CSP | A future Markdown renderer needs sanitization review |
| Model output | JSON schema, finite vector/count checks, digest spaces, citation allowlist | Quality varies by model/corpus |
| Upstream | Timeouts, response limits, safe public errors, visible fallback | Public GitHub quotas can interrupt sync |
| Storage | Project-scoped queries, atomic revision replacement, cascading deletion | Single owner; no enterprise multi-tenant claim |
| Runtime | UID10001, read-only root, dropped capabilities, loopback publication | Public hosting needs HTTPS and operational hardening |

Notes/documents remain in the configured database. Deleting a source physically removes its versions/chunks; existing backups can retain earlier data. Feedback stores only answer ID/vote, not question or answer text. The last 1,024 answer IDs live in process memory to scope feedback. Browser answer state clears on project change/logout.

Local Ollama receives the selected question/excerpts. No hosted model API is implemented. An optional GitHub read token goes only to the fixed GitHub API origin and never enters model context. Raw errors, auth headers and response bodies are excluded from public error messages. Uvicorn logs paths/status, not request bodies.

`.env`, databases, virtual environments, model files, session fixtures and runtime logs are excluded from Git/Docker context. Public demo credentials are fixtures; configure live mode and a personal password before storing private data. No application telemetry integration is configured.
