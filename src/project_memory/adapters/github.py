import base64
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from project_memory.adapters.http import bounded_json
from project_memory.domain.checks import CheckSnapshot, reconcile_checks
from project_memory.domain.models import ProviderUnavailable, SourceInput

REPOSITORY_PATTERN = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z"
)
COMMIT_PATTERN = re.compile(r"[a-f0-9]{40}\Z")


def validate_repository(repository: str) -> str:
    if not REPOSITORY_PATTERN.fullmatch(repository) or ".." in repository:
        raise ValueError("Depo owner/name biçiminde olmalı.")
    return repository


class GitHubClient:
    ORIGIN = "https://api.github.com"

    def __init__(self, client: httpx.Client | None = None, token: str = "") -> None:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "project-memory/1.0"}
        if token:
            headers["Authorization"] = "Bearer " + token
        self.client = client or httpx.Client(headers=headers, timeout=20, follow_redirects=False)

    def _get(self, path: str) -> dict[str, Any]:
        result = bounded_json(self.client, "GET", self.ORIGIN + path)
        if not isinstance(result, dict):
            raise ProviderUnavailable("GitHub beklenen veri biçimini döndürmedi.")
        return result

    def _head(self, repository: str) -> tuple[str, str]:
        validate_repository(repository)
        info = self._get(f"/repos/{repository}")
        if info.get("private"):
            raise ProviderUnavailable("Bu sürüm yalnızca herkese açık depoları içe aktarır.")
        branch = info.get("default_branch")
        if not isinstance(branch, str) or not branch or len(branch) > 200:
            raise ProviderUnavailable("Varsayılan dal belirlenemedi.")
        data = self._get(f"/repos/{repository}/branches/{quote(branch, safe='')}")
        sha = data.get("commit", {}).get("sha", "")
        if not isinstance(sha, str) or not COMMIT_PATTERN.fullmatch(sha):
            raise ProviderUnavailable("Geçerli commit bilgisi alınamadı.")
        return branch, sha

    def snapshot(self, repository: str, workflows: tuple[str, ...]) -> CheckSnapshot:
        branch, sha = self._head(repository)
        data = self._get(
            f"/repos/{repository}/actions/runs?per_page=100&branch={quote(branch, safe='')}"
        )
        runs = data.get("workflow_runs")
        if not isinstance(runs, list) or not all(isinstance(r, dict) for r in runs):
            raise ProviderUnavailable("GitHub kontrol listesi alınamadı.")
        return reconcile_checks(sha, workflows, runs, repository, branch)

    def documents(self, repository: str) -> list[SourceInput]:
        _, sha = self._head(repository)
        tree = self._get(f"/repos/{repository}/git/trees/{sha}?recursive=1")
        if tree.get("truncated") or not isinstance(tree.get("tree"), list):
            raise ProviderUnavailable("Depo dosya listesi eksik; kaynaklar değiştirilmedi.")
        paths: list[str] = []
        for entry in tree["tree"]:
            path = entry.get("path", "")
            if (
                entry.get("type") == "blob"
                and isinstance(path, str)
                and (path.lower() == "readme.md" or path.startswith("docs/"))
                and path.lower().endswith(".md")
                and len(path) <= 400
                and all(part not in {"", ".", ".."} for part in path.split("/"))
            ):
                paths.append(path)
        paths.sort(key=lambda p: (p.lower() != "readme.md", p))
        documents: list[SourceInput] = []
        for path in paths[:12]:
            content = self._get(f"/repos/{repository}/contents/{quote(path, safe='/')}?ref={sha}")
            if content.get("encoding") != "base64" or not isinstance(content.get("content"), str):
                raise ProviderUnavailable("Belge içeriği okunamadı; içe aktarma tamamlanmadı.")
            try:
                body = base64.b64decode(content["content"], validate=False).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                raise ProviderUnavailable("Belge UTF-8 metni olarak okunamadı.") from None
            if not body.strip() or len(body) > 100_000:
                continue
            documents.append(
                SourceInput(
                    path,
                    path.rsplit("/", 1)[-1],
                    body,
                    f"https://github.com/{repository}/blob/{sha}/{quote(path, safe='/')}",
                    sha,
                    datetime.now(UTC),
                    "repository",
                )
            )
        return documents
