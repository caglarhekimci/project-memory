"""Catch stale-success claims, unsafe imports and upstream API errors."""

import httpx
import pytest

from project_memory.adapters.github import GitHubClient, validate_repository
from project_memory.application.checks import reconcile_checks
from project_memory.domain.models import ProviderUnavailable

SHA = "b" * 40
OLD = "a" * 40


def run(name, sha=SHA, conclusion="success", status="completed", run_id=1):
    return {
        "id": run_id,
        "name": name,
        "head_sha": sha,
        "status": status,
        "conclusion": conclusion,
        "html_url": f"https://github.com/e/r/actions/runs/{run_id}",
    }


def test_old_failure_is_separate_from_success_at_current_head():
    result = reconcile_checks(
        SHA,
        ("CI", "Docker"),
        [run("CI"), run("Docker", run_id=2), run("Docker", OLD, "failure", run_id=3)],
    )
    assert result.state == "success"
    assert len(result.checks) == 2
    assert all(check.head_sha == SHA for check in result.checks)
    assert result.historical_failures == 1


@pytest.mark.parametrize(
    "conclusion,state",
    [("failure", "failure"), ("cancelled", "unknown"), ("skipped", "unknown"), (None, "pending")],
)
def test_non_successful_check_never_becomes_success(conclusion, state):
    status = "in_progress" if conclusion is None else "completed"
    result = reconcile_checks(SHA, ("CI",), [run("CI", conclusion=conclusion, status=status)])
    assert result.state == state


def test_missing_expected_workflow_is_unknown_even_with_other_success():
    assert reconcile_checks(SHA, ("CI", "Docker"), [run("CI")]).state == "unknown"


def test_no_workflow_configuration_is_unknown():
    assert reconcile_checks(SHA, (), [run("CI")]).state == "unknown"


def test_newer_attempt_wins_for_same_workflow_at_same_head():
    result = reconcile_checks(
        SHA, ("CI",), [run("CI", conclusion="failure", run_id=1), run("CI", run_id=2)]
    )
    assert result.state == "success"
    assert result.checks[0].url.endswith("/2")


@pytest.mark.parametrize(
    "repository",
    [
        "../secret",
        "https://evil.test/a",
        "owner/repo/extra",
        "owner/repo?x=1",
        "owner/.git",
        "owner/repo%2fetc",
    ],
)
def test_repository_identity_rejects_paths_and_urls(repository):
    with pytest.raises(ValueError):
        validate_repository(repository)


def test_github_error_does_not_expose_upstream_body_or_credentials():
    client = GitHubClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(403, json={"message": "PRIVATE_TOKEN_VALUE"})
            )
        )
    )
    with pytest.raises(ProviderUnavailable) as error:
        client.snapshot("owner/repo", ("CI",))
    assert "PRIVATE_TOKEN_VALUE" not in str(error.value)


def test_snapshot_resolves_default_branch_then_uses_its_exact_head():
    def handle(request):
        assert request.url.host == "api.github.com"
        path = request.url.path
        if path == "/repos/owner/repo":
            return httpx.Response(200, json={"default_branch": "main"})
        if path.endswith("/branches/main"):
            return httpx.Response(200, json={"commit": {"sha": SHA}})
        if path.endswith("/actions/runs"):
            return httpx.Response(200, json={"workflow_runs": [run("CI")]})
        raise AssertionError(f"Unexpected request {path}")

    result = GitHubClient(httpx.Client(transport=httpx.MockTransport(handle))).snapshot(
        "owner/repo", ("CI",)
    )
    assert result.state == "success"
    assert result.head_sha == SHA
    assert result.observed_at


def test_repository_documents_are_downloaded_at_immutable_ref():
    import base64

    def handle(request):
        path = request.url.path
        if path == "/repos/owner/repo":
            return httpx.Response(200, json={"default_branch": "main", "private": False})
        if path.endswith("/branches/main"):
            return httpx.Response(200, json={"commit": {"sha": SHA}})
        if "/git/trees/" in path:
            assert path.endswith(SHA)
            return httpx.Response(
                200,
                json={
                    "truncated": False,
                    "tree": [
                        {"type": "blob", "path": "README.md"},
                        {"type": "blob", "path": "docs/architecture.md"},
                        {"type": "blob", "path": ".env"},
                    ],
                },
            )
        if "/contents/" in path:
            assert request.url.params["ref"] == SHA
            return httpx.Response(
                200,
                json={
                    "encoding": "base64",
                    "content": base64.b64encode(b"# Decision\nRedis limits requests.").decode(),
                },
            )
        raise AssertionError(path)

    documents = GitHubClient(httpx.Client(transport=httpx.MockTransport(handle))).documents(
        "owner/repo"
    )
    assert len(documents) == 2
    assert all(d.revision == SHA and SHA in d.url for d in documents)
