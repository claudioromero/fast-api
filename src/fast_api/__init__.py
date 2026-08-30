from pathlib import Path

import uvicorn

APP_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    uvicorn.run("main:app", app_dir=str(APP_DIR), host="0.0.0.0", port=8000)