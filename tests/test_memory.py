"""Catch cross-project leaks, stale revisions and broken durable writes."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from project_memory.adapters.store import SqlMemoryStore
from project_memory.domain.models import ChunkDraft, SourceInput


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def store(tmp_path, request):
    admin = None
    schema = None
    if request.param == "postgres":
        configured = os.getenv("TEST_DATABASE_URL")
        if not configured:
            pytest.skip("TEST_DATABASE_URL is not configured")
        admin = create_engine(configured)
        schema = "pm_test_" + uuid.uuid4().hex
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(configured).update_query_dict({"options": f"-csearch_path={schema},public"})
        instance = SqlMemoryStore(url.render_as_string(hide_password=False))
    else:
        instance = SqlMemoryStore(f"sqlite:///{tmp_path / 'memory.db'}")
    instance.initialize()
    yield instance
    instance.close()
    if admin is not None and schema is not None:
        assert schema.startswith("pm_test_") and len(schema) == 40
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


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


def test_same_revision_can_be_reindexed_with_a_new_embedding_space(store):
    project = store.create_project("Reindex")
    store.put_source(project.id, source(), [ChunkDraft("Redis")])
    store.put_source(project.id, source(), [ChunkDraft("Redis", (1.0, 0.0), "new:v1")])
    assert store.chunks(project.id)[0].embedding_space == "new:v1"
    assert store.sources(project.id)[0].version_count == 1


def test_dense_scores_are_project_and_model_scoped(store):
    project = store.create_project("Dense")
    other = store.create_project("Other")
    store.put_source(project.id, source(), [ChunkDraft("Redis", (1.0, 0.0), "new:v1")])
    stored = store.chunks(project.id)[0]
    scores = store.dense_scores(project.id, "new:v1", (1.0, 0.0))
    assert scores[stored.id] == pytest.approx(1.0)
    assert store.dense_scores(other.id, "new:v1", (1.0, 0.0)) == {}
    assert store.dense_scores(project.id, "old:v1", (1.0, 0.0)) == {}


def test_batch_import_rolls_back_all_sources_if_one_revision_is_invalid(store):
    project = store.create_project("Atomic")
    store.put_source(project.id, source(), [ChunkDraft("İlk")])
    new = SourceInput("new.md", "New", "Yeni", "", "new", datetime.now(UTC), "repository")
    with pytest.raises(ValueError, match="revision"):
        store.replace_repository_sources(
            project.id,
            [
                (new, [ChunkDraft("Yeni")]),
                (source("Bozuk aynı sürüm"), [ChunkDraft("Bozuk")]),
            ],
        )
    assert len(store.sources(project.id)) == 1
    assert store.chunks(project.id)[0].text == "İlk"
