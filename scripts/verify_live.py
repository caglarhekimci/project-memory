"""Opt-in real public-GitHub + local-model + browser verification in a temporary database."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


def main() -> None:
    results = Path("test-results")
    results.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=results) as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "PM_DEMO_MODE": "true",
            "PM_MODEL_BACKEND": "ollama",
            "PM_DATABASE_URL": f"sqlite:///{Path(directory).resolve() / 'live.db'}",
            "PM_ORIGIN": origin,
        }
        with (results / "live-server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "project_memory", "serve", "--port", str(port)],
                env=env,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            try:
                with httpx.Client(
                    base_url=origin, headers={"Origin": origin}, timeout=180
                ) as client:
                    for _ in range(100):
                        try:
                            if client.get("/healthz").status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.1)
                    assert client.get("/api/projects").status_code == 401
                    assert (
                        client.post(
                            "/api/login", json={"password": "project-memory-demo"}
                        ).status_code
                        == 200
                    )
                    projects = client.get("/api/projects").json()
                    ledger = next(p for p in projects if p["name"] == "StockLedger")
                    base = f"/api/projects/{ledger['id']}"
                    sync = client.post(base + "/sync")
                    assert sync.status_code == 200, sync.text
                    sources = client.get(base + "/sources").json()
                    imported = [s for s in sources if s["kind"] == "repository"]
                    assert imported and len({s["revision"] for s in imported}) == 1
                    answer = client.post(
                        base + "/answer", json={"question": "Redis hangi amaçla kullanılıyor?"}
                    ).json()
                    assert answer["mode"] == "llm", answer
                    assert answer["retrieval_mode"] == "hybrid", answer
                    assert answer["claims"] and answer["evidence"]
                    snapshots = []
                    for project in projects:
                        response = client.post(f"/api/projects/{project['id']}/checks")
                        assert response.status_code == 200, response.text
                        snapshots.append(response.json())
                    report = {
                        "checked_at": datetime.now(UTC).isoformat(),
                        "evidence": "real browser/HTTP/SQLite, public GitHub API and local Ollama",
                        "sync": sync.json(),
                        "import_revision": imported[0]["revision"],
                        "answer_mode": answer["mode"],
                        "retrieval_mode": answer["retrieval_mode"],
                        "claims": answer["claims"],
                        "snapshots": snapshots,
                    }
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    page = browser.new_page(viewport={"width": 1440, "height": 1050})
                    page.goto(origin)
                    page.get_by_label("Çalışma alanı parolası").fill("project-memory-demo")
                    page.get_by_role("button", name="Çalışma alanına gir").click()
                    page.get_by_role("button", name="StockLedger", exact=False).click()
                    page.get_by_label("Projen hakkında bir soru sor").fill(
                        "Redis hangi amaçla kullanılıyor?"
                    )
                    page.get_by_role("button", name="Kaynaklarda ara").click()
                    expect(page.locator("#answer-panel")).to_contain_text(
                        "Kaynaklı yanıt", timeout=120_000
                    )
                    page.get_by_role("button", name="GitHub’ı kontrol et", exact=False).click()
                    expect(page.locator("#check-results .check-sha")).to_be_visible(timeout=30_000)
                    images = Path("docs/images")
                    images.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(images / "workspace-desktop.png"), full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=str(images / "workspace-mobile.png"), full_page=True)
                    browser.close()
                output = Path("docs/evidence/live-integration.json")
                output.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    json.dumps(
                        {
                            "evidence": report["evidence"],
                            "documents": len(imported),
                            "answer_mode": answer["mode"],
                            "retrieval_mode": answer["retrieval_mode"],
                            "checks": [
                                {
                                    "repository": s["repository"],
                                    "state": s["state"],
                                    "sha": s["head_sha"],
                                }
                                for s in snapshots
                            ],
                        }
                    )
                )
            finally:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True
                    )
                else:
                    process.terminate()
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
