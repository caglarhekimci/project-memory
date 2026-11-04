"""Serialize the complete read/prepare/commit workflow for each project."""

import threading
from _thread import LockType
from dataclasses import dataclass

from project_memory.application.ingestion import Ingestor
from project_memory.domain.ports import MemoryStore, RepositoryReader


class SyncInProgress(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SyncResult:
    documents: int
    changed: int
    scope: str = "README.md ve docs/ altından en fazla 12 Markdown belgesi"


class RepositorySync:
    def __init__(self, store: MemoryStore, reader: RepositoryReader, ingestor: Ingestor) -> None:
        self.store = store
        self.reader = reader
        self.ingestor = ingestor
        self._guard = threading.Lock()
        self._project_locks: dict[str, LockType] = {}

    def run(self, project_id: str, repository: str) -> SyncResult:
        with self._guard:
            lock = self._project_locks.setdefault(project_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise SyncInProgress("Bu proje için belge güncellemesi zaten sürüyor.")
        try:
            documents = self.reader.documents(repository)
            prepared = [(source, self.ingestor.prepare(source)) for source in documents]
            results = self.store.replace_repository_sources(project_id, prepared)
            return SyncResult(len(documents), sum(result.changed for result in results))
        finally:
            lock.release()
