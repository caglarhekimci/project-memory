import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Project Memory · Proje Hafızası")
    parser.add_argument("command", choices=["serve"])
    parser.add_argument(
        "--demo", action="store_true", help="Use explicit sample data and demo password"
    )
    parser.add_argument(
        "--ollama", action="store_true", help="Use local Ollama embeddings and generation"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4180)
    args = parser.parse_args()
    if args.demo:
        os.environ["PM_DEMO_MODE"] = "true"
    if args.ollama:
        os.environ["PM_MODEL_BACKEND"] = "ollama"
    from project_memory.web.app import create_app

    try:
        app = create_app()
    except ValueError:
        parser.exit(
            2, "Configuration invalid. Set PM_APP_PASSWORD (12+ characters), or use --demo.\n"
        )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
