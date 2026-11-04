import re

from project_memory.domain.models import ChunkDraft, ImportResult, SourceInput
from project_memory.domain.ports import Embedder, MemoryStore


def chunk_markdown(body: str, max_chars: int = 1200) -> list[str]:
    """Preserve paragraph boundaries when possible; bound even unbroken input."""
    text = body.replace("\r\n", "\n").strip()
    parts: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", text):
        while len(paragraph) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        if len(current) + len(paragraph) + 2 > max_chars:
            parts.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        parts.append(current)
    return [p for p in parts if p]


class Ingestor:
    def __init__(self, store: MemoryStore, embedder: Embedder | None = None) -> None:
        self.store = store
        self.embedder = embedder

    def ingest(self, project_id: str, source: SourceInput) -> ImportResult:
        return self.store.put_source(project_id, source, self.prepare(source))

    def prepare(self, source: SourceInput) -> list[ChunkDraft]:
        if not source.body.strip() or len(source.body) > 100_000:
            raise ValueError("Source must contain 1–100000 characters")
        parts = chunk_markdown(source.body)
        if self.embedder:
            batch = self.embedder.embed(parts)
            if len(batch.vectors) != len(parts):
                raise ValueError("Embedding count mismatch")
            drafts = [
                ChunkDraft(p, v, batch.space) for p, v in zip(parts, batch.vectors, strict=True)
            ]
        else:
            drafts = [ChunkDraft(p) for p in parts]
        return drafts
