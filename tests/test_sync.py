"""An older in-flight sync must not overwrite a newer repository snapshot."""

import threading
from datetime import UTC, datetime

import pytest

from project_memory.adapters.store import SqlMemoryStore
from project_memory.application.ingestion import Ingestor
from project_memory.application.sync import RepositorySync, SyncInProgress
from project_memory.domain.models import SourceInput


def test_same_project_sync_cannot_fetch_or_commit_out_of_order(tmp_path):
    store = SqlMemoryStore(f"sqlite:///{tmp_path / 'sync.db'}")
    store.initialize()
    project = store.create_project("Ledger", "owner/repo")
    entered = threading.Event()
    release = threading.Event()

    class ControlledReader:
        def __init__(self):
            self.calls = 0

        def documents(self, repository):
            self.calls += 1
            if self.calls == 1:
                entered.set()
                assert release.wait(5)
            revision = "old" if self.calls == 1 else "new"
            return [
                SourceInput(
                    "README.md", "Readme", revision, "", revision, datetime.now(UTC), "repository"
                )
            ]

    reader = ControlledReader()
    sync = RepositorySync(store, reader, Ingestor(store))
    errors = []

    def first_sync():
        try:
            sync.run(project.id, project.repository)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=first_sync)
    thread.start()
    assert entered.wait(5)
    try:
        with pytest.raises(SyncInProgress):
            sync.run(project.id, project.repository)
        assert reader.calls == 1
    finally:
        release.set()
        thread.join(5)
    assert not errors
    assert store.sources(project.id)[0].revision == "old"
    sync.run(project.id, project.repository)
    assert store.sources(project.id)[0].revision == "new"
    assert store.sources(project.id)[0].version_count == 2
    store.close()
