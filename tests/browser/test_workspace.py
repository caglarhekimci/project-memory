"""Real browser -> HTTP -> SQLite -> cited answer flows, no external model required."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

pytestmark = pytest.mark.skipif(os.getenv("RUN_BROWSER") != "1", reason="Set RUN_BROWSER=1")


@pytest.fixture(scope="module")
def browser_app(tmp_path_factory):
    external = os.getenv("BROWSER_BASE_URL")
    if external:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            yield browser, external.rstrip("/")
            browser.close()
        return
    directory = tmp_path_factory.mktemp("browser")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PM_DEMO_MODE": "true",
        "PM_MODEL_BACKEND": "extractive",
        "PM_DATABASE_URL": f"sqlite:///{directory / 'browser.db'}",
        "PM_ORIGIN": origin,
    }
    log = (directory / "server.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "project_memory", "serve", "--port", str(port)],
        env=env,
        stdout=log,
        stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        for _ in range(100):
            try:
                if httpx.get(origin + "/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None:
                raise RuntimeError((directory / "server.log").read_text(encoding="utf-8"))
            time.sleep(0.1)
        else:
            raise RuntimeError("App did not become ready")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            yield browser, origin
            browser.close()
    finally:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        else:
            process.terminate()
        process.wait(timeout=10)
        log.close()


@pytest.fixture
def page(browser_app):
    browser, origin = browser_app
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.set_default_timeout(6000)
    page.goto(origin)
    page.get_by_label("Çalışma alanı parolası").fill("project-memory-demo")
    page.get_by_role("button", name="Çalışma alanına gir").click()
    expect(page.get_by_role("button", name="StockLedger", exact=False)).to_be_visible()
    page.get_by_role("button", name="StockLedger", exact=False).click()
    yield page
    context.close()


def test_answer_shows_real_citation_and_explicit_extractive_mode(page):
    page.get_by_label("Projen hakkında bir soru sor").fill("Redis neden kullanılıyor?")
    page.get_by_role("button", name="Kaynaklarda ara").click()
    expect(page.locator("#answer-panel")).to_contain_text("hız sınırlama")
    expect(page.locator("#answer-panel")).to_contain_text("Kaynak alıntıları")
    expect(page.locator("#evidence-list")).to_contain_text("Redis ve veri bütünlüğü")


def test_note_create_edit_and_delete_changes_visible_sources(page):
    page.get_by_role("button", name="Not ekle", exact=True).click()
    page.get_by_label("Not başlığı").fill("Tarayıcı kararı")
    page.get_by_label("Not içeriği").fill("Pusula hizmeti Ankara bölgesindedir.")
    page.get_by_role("button", name="Notu kaydet").click()
    page.get_by_role("tab", name="Kaynaklar").click()
    card = page.locator(".source-card").filter(has_text="Tarayıcı kararı")
    expect(card).to_be_visible()
    card.get_by_role("button", name="Düzenle").click()
    page.get_by_label("Not içeriği").fill("Pusula hizmeti İzmir bölgesindedir.")
    page.get_by_role("button", name="Notu kaydet").click()
    expect(card).to_contain_text("İzmir")
    card.get_by_role("button", name="Sil", exact=True).click()
    page.get_by_role("button", name="Kaynağı sil").click()
    expect(card).to_have_count(0)


def test_unknown_question_abstains_and_project_switch_clears_old_answer(page):
    page.get_by_label("Projen hakkında bir soru sor").fill("Satürn gezegeninin halkaları")
    page.get_by_role("button", name="Kaynaklarda ara").click()
    expect(page.locator("#answer-panel")).to_contain_text("Yeterli kanıt bulunamadı")
    page.get_by_role("button", name="ProcureFlow", exact=False).click()
    expect(page.locator("#answer-panel")).to_be_hidden()


def test_untrusted_source_is_rendered_as_text_without_script_execution(page):
    page.get_by_role("button", name="Not ekle", exact=True).click()
    page.get_by_label("Not başlığı").fill("Güvenli görünüm")
    page.get_by_label("Not içeriği").fill(
        '<img src=x onerror="window.injected=true"> Yörünge kararı'
    )
    page.get_by_role("button", name="Notu kaydet").click()
    page.get_by_role("tab", name="Kaynaklar").click()
    card = page.locator(".source-card").filter(has_text="Güvenli görünüm")
    expect(card).to_contain_text("<img")
    assert page.evaluate("window.injected") is None
    assert card.locator("img").count() == 0


def test_mobile_layout_and_keyboard_dialog(page):
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_role("button", name="Not ekle", exact=True).click()
    expect(page.get_by_role("dialog", name="Yeni not")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog", name="Yeni not")).to_be_hidden()
    os.makedirs("test-results", exist_ok=True)
    page.screenshot(path="test-results/workspace-mobile.png", full_page=True)


def test_desktop_workspace_screenshot_and_logout(page):
    os.makedirs("test-results", exist_ok=True)
    page.screenshot(path="test-results/workspace-desktop.png", full_page=True)
    page.get_by_role("button", name="Oturumu kapat").click()
    expect(page.get_by_role("button", name="Çalışma alanına gir")).to_be_visible()


def test_mobile_has_accessible_logout(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Oturumu kapat").click()
    expect(page.get_by_role("button", name="Çalışma alanına gir")).to_be_visible()


def test_desktop_and_mobile_have_no_axe_wcag_a_aa_violations(page):
    page.evaluate(Path("node_modules/axe-core/axe.min.js").read_text(encoding="utf-8"))
    for width, height in [(1440, 1000), (390, 844)]:
        page.set_viewport_size({"width": width, "height": height})
        result = page.evaluate("""async () => await axe.run(document, {
            runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}
        })""")
        failures = [
            {"id": item["id"], "nodes": [n["target"] for n in item["nodes"]]}
            for item in result["violations"]
        ]
        Path("test-results").mkdir(exist_ok=True)
        Path("test-results/axe-violations.json").write_text(
            __import__("json").dumps(failures, indent=2), encoding="utf-8"
        )
        assert failures == []
