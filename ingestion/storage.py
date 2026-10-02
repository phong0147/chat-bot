"""Read scrape state, hash content, and write local files atomically."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".writing-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path: Path, value: dict) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_state(path: Path, source: str, locale: str) -> dict:
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if (state.get("version") != 1 or state.get("source") != source
                or state.get("locale") != locale or not isinstance(state.get("articles"), dict)):
            raise ValueError("Incompatible state.json; use a different output directory")
    else:
        state = {"version": 1, "source": source, "locale": locale, "articles": {}}
    return state
