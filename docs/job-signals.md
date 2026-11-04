# Türkiye LinkedIn signals → implementation

Research date: 4 November 2026. Purposive technology sample, not an open-vacancy census or application-fit assessment; some postings were closed.

| Signal | Concrete evidence |
| --- | --- |
| Python/backend, clean code | FastAPI, typed ports, domain/application/adapters/web separation, lint/type checks |
| LLM, structured output | Real Ollama adapter, JSON schema, bounded claims, validated citations |
| RAG, embeddings, vector search | Versioned sources, BGE-M3 digest namespaces, PostgreSQL/pgvector cosine, portable SQLite |
| Hybrid search | BM25 + dense + reciprocal-rank fusion; measured baseline comparison |
| Evaluation/LLMOps | Frozen questions, separate calibration, preserved failures, reproducible metrics/feedback |
| Tool/API integration | Read-only fixed-origin GitHub, current-head reconciliation, no arbitrary model execution |
| Containers/CI | Nonroot image, two storage modes, browser/persistence checks |
| Fine-tuning/LoRA | Explicitly deferred without measured benefit and suitable reviewed data |
| MCP/reranker/multi-agent | Not implemented or claimed; provider/tool boundaries allow justified extensions |

Primary examples: [QNB](https://tr.linkedin.com/jobs/view/a%C4%B1-eng%C4%B1neer-a%C4%B1-agent-developer-at-qnb-t%C3%BCrkiye-4484634702), [Raporzen](https://tr.linkedin.com/jobs/view/yapay-zek%C3%A2-m%C3%BChendisi-llm-a%C4%B1-agent-at-raporzen-yaz%C4%B1l%C4%B1m-4481862582), [Garanti AI Factory](https://tr.linkedin.com/jobs/view/yapay-zeka-m%C3%BChendisi-%E2%80%93-a%C4%B1-factory-at-garanti-bbva-teknoloji-4484356343), [Gordian](https://tr.linkedin.com/jobs/view/working-student-%C4%B1ntern-%E2%80%93-a%C4%B1-engineering-llm-systems-ankara-dach-remote-at-gordian-analytics-4469813491), [SemperTech](https://tr.linkedin.com/jobs/view/a%C4%B1-engineer-and-software-developer-at-sempertech-4480625350).

A portfolio provides inspectable implementation/evaluation; it does not become claimed years of professional LLM experience.
