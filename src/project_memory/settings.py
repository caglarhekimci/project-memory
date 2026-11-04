from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEMO_PASSWORD = "project-memory-demo"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PM_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///data/memory.db"
    demo_mode: bool = False
    app_password: SecretStr = SecretStr("")
    origin: str = "http://127.0.0.1:4180"
    model_backend: Literal["extractive", "ollama"] = "extractive"
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3.5:9b"
    embedding_model: str = "bge-m3"
    dense_threshold: float = Field(default=0.4, ge=-1, le=1)
    github_token: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def validate_runtime(self) -> "Settings":
        parsed = urlparse(self.origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("PM_ORIGIN must be an HTTP origin")
        self.origin = self.origin.rstrip("/")
        password = self.app_password.get_secret_value()
        if not self.demo_mode and (
            len(password) < 12 or password == DEMO_PASSWORD or password.startswith("change-this")
        ):
            raise ValueError(
                "Set a private PM_APP_PASSWORD of at least 12 characters for live mode"
            )
        if self.demo_mode and not password:
            self.app_password = SecretStr(DEMO_PASSWORD)
        return self
