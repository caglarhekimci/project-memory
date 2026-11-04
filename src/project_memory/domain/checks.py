from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkflowCheck:
    name: str
    state: str
    head_sha: str
    url: str


@dataclass(frozen=True, slots=True)
class CheckSnapshot:
    state: str
    head_sha: str
    checks: tuple[WorkflowCheck, ...]
    historical_failures: int
    observed_at: str
    repository: str = ""
    branch: str = ""


def reconcile_checks(
    head_sha: str,
    expected: tuple[str, ...],
    runs: list[dict[str, Any]],
    repository: str = "",
    branch: str = "",
) -> CheckSnapshot:
    checks: list[WorkflowCheck] = []
    for name in expected:
        matching = [r for r in runs if r.get("name") == name and r.get("head_sha") == head_sha]
        if not matching:
            checks.append(WorkflowCheck(name, "unknown", head_sha, ""))
            continue
        latest = max(matching, key=lambda r: int(r.get("id", 0)))
        conclusion = latest.get("conclusion")
        if latest.get("status") != "completed":
            state = "pending"
        elif conclusion == "success":
            state = "success"
        elif conclusion in {"failure", "timed_out", "startup_failure", "action_required"}:
            state = "failure"
        else:
            state = "unknown"
        raw_url = str(latest.get("html_url", ""))
        url = raw_url if raw_url.startswith("https://github.com/") else ""
        checks.append(WorkflowCheck(name, state, head_sha, url))
    states = {c.state for c in checks}
    overall = (
        "failure"
        if "failure" in states
        else (
            "pending"
            if "pending" in states
            else ("success" if checks and states == {"success"} else "unknown")
        )
    )
    historical = sum(
        1 for r in runs if r.get("head_sha") != head_sha and r.get("conclusion") == "failure"
    )
    return CheckSnapshot(
        overall,
        head_sha,
        tuple(checks),
        historical,
        datetime.now(UTC).isoformat(),
        repository,
        branch,
    )
