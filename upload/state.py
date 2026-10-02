"""Persist upload progress independently of the scraper's state."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".upload-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load(path: Path, source: str, locale: str) -> dict:
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if (value.get("version") != 1 or value.get("source") != source
                or value.get("locale") != locale or not value.get("owner")
                or not isinstance(value.get("articles"), dict)
                or not isinstance(value.get("pending"), dict)):
            raise ValueError("Incompatible upload-state.json; use the matching data directory.")
        return value
    value = {"version": 1, "source": source, "locale": locale,
             "owner": uuid.uuid4().hex, "store_name": None, "articles": {}, "pending": {}}
    save(path, value)
    return value
