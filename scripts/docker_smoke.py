"""Disposable Docker smoke: durable note revisions and owner session survive replacement."""

import argparse
import json
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "verify"])
    parser.add_argument("--url", default="http://127.0.0.1:4180")
    args = parser.parse_args()
    state_file = Path("test-results/docker-state.json")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    cookie = ""

    def request(path, method="GET", body=None):
        headers = {"Origin": args.url, "Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        req = Request(
            args.url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method,
        )
        with urlopen(req, timeout=30) as response:
            raw = response.read()
            return (json.loads(raw) if raw else None), response.headers

    if args.phase == "prepare":
        try:
            request("/api/projects")
            raise AssertionError("Owner authentication was bypassed")
        except HTTPError as error:
            assert error.code == 401
        _, headers = request("/api/login", "POST", {"password": "project-memory-demo"})
        parsed = SimpleCookie()
        parsed.load(headers["Set-Cookie"])
        cookie = "pm_session=" + parsed["pm_session"].value
        project, _ = request("/api/projects", "POST", {"name": "Docker durable evidence"})
        base = f"/api/projects/{project['id']}"
        note, _ = request(
            base + "/notes", "POST", {"title": "Kalıcılık", "body": "Kutup istasyonu İzmir."}
        )
        request(
            base + "/notes/" + note["source_id"],
            "PUT",
            {"title": "Kalıcılık", "body": "Kutup istasyonu Ankara."},
        )
        answer, _ = request(base + "/answer", "POST", {"question": "Kutup istasyonu"})
        assert "Ankara" in answer["claims"][0]["text"]
        assert answer["mode"] == "extractive"
        state_file.write_text(
            json.dumps({"cookie": cookie, "project": project["id"], "source": note["source_id"]}),
            encoding="utf-8",
        )
        state_file.chmod(0o600)
        print("Prepared durable note, source revision and owner session; no credentials printed.")
    else:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        cookie = state["cookie"]
        sources, _ = request(f"/api/projects/{state['project']}/sources")
        source = next(s for s in sources if s["id"] == state["source"])
        assert source["version_count"] == 2
        assert source["body"] == "Kutup istasyonu Ankara."
        answer, _ = request(
            f"/api/projects/{state['project']}/answer", "POST", {"question": "Kutup istasyonu"}
        )
        assert "Ankara" in answer["claims"][0]["text"]
        assert all("İzmir" not in e["chunk"]["text"] for e in answer["evidence"])
        print(
            "Docker persistence passed: original owner session, two source revisions "
            "and active cited answer survived replacement."
        )


if __name__ == "__main__":
    main()
