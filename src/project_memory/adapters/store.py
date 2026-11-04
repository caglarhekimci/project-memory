"""One transactional contract for portable SQLite and PostgreSQL/pgvector."""

import hashlib
import json
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    event,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import Connection, RowMapping

from project_memory.domain.models import (
    Chunk,
    ChunkDraft,
    ImportResult,
    Project,
    SourceInput,
    SourceRecord,
)
from project_memory.domain.vectors import cosine

metadata = MetaData()
projects = Table(
    "projects",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("repository", String(200), nullable=False),
    Column("workflows", JSON, nullable=False),
)
sources = Table(
    "sources",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
    Column("source_key", String(500), nullable=False),
    Column("kind", String(30), nullable=False),
    UniqueConstraint("project_id", "source_key"),
)
versions = Table(
    "versions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("source_id", ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
    Column("title", String(200), nullable=False),
    Column("body", Text, nullable=False),
    Column("url", String(1500), nullable=False),
    Column("revision", String(100), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("observed_at", String(40), nullable=False),
    Column("active", Boolean, nullable=False),
    UniqueConstraint("source_id", "revision"),
)
chunks = Table(
    "chunks",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("version_id", ForeignKey("versions.id", ondelete="CASCADE"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("embedding", JSON().with_variant(Vector(), "postgresql")),
    Column("embedding_space", String(300), nullable=False),
)
sessions = Table(
    "sessions",
    metadata,
    Column("digest", String(64), primary_key=True),
    Column("expires_at", String(40), nullable=False),
)
feedback = Table(
    "feedback",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
    Column("answer_id", String(36), nullable=False),
    Column("vote", Integer, nullable=False),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("project_id", "answer_id"),
)


def _project(row: RowMapping) -> Project:
    return Project(row["id"], row["name"], row["repository"], tuple(row["workflows"]))


class SqlMemoryStore:
    def __init__(self, url: str) -> None:
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False, "timeout": 30}
            if url.startswith("sqlite")
            else {},
        )
        self._lock = threading.RLock()
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", self._sqlite_options)

    @staticmethod
    def _sqlite_options(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

    def initialize(self) -> None:
        with self.engine.begin() as conn:
            if self.engine.dialect.name == "postgresql":
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            metadata.create_all(conn)

    def close(self) -> None:
        self.engine.dispose()

    def _lock_project(self, conn: Connection, project_id: str) -> None:
        if self.engine.dialect.name == "postgresql":
            key = int(hashlib.sha256(project_id.encode()).hexdigest()[:15], 16)
            conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        if not conn.execute(select(projects.c.id).where(projects.c.id == project_id)).first():
            raise KeyError("Project not found")

    def create_project(
        self, name: str, repository: str = "", workflows: tuple[str, ...] = ()
    ) -> Project:
        project = Project(str(uuid.uuid4()), name, repository, workflows)
        with self._lock, self.engine.begin() as conn:
            conn.execute(
                insert(projects).values(
                    id=project.id, name=name, repository=repository, workflows=list(workflows)
                )
            )
        return project

    def project(self, project_id: str) -> Project:
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(projects).where(projects.c.id == project_id)).mappings().first()
            )
            if row is None:
                raise KeyError("Project not found")
            return _project(row)

    def projects(self) -> list[Project]:
        with self.engine.connect() as conn:
            return [
                _project(r)
                for r in conn.execute(select(projects).order_by(projects.c.name)).mappings()
            ]

    def put_source(
        self, project_id: str, source: SourceInput, drafts: list[ChunkDraft]
    ) -> ImportResult:
        with self._lock, self.engine.begin() as conn:
            self._lock_project(conn, project_id)
            return self._put_source(conn, project_id, source, drafts)

    def _put_source(
        self, conn: Connection, project_id: str, source: SourceInput, drafts: list[ChunkDraft]
    ) -> ImportResult:
        body_hash = hashlib.sha256(source.body.encode()).hexdigest()
        row = (
            conn.execute(
                select(sources).where(
                    sources.c.project_id == project_id,
                    sources.c.source_key == source.source_key,
                )
            )
            .mappings()
            .first()
        )
        source_id = row["id"] if row else str(uuid.uuid4())
        if row is None:
            conn.execute(
                insert(sources).values(
                    id=source_id,
                    project_id=project_id,
                    source_key=source.source_key,
                    kind=source.kind,
                )
            )
        old = (
            conn.execute(
                select(versions).where(
                    versions.c.source_id == source_id, versions.c.revision == source.revision
                )
            )
            .mappings()
            .first()
        )
        if old:
            if old["content_hash"] != body_hash:
                raise ValueError("Immutable revision has different content")
            conn.execute(
                update(versions).where(versions.c.source_id == source_id).values(active=False)
            )
            conn.execute(update(versions).where(versions.c.id == old["id"]).values(active=True))
            spaces: set[str] = set(
                conn.execute(
                    select(chunks.c.embedding_space).where(chunks.c.version_id == old["id"])
                ).scalars()
            )
            new_spaces = {draft.embedding_space for draft in drafts}
            if new_spaces != spaces and any(draft.embedding is not None for draft in drafts):
                conn.execute(delete(chunks).where(chunks.c.version_id == old["id"]))
                self._insert_chunks(conn, old["id"], drafts)
                return ImportResult(source_id, True, len(drafts))
            count = conn.execute(
                select(func.count()).select_from(chunks).where(chunks.c.version_id == old["id"])
            ).scalar_one()
            return ImportResult(source_id, False, count)
        conn.execute(update(versions).where(versions.c.source_id == source_id).values(active=False))
        version_id = str(uuid.uuid4())
        conn.execute(
            insert(versions).values(
                id=version_id,
                source_id=source_id,
                title=source.title,
                body=source.body,
                url=source.url,
                revision=source.revision,
                content_hash=body_hash,
                observed_at=source.observed_at.astimezone(UTC).isoformat(),
                active=True,
            )
        )
        self._insert_chunks(conn, version_id, drafts)
        return ImportResult(source_id, True, len(drafts))

    def _insert_chunks(self, conn: Connection, version_id: str, drafts: list[ChunkDraft]) -> None:
        for ordinal, draft in enumerate(drafts):
            conn.execute(
                insert(chunks).values(
                    id=str(uuid.uuid4()),
                    version_id=version_id,
                    ordinal=ordinal,
                    text=draft.text,
                    embedding=list(draft.embedding) if draft.embedding is not None else None,
                    embedding_space=draft.embedding_space,
                )
            )

    def replace_repository_sources(
        self, project_id: str, prepared: list[tuple[SourceInput, list[ChunkDraft]]]
    ) -> list[ImportResult]:
        with self._lock, self.engine.begin() as conn:
            self._lock_project(conn, project_id)
            results = [
                self._put_source(conn, project_id, source, drafts) for source, drafts in prepared
            ]
            keys = {source.source_key for source, _ in prepared}
            obsolete = select(sources.c.id).where(
                sources.c.project_id == project_id,
                sources.c.kind == "repository",
                sources.c.source_key.not_in(keys),
            )
            conn.execute(
                update(versions).where(versions.c.source_id.in_(obsolete)).values(active=False)
            )
            return results

    def dense_scores(
        self, project_id: str, space: str, vector: tuple[float, ...]
    ) -> dict[str, float]:
        if self.engine.dialect.name == "postgresql":
            statement = text("""
                SELECT c.id, 1 - (c.embedding <=> CAST(:query AS vector)) AS similarity
                FROM chunks c JOIN versions v ON c.version_id = v.id
                JOIN sources s ON v.source_id = s.id
                WHERE s.project_id = :project AND v.active = true
                  AND c.embedding_space = :space AND c.embedding IS NOT NULL
                  AND vector_dims(c.embedding) = :dimensions
                ORDER BY similarity DESC LIMIT 20
            """)
            with self.engine.connect() as conn:
                return {
                    r.id: float(r.similarity)
                    for r in conn.execute(
                        statement,
                        {
                            "query": json.dumps(vector),
                            "project": project_id,
                            "space": space,
                            "dimensions": len(vector),
                        },
                    )
                }
        return {
            chunk.id: cosine(vector, chunk.embedding)
            for chunk in self.chunks(project_id)
            if chunk.embedding is not None and chunk.embedding_space == space
        }

    def sources(self, project_id: str) -> list[SourceRecord]:
        counts = (
            select(versions.c.source_id, func.count().label("version_count"))
            .group_by(versions.c.source_id)
            .subquery()
        )
        stmt = (
            select(sources, versions, counts.c.version_count)
            .join(versions, sources.c.id == versions.c.source_id)
            .join(counts, counts.c.source_id == sources.c.id)
            .where(sources.c.project_id == project_id, versions.c.active.is_(True))
            .order_by(versions.c.observed_at.desc())
        )
        with self.engine.connect() as conn:
            return [
                SourceRecord(
                    r["id"],
                    r["source_key"],
                    r["title"],
                    r["body"],
                    r["url"],
                    r["revision"],
                    r["observed_at"],
                    r["kind"],
                    r["version_count"],
                )
                for r in conn.execute(stmt).mappings()
            ]

    def chunks(self, project_id: str) -> list[Chunk]:
        stmt = (
            select(
                chunks,
                sources.c.id.label("source_id"),
                sources.c.project_id,
                versions.c.title,
                versions.c.url,
                versions.c.revision,
                versions.c.observed_at,
            )
            .join(versions, chunks.c.version_id == versions.c.id)
            .join(sources, versions.c.source_id == sources.c.id)
            .where(sources.c.project_id == project_id, versions.c.active.is_(True))
            .order_by(sources.c.id, chunks.c.ordinal)
        )
        with self.engine.connect() as conn:
            return [
                Chunk(
                    r["id"],
                    r["source_id"],
                    r["project_id"],
                    r["title"],
                    r["text"],
                    r["url"],
                    r["revision"],
                    r["observed_at"],
                    tuple(float(x) for x in r["embedding"]) if r["embedding"] is not None else None,
                    r["embedding_space"],
                )
                for r in conn.execute(stmt).mappings()
            ]

    def delete_source(self, project_id: str, source_id: str) -> bool:
        with self._lock, self.engine.begin() as conn:
            self._lock_project(conn, project_id)
            result = conn.execute(
                delete(sources).where(sources.c.id == source_id, sources.c.project_id == project_id)
            )
            return bool(result.rowcount)

    def reconcile_repository_sources(self, project_id: str, keys: set[str]) -> None:
        with self._lock, self.engine.begin() as conn:
            self._lock_project(conn, project_id)
            obsolete = select(sources.c.id).where(
                sources.c.project_id == project_id,
                sources.c.kind == "repository",
                sources.c.source_key.not_in(keys),
            )
            conn.execute(
                update(versions).where(versions.c.source_id.in_(obsolete)).values(active=False)
            )

    def create_session(self, digest: str, expires_at: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                delete(sessions).where(sessions.c.expires_at <= datetime.now(UTC).isoformat())
            )
            conn.execute(
                insert(sessions).values(
                    digest=digest, expires_at=expires_at.astimezone(UTC).isoformat()
                )
            )

    def session_valid(self, digest: str, now: datetime) -> bool:
        with self.engine.connect() as conn:
            return (
                conn.execute(
                    select(sessions.c.digest).where(
                        sessions.c.digest == digest,
                        sessions.c.expires_at > now.astimezone(UTC).isoformat(),
                    )
                ).first()
                is not None
            )

    def revoke_session(self, digest: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(sessions).where(sessions.c.digest == digest))

    def add_feedback(self, project_id: str, answer_id: str, vote: int) -> None:
        with self._lock, self.engine.begin() as conn:
            self._lock_project(conn, project_id)
            conn.execute(
                delete(feedback).where(
                    feedback.c.project_id == project_id, feedback.c.answer_id == answer_id
                )
            )
            conn.execute(
                insert(feedback).values(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    answer_id=answer_id,
                    vote=vote,
                    created_at=datetime.now(UTC).isoformat(),
                )
            )
