"""Catch unrelated answers, lexical misses and incompatible dense vectors."""

from datetime import UTC, datetime

import pytest

from project_memory.adapters.store import SqlMemoryStore
from project_memory.application.ingestion import Ingestor, chunk_markdown
from project_memory.application.retrieval import Retriever, tokenize
from project_memory.domain.models import (
    ChunkDraft,
    EmbeddingBatch,
    ProviderUnavailable,
    SourceInput,
)


@pytest.fixture
def memory(tmp_path):
    store = SqlMemoryStore(f"sqlite:///{tmp_path / 'search.db'}")
    store.initialize()
    project = store.create_project("Ledger")
    yield store, project
    store.close()


def add(store, project, title, body):
    spec = SourceInput(title, title, body, "", title, datetime.now(UTC), "note")
    return Ingestor(store).ingest(project.id, spec)


def test_turkish_search_normalizes_dotted_and_dotless_i():
    assert tokenize("HIZ SINIRLAMA İÇİN Redis") == ["hiz", "sinirlama", "icin", "redis"]


def test_markdown_chunks_keep_headings_and_have_a_hard_size_limit():
    chunks = chunk_markdown("# Karar\n\n" + "x" * 5000, max_chars=800)
    assert len(chunks) > 1
    assert all(0 < len(c) <= 800 for c in chunks)
    assert "Karar" in chunks[0]


def test_lexical_search_returns_supporting_excerpt_and_revision(memory):
    store, project = memory
    add(store, project, "Redis", "Redis hız sınırlama sağlar; stok PostgreSQL üzerinde tutulur.")
    add(store, project, "Arayüz", "Mobil arayüz erişilebilirlik testleri içerir.")
    result = Retriever(store).search(project.id, "Redis neden kullanılıyor?")
    assert len(result.evidence) == 1
    assert "hız sınırlama" in result.evidence[0].chunk.text
    assert result.mode == "lexical"


def test_unknown_question_returns_no_evidence(memory):
    store, project = memory
    add(store, project, "Stok", "PostgreSQL stok kayıtlarının kaynağıdır.")
    assert Retriever(store).search(project.id, "Satürn gezegeninin halkaları").evidence == ()


def test_retrieval_does_not_cross_project_boundary(memory):
    store, project = memory
    other = store.create_project("Other")
    add(store, project, "Redis", "Redis stok rezervasyonu")
    assert Retriever(store).search(other.id, "Redis").evidence == ()


class FixedEmbedding:
    def __init__(self, space="test:v1"):
        self.space = space

    def embed(self, texts):
        return EmbeddingBatch(self.space, tuple((1.0, 0.0) for _ in texts))


def test_hybrid_retrieves_a_semantic_match_without_shared_words(memory):
    store, project = memory
    spec = SourceInput("semantic", "Karar", "Aynı işlem yinelenmez.", "", "v1", datetime.now(UTC))
    store.put_source(project.id, spec, [ChunkDraft(spec.body, (1.0, 0.0), "test:v1")])
    result = Retriever(store, FixedEmbedding()).search(project.id, "idempotency")
    assert result.mode == "hybrid"
    assert result.evidence[0].chunk.text == "Aynı işlem yinelenmez."


def test_incompatible_embedding_space_cannot_supply_semantic_evidence(memory):
    store, project = memory
    spec = SourceInput("semantic", "Karar", "Aynı işlem yinelenmez.", "", "v1", datetime.now(UTC))
    store.put_source(project.id, spec, [ChunkDraft(spec.body, (1.0, 0.0), "test:old")])
    result = Retriever(store, FixedEmbedding()).search(project.id, "idempotency")
    assert result.evidence == ()
    assert result.mode == "lexical"
    assert result.warnings


def test_embedding_outage_preserves_explicit_lexical_fallback(memory):
    store, project = memory
    add(store, project, "Redis", "Redis hız sınırlama sağlar.")

    class Offline:
        def embed(self, texts):
            raise ProviderUnavailable("Offline")

    result = Retriever(store, Offline()).search(project.id, "Redis")
    assert result.mode == "lexical"
    assert len(result.evidence) == 1
    assert result.warnings


def test_calibrated_semantic_threshold_accepts_supported_paraphrase_range(memory):
    store, project = memory
    spec = SourceInput("semantic", "Karar", "Yinelenen kayıt önlenir.", "", "v1", datetime.now(UTC))
    store.put_source(project.id, spec, [ChunkDraft(spec.body, (0.45, 0.89302855497), "test:v1")])
    assert Retriever(store, FixedEmbedding()).search(project.id, "idempotency").evidence


def test_calibrated_semantic_threshold_rejects_irrelevant_range(memory):
    store, project = memory
    spec = SourceInput("semantic", "Karar", "Yinelenen kayıt önlenir.", "", "v1", datetime.now(UTC))
    store.put_source(project.id, spec, [ChunkDraft(spec.body, (0.3, 0.9539392014), "test:v1")])
    assert Retriever(store, FixedEmbedding()).search(project.id, "astronomy").evidence == ()


def test_lexical_only_evidence_does_not_claim_hybrid_mode(memory):
    store, project = memory
    spec = SourceInput("redis", "Redis", "Redis hız sınırlar.", "", "v1", datetime.now(UTC))
    store.put_source(project.id, spec, [ChunkDraft(spec.body, (0.3, 0.9539392014), "test:v1")])
    result = Retriever(store, FixedEmbedding()).search(project.id, "Redis")
    assert result.evidence
    assert result.mode == "lexical"
