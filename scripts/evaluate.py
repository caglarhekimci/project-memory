"""Run fixed, public-fixture retrieval experiments. Outputs contain no private project data."""

import argparse
import json
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from project_memory.adapters.ollama import Ollama
from project_memory.adapters.store import SqlMemoryStore
from project_memory.application.answers import AnswerService
from project_memory.application.ingestion import Ingestor
from project_memory.application.retrieval import Retriever
from project_memory.domain.models import SourceInput


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models", action="store_true", help="Use real local Ollama BGE-M3 embeddings"
    )
    parser.add_argument(
        "--generate", action="store_true", help="Also generate answers for 3 selected questions"
    )
    parser.add_argument(
        "--gate", action="store_true", help="Fail if the frozen retrieval gates are missed"
    )
    parser.add_argument("--output", type=Path, default=Path("test-results/evaluation.json"))
    args = parser.parse_args()
    dataset = json.loads(Path("evals/dataset.json").read_text(encoding="utf-8"))
    model = Ollama() if args.models else None
    with tempfile.TemporaryDirectory() as directory:
        store = SqlMemoryStore(f"sqlite:///{Path(directory) / 'evaluation.db'}")
        store.initialize()
        projects = {
            name: store.create_project(name)
            for name in {d["project"] for d in dataset["documents"]}
        }
        for document in dataset["documents"]:
            Ingestor(store, model).ingest(
                projects[document["project"]].id,
                SourceInput(
                    document["key"],
                    document["title"],
                    document["body"],
                    "",
                    dataset["version"],
                    datetime.now(UTC),
                ),
            )
        source_keys = {
            source.id: source.source_key
            for p in projects.values()
            for source in store.sources(p.id)
        }
        reports = []
        for mode, embedder in [("lexical", None), *(([("hybrid", model)]) if model else [])]:
            rows = []
            for item in dataset["questions"]:
                started = time.monotonic()
                result = Retriever(store, embedder).search(
                    projects[item["project"]].id, item["question"], 3
                )
                found = [source_keys[e.chunk.source_id] for e in result.evidence]
                rank = found.index(item["expected"]) + 1 if item["expected"] in found else None
                rows.append(
                    {
                        "id": item["id"],
                        "type": item["type"],
                        "question": item["question"],
                        "expected": item["expected"],
                        "found": found,
                        "rank": rank,
                        "mode": result.mode,
                        "warnings": result.warnings,
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                    }
                )
            supported = [r for r in rows if r["expected"] is not None]
            unknown = [r for r in rows if r["expected"] is None]
            report = {
                "mode": mode,
                "supported_recall_at_3": sum(r["rank"] is not None for r in supported)
                / len(supported),
                "supported_mrr": sum(1 / r["rank"] if r["rank"] else 0 for r in supported)
                / len(supported),
                "unanswerable_abstention": sum(not r["found"] for r in unknown) / len(unknown),
                "rows": rows,
            }
            reports.append(report)
        generated = []
        if args.generate and model:
            for item in [
                dataset["questions"][0],
                dataset["questions"][4],
                dataset["questions"][-1],
            ]:
                started = time.monotonic()
                answer = AnswerService(Retriever(store, model), model).answer(
                    projects[item["project"]].id, item["question"]
                )
                generated.append(
                    {
                        "id": item["id"],
                        "question": item["question"],
                        "status": answer.status,
                        "mode": answer.mode,
                        "claims": [asdict(c) for c in answer.claims],
                        "citation_ids_valid": all(
                            set(c.citations) <= {e.chunk.id for e in answer.evidence}
                            for c in answer.claims
                        ),
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                    }
                )
        output = {
            "dataset": dataset["version"],
            "checked_at": datetime.now(UTC).isoformat(),
            "evidence": "real local Ollama" if model else "deterministic lexical baseline",
            "gates": dataset["gates"],
            "reports": reports,
            "generated": generated,
            "limits": (
                "6 hand-authored documents, 15 curated questions; "
                "not a production quality estimate."
            ),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "metrics": [{k: v for k, v in r.items() if k != "rows"} for r in reports],
                }
            )
        )
        store.close()
        if model:
            model.client.close()
        if args.gate:
            final = reports[-1]
            if any(final[key] < threshold for key, threshold in dataset["gates"].items()):
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
