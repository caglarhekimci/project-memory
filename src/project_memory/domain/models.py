from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    repository: str
    workflows: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceInput:
    source_key: str
    title: str
    body: str
    url: str
    revision: str
    observed_at: datetime
    kind: str = "note"


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    text: str
    embedding: tuple[float, ...] | None = None
    embedding_space: str = ""


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    source_id: str
    project_id: str
    title: str
    text: str
    url: str
    revision: str
    observed_at: str
    embedding: tuple[float, ...] | None
    embedding_space: str


@dataclass(frozen=True, slots=True)
class SourceRecord:
    id: str
    source_key: str
    title: str
    body: str
    url: str
    revision: str
    observed_at: str
    kind: str
    version_count: int


@dataclass(frozen=True, slots=True)
class ImportResult:
    source_id: str
    changed: bool
    chunk_count: int


@dataclass(frozen=True, slots=True)
class Evidence:
    chunk: Chunk
    score: float


@dataclass(frozen=True, slots=True)
class SearchResult:
    evidence: tuple[Evidence, ...]
    mode: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    space: str
    vectors: tuple[tuple[float, ...], ...]


class ProviderUnavailable(Exception):
    """An upstream operation failed; the public message must be safe to display."""
