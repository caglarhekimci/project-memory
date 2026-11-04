"""Catch cross-project leaks, stale revisions and broken durable writes."""

from datetime import UTC, datetime, timedelta

import pytest

from project_memory.adapters.store import SqlMemoryStore
from project_memory.domain.models import ChunkDraft, SourceInput


@pytest.fixture
def store(tmp_path):
    instance = SqlMemoryStore(f"sqlite:///{tmp_path / 'memory.db'}")
    instance.initialize()
    yield instance
    instance.close()


def source(body="Redis yalnızca hız sınırlama için kullanılır.", revision="a" * 40):
    return SourceInput(
        source_key="docs/architecture.md",
        title="Mimari karar",
        body=body,
        url=f"https://github.com/example/ledger/blob/{revision}/docs/architecture.md",
        revision=revision,
        observed_at=datetime(2026, 11, 4, tzinfo=UTC),
        kind="repository",
    )


def test_repeated_import_does_not_duplicate_chunks(store):
    project = store.create_project("Ledger", "example/ledger", ("CI",))
    first = store.put_source(project.id, source(), [ChunkDraft("Redis hız sınırlar.")])
    second = store.put_source(project.id, source(), [ChunkDraft("Redis hız sınırlar.")])
    assert first.changed is True
    assert second.changed is False
    assert first.source_id == second.source_id
    assert len(store.chunks(project.id)) == 1


def test_new_revision_replaces_active_chunks_and_keeps_revision_history(store):
    project = store.create_project("Ledger")
    store.put_source(project.id, source(), [ChunkDraft("Eski karar")])
    store.put_source(project.id, source("Yeni karar", "b" * 40), [ChunkDraft("Yeni karar")])
    assert [c.text for c in store.chunks(project.id)] == ["Yeni karar"]
    records = store.sources(project.id)
    assert len(records) == 1
    assert records[0].revision == "b" * 40
    assert records[0].version_count == 2


def test_same_revision_with_different_content_is_rejected_atomically(store):
    project = store.create_project("Ledger")
    store.put_source(project.id, source(), [ChunkDraft("İlk karar")])
    with pytest.raises(ValueError, match="revision"):
        store.put_source(project.id, source("Değiştirilmiş"), [ChunkDraft("Yanlış karar")])
    assert [c.text for c in store.chunks(project.id)] == ["İlk karar"]


def test_chunks_and_sources_are_project_scoped(store):
    first = store.create_project("A")
    second = store.create_project("B")
    store.put_source(first.id, source(), [ChunkDraft("A gizli kararı")])
    assert store.chunks(second.id) == []
    assert store.sources(second.id) == []


def test_delete_source_removes_all_versions_and_rejects_wrong_project(store):
    first = store.create_project("A")
    second = store.create_project("B")
    saved = store.put_source(first.id, source(), [ChunkDraft("Eski")])
    store.put_source(first.id, source("Yeni", "b" * 40), [ChunkDraft("Yeni")])
    assert store.delete_source(second.id, saved.source_id) is False
    assert len(store.chunks(first.id)) == 1
    assert store.delete_source(first.id, saved.source_id) is True
    assert store.sources(first.id) == []
    assert store.chunks(first.id) == []


def test_data_survives_database_reopen(tmp_path):
    url = f"sqlite:///{tmp_path / 'durable.db'}"
    first = SqlMemoryStore(url)
    first.initialize()
    project = first.create_project("Kalıcı")
    first.put_source(project.id, source(), [ChunkDraft("Kalıcı karar")])
    first.close()
    second = SqlMemoryStore(url)
    second.initialize()
    assert second.project(project.id).name == "Kalıcı"
    assert second.chunks(project.id)[0].text == "Kalıcı karar"
    second.close()


def test_sessions_expire_and_logout_revokes_digest(store):
    now = datetime(2026, 11, 4, tzinfo=UTC)
    store.create_session("digest-one", now + timedelta(hours=8))
    assert store.session_valid("digest-one", now)
    assert not store.session_valid("digest-one", now + timedelta(hours=9))
    store.revoke_session("digest-one")
    assert not store.session_valid("digest-one", now)


def test_embedding_space_is_preserved_without_mixing(store):
    project = store.create_project("Vektörler")
    store.put_source(project.id, source(), [ChunkDraft("Redis", (1.0, 0.0), "model:revision1")])
    chunk = store.chunks(project.id)[0]
    assert chunk.embedding == (1.0, 0.0)
    assert chunk.embedding_space == "model:revision1"


def test_repository_sync_deactivates_deleted_paths_but_keeps_personal_notes(store):
    project = store.create_project("Ledger")
    store.put_source(project.id, source(), [ChunkDraft("Silinecek dosya")])
    note = SourceInput("note:1", "Not", "Kişisel not", "", "n1", datetime.now(UTC), "note")
    store.put_source(project.id, note, [ChunkDraft("Kişisel not")])
    store.reconcile_repository_sources(project.id, set())
    assert [c.text for c in store.chunks(project.id)] == ["Kişisel not"]
