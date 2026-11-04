from pydantic import BaseModel, ConfigDict, Field, field_validator

from project_memory.adapters.github import validate_repository


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginInput(InputModel):
    password: str = Field(min_length=1, max_length=256)


class ProjectInput(InputModel):
    name: str = Field(min_length=1, max_length=100)
    repository: str = Field(default="", max_length=140)
    workflows: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("repository")
    @classmethod
    def valid_repository(cls, value: str) -> str:
        return validate_repository(value) if value else ""

    @field_validator("workflows")
    @classmethod
    def valid_workflows(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 100 for value in values):
            raise ValueError("Workflow names must contain 1–100 characters")
        return list(dict.fromkeys(value.strip() for value in values))


class NoteInput(InputModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=100_000)


class QuestionInput(InputModel):
    question: str = Field(min_length=2, max_length=1000)
    use_live_checks: bool = False


class FeedbackInput(InputModel):
    answer_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    vote: int = Field(ge=-1, le=1)
