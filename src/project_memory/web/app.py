import hashlib
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from project_memory.adapters.github import GitHubClient
from project_memory.adapters.ollama import Ollama
from project_memory.adapters.store import SqlMemoryStore
from project_memory.application.answers import AnswerService
from project_memory.application.ingestion import Ingestor
from project_memory.application.retrieval import Retriever
from project_memory.bootstrap import seed_demo
from project_memory.domain.models import ProviderUnavailable, SourceInput
from project_memory.settings import Settings
from project_memory.web.schemas import (
    FeedbackInput,
    LoginInput,
    NoteInput,
    ProjectInput,
    QuestionInput,
)
from project_memory.web.security import BodyLimitMiddleware, OwnerAuth

WEB_DIR = Path(__file__).parent


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    if config.database_url.startswith("sqlite:///"):
        Path(config.database_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )
    store = SqlMemoryStore(config.database_url)
    github = GitHubClient(token=config.github_token.get_secret_value())
    model = (
        Ollama(config.ollama_url, config.model, config.embedding_model)
        if config.model_backend == "ollama"
        else None
    )
    ingestor = Ingestor(store, model)
    answers = AnswerService(Retriever(store, model, config.dense_threshold), model)
    auth = OwnerAuth(config, store)
    busy = threading.BoundedSemaphore(2)
    answer_ids: OrderedDict[str, str] = OrderedDict()
    answer_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        store.initialize()
        if config.demo_mode:
            seed_demo(store)
        yield
        github.client.close()
        if model:
            model.client.close()
        store.close()

    app = FastAPI(
        title="Project Memory", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.add_middleware(BodyLimitMiddleware)
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=WEB_DIR / "templates")

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(KeyError)
    async def not_found(_: Request, __: KeyError) -> JSONResponse:
        return JSONResponse({"detail": "Kayıt bulunamadı."}, status_code=404)

    @app.exception_handler(ProviderUnavailable)
    async def upstream_error(_: Request, error: ProviderUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=502)

    @contextmanager
    def operation() -> Iterator[None]:
        if not busy.acquire(blocking=False):
            raise HTTPException(429, "İki işlem sürüyor. Biraz sonra tekrar deneyin.")
        try:
            yield
        finally:
            busy.release()

    @app.get("/", include_in_schema=False)
    def index(request: Request) -> Response:
        return templates.TemplateResponse(
            request=request, name="index.html", context={"demo": config.demo_mode}
        )

    @app.get("/healthz")
    def health() -> dict[str, str]:
        store.projects()
        return {"status": "ok"}

    @app.post("/api/login")
    def login(payload: LoginInput, request: Request, response: Response) -> dict[str, bool]:
        auth.login(request, response, payload.password)
        return {"ok": True}

    @app.post("/api/logout", dependencies=[Depends(auth.require_owner)])
    def logout(request: Request, response: Response) -> dict[str, bool]:
        auth.logout(request, response)
        return {"ok": True}

    @app.get("/api/meta", dependencies=[Depends(auth.require_owner)])
    def meta() -> dict[str, Any]:
        return {
            "demo_mode": config.demo_mode,
            "model_backend": config.model_backend,
            "model": config.model if model else None,
            "embedding_model": config.embedding_model if model else None,
            "storage": store.engine.dialect.name,
        }

    @app.get("/api/projects", dependencies=[Depends(auth.require_owner)])
    def list_projects() -> list[dict[str, Any]]:
        return [asdict(p) for p in store.projects()]

    @app.post("/api/projects", status_code=201, dependencies=[Depends(auth.require_owner)])
    def create_project(payload: ProjectInput) -> dict[str, Any]:
        if len(store.projects()) >= 20:
            raise HTTPException(409, "Bu kişisel çalışma alanında en fazla 20 proje tutulabilir.")
        return asdict(
            store.create_project(payload.name, payload.repository, tuple(payload.workflows))
        )

    @app.get("/api/projects/{project_id}/sources", dependencies=[Depends(auth.require_owner)])
    def list_sources(project_id: str) -> list[dict[str, Any]]:
        store.project(project_id)
        return [asdict(s) for s in store.sources(project_id)]

    def save_note(project_id: str, payload: NoteInput, key: str) -> dict[str, Any]:
        revision = hashlib.sha256((payload.title + "\n" + payload.body).encode()).hexdigest()
        spec = SourceInput(
            key, payload.title, payload.body, "", revision, datetime.now(UTC), "note"
        )
        with operation():
            result = ingestor.ingest(project_id, spec)
        return asdict(result)

    @app.post(
        "/api/projects/{project_id}/notes",
        status_code=201,
        dependencies=[Depends(auth.require_owner)],
    )
    def create_note(project_id: str, payload: NoteInput) -> dict[str, Any]:
        store.project(project_id)
        if len(store.sources(project_id)) >= 200:
            raise HTTPException(409, "Bu projede kaynak sınırına ulaşıldı.")
        return save_note(project_id, payload, "note:" + str(uuid.uuid4()))

    @app.put(
        "/api/projects/{project_id}/notes/{source_id}", dependencies=[Depends(auth.require_owner)]
    )
    def update_note(project_id: str, source_id: str, payload: NoteInput) -> dict[str, Any]:
        record = next(
            (s for s in store.sources(project_id) if s.id == source_id and s.kind == "note"), None
        )
        if record is None:
            raise HTTPException(404, "Düzenlenebilir not bulunamadı.")
        return save_note(project_id, payload, record.source_key)

    @app.delete(
        "/api/projects/{project_id}/sources/{source_id}",
        status_code=204,
        dependencies=[Depends(auth.require_owner)],
    )
    def remove_source(project_id: str, source_id: str) -> Response:
        if not store.delete_source(project_id, source_id):
            raise HTTPException(404, "Kaynak bulunamadı.")
        return Response(status_code=204)

    @app.post("/api/projects/{project_id}/sync", dependencies=[Depends(auth.require_owner)])
    def sync(project_id: str) -> dict[str, Any]:
        project = store.project(project_id)
        if not project.repository:
            raise HTTPException(409, "Bu projeye bağlı GitHub deposu yok.")
        with operation():
            documents = github.documents(project.repository)
            prepared = [(document, ingestor.prepare(document)) for document in documents]
            results = store.replace_repository_sources(project_id, prepared)
        return {
            "documents": len(documents),
            "changed": sum(r.changed for r in results),
            "scope": "README.md ve docs/ altından en fazla 12 Markdown belgesi",
        }

    @app.post("/api/projects/{project_id}/checks", dependencies=[Depends(auth.require_owner)])
    def checks(project_id: str) -> dict[str, Any]:
        project = store.project(project_id)
        if not project.repository:
            raise HTTPException(409, "Bu projeye bağlı GitHub deposu yok.")
        with operation():
            return asdict(github.snapshot(project.repository, project.workflows))

    @app.post("/api/projects/{project_id}/answer", dependencies=[Depends(auth.require_owner)])
    def answer(project_id: str, payload: QuestionInput) -> dict[str, Any]:
        project = store.project(project_id)
        started = time.monotonic()
        with operation():
            snapshot = None
            check_error = None
            if payload.use_live_checks and project.repository:
                try:
                    snapshot = asdict(github.snapshot(project.repository, project.workflows))
                except ProviderUnavailable as error:
                    check_error = str(error)
            result = answers.answer(project_id, payload.question)
        with answer_lock:
            answer_ids[result.id] = project_id
            while len(answer_ids) > 1024:
                answer_ids.popitem(last=False)
        return {
            **asdict(result),
            "checks": snapshot,
            "check_error": check_error,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "observed_at": datetime.now(UTC).isoformat(),
        }

    @app.post(
        "/api/projects/{project_id}/feedback",
        status_code=204,
        dependencies=[Depends(auth.require_owner)],
    )
    def add_feedback(project_id: str, payload: FeedbackInput) -> Response:
        with answer_lock:
            if answer_ids.get(payload.answer_id) != project_id:
                raise HTTPException(404, "Bu oturumda yanıt bulunamadı.")
        store.add_feedback(project_id, payload.answer_id, payload.vote)
        return Response(status_code=204)

    return app
