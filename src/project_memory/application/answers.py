import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from project_memory.application.retrieval import Retriever
from project_memory.domain.models import Evidence, ProviderUnavailable
from project_memory.domain.ports import Generator


class ModelClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1200)
    citations: list[str] = Field(min_length=1, max_length=5)


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[ModelClaim] = Field(max_length=5)


@dataclass(frozen=True, slots=True)
class Claim:
    text: str
    citations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Answer:
    id: str
    status: str
    mode: str
    retrieval_mode: str
    claims: tuple[Claim, ...]
    evidence: tuple[Evidence, ...]
    warnings: tuple[str, ...]


class AnswerService:
    def __init__(self, retriever: Retriever, generator: Generator | None = None) -> None:
        self.retriever = retriever
        self.generator = generator

    def answer(self, project_id: str, question: str) -> Answer:
        search = self.retriever.search(project_id, question)
        answer_id = str(uuid.uuid4())
        if not search.evidence:
            return Answer(answer_id, "insufficient", "none", search.mode, (), (), search.warnings)
        warnings = list(search.warnings)
        if self.generator:
            supplied = [
                {
                    "id": e.chunk.id,
                    "title": e.chunk.title,
                    "text": e.chunk.text,
                    "revision": e.chunk.revision,
                }
                for e in search.evidence
            ]
            try:
                generated = ModelAnswer.model_validate(self.generator.generate(question, supplied))
                allowed = {e.chunk.id for e in search.evidence}
                if any(set(claim.citations) - allowed for claim in generated.claims):
                    raise ValueError("Unknown citation")
                if not generated.claims:
                    return Answer(
                        answer_id,
                        "insufficient",
                        "llm",
                        search.mode,
                        (),
                        search.evidence,
                        tuple(warnings),
                    )
                claims = tuple(Claim(c.text, tuple(c.citations)) for c in generated.claims)
                return Answer(
                    answer_id,
                    "grounded",
                    "llm",
                    search.mode,
                    claims,
                    search.evidence,
                    tuple(warnings),
                )
            except (ProviderUnavailable, ValidationError, ValueError):
                warnings.append(
                    "Model yanıtı kullanılamadı; aşağıda doğrudan kaynak alıntıları gösteriliyor."
                )
        claims = tuple(Claim(e.chunk.text, (e.chunk.id,)) for e in search.evidence[:3])
        return Answer(
            answer_id,
            "excerpts",
            "extractive",
            search.mode,
            claims,
            search.evidence,
            tuple(warnings),
        )
