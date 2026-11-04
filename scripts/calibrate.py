"""Inspect a separate development split; never tune against the regression questions."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from project_memory.adapters.ollama import Ollama
from project_memory.adapters.store import SqlMemoryStore
from project_memory.application.ingestion import Ingestor
from project_memory.domain.models import SourceInput


def main() -> None:
    dataset = json.loads(Path("evals/dataset.json").read_text(encoding="utf-8"))
    calibration = json.loads(Path("evals/calibration.json").read_text(encoding="utf-8"))
    model = Ollama()
    with tempfile.TemporaryDirectory() as directory:
        store = SqlMemoryStore(f"sqlite:///{Path(directory) / 'calibration.db'}")
        store.initialize()
        projects = {
            name: store.create_project(name)
            for name in {d["project"] for d in dataset["documents"]}
        }
        for doc in dataset["documents"]:
            Ingestor(store, model).ingest(
                projects[doc["project"]].id,
                SourceInput(
                    doc["key"], doc["title"], doc["body"], "", "calibration", datetime.now(UTC)
                ),
            )
        rows = []
        for item in calibration["questions"]:
            embedded = model.embed([item["question"]])
            scores = store.dense_scores(
                projects[item["project"]].id, embedded.space, embedded.vectors[0]
            )
            rows.append({**item, "maximum_cosine": max(scores.values(), default=0.0)})
        result = {
            "checked_at": datetime.now(UTC).isoformat(),
            "rows": rows,
            "lowest_relevant": min(r["maximum_cosine"] for r in rows if r["relevant"]),
            "highest_irrelevant": max(r["maximum_cosine"] for r in rows if not r["relevant"]),
        }
        Path("test-results/calibration.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False))
        store.close()
    model.client.close()


if __name__ == "__main__":
    main()
