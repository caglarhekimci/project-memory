from datetime import UTC, datetime

import pytest

from project_memory.adapters.store import SqlMemoryStore
from project_memory.application.answers import AnswerService
from project_memory.application.ingestion import Ingestor
from project_memory.application.retrieval import Retriever
from project_memory.domain.models import ProviderUnavailable, SourceInput


@pytest.fixture
def memory(tmp_path):
    store = SqlMemoryStore(f"sqlite:///{tmp_path / 'answer.db'}")
    store.initialize()
    project = store.create_project("Ledger")
    Ingestor(store).ingest(
        project.id,
        SourceInput(
            "redis",
            "Redis kararı",
            "Redis yalnızca hız sınırlama için kullanılır.",
            "",
            "v1",
            datetime.now(UTC),
        ),
    )
    yield store, project
    store.close()


def test_missing_evidence_abstains_before_calling_model(memory):
    store, project = memory

    class MustNotRun:
        def generate(self, question, evidence):
            raise AssertionError("No evidence should reach a generator")

    result = AnswerService(Retriever(store), MustNotRun()).answer(project.id, "Satürn halkaları")
    assert result.status == "insufficient"
    assert result.claims == ()


def test_model_cannot_cite_an_unknown_document(memory):
    store, project = memory

    class InvalidCitation:
        def generate(self, question, evidence):
            return {"claims": [{"text": "Redis stokları tutar.", "citations": ["invented"]}]}

    result = AnswerService(Retriever(store), InvalidCitation()).answer(project.id, "Redis")
    assert result.mode == "extractive"
    assert "hız sınırlama" in result.claims[0].text
    assert result.warnings


def test_model_outage_returns_labelled_source_excerpts(memory):
    store, project = memory

    class Offline:
        def generate(self, question, evidence):
            raise ProviderUnavailable("Model unavailable")

    result = AnswerService(Retriever(store), Offline()).answer(project.id, "Redis")
    assert result.mode == "extractive"
    assert result.warnings


def test_generated_claims_keep_only_valid_source_identifiers(memory):
    store, project = memory

    class Grounded:
        def generate(self, question, evidence):
            return {
                "claims": [
                    {"text": "Redis hız sınırlama içindir.", "citations": [evidence[0]["id"]]}
                ]
            }

    result = AnswerService(Retriever(store), Grounded()).answer(project.id, "Redis")
    assert result.mode == "llm"
    assert result.claims[0].citations == (result.evidence[0].chunk.id,)


def test_short_model_citations_map_back_to_immutable_chunk_ids(memory):
    store, project = memory

    class ShortCitations:
        def generate(self, question, evidence):
            assert evidence[0]["id"] == "S1"
            return {"claims": [{"text": "Redis hız sınırlar.", "citations": ["S1"]}]}

    result = AnswerService(Retriever(store), ShortCitations()).answer(project.id, "Redis")
    assert result.mode == "llm"
    assert result.claims[0].citations == (result.evidence[0].chunk.id,)
