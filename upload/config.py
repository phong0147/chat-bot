"""Load Gemini credentials from the project .env or process environment."""
from dataclasses import dataclass, field
import os
from pathlib import Path
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    store_name: str = ""
    timeout: int = 300


def load_settings(project_dir: Path) -> Settings:
    load_dotenv(project_dir / ".env", override=False)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or key.lower() in {"your_api_key", "replace_me"}:
        raise ValueError("Set GEMINI_API_KEY in the project .env before upload.")
    try:
        timeout = int(os.environ.get("GEMINI_UPLOAD_TIMEOUT", "300"))
    except ValueError:
        raise ValueError("GEMINI_UPLOAD_TIMEOUT must be an integer in seconds.") from None
    if timeout < 1:
        raise ValueError("GEMINI_UPLOAD_TIMEOUT must be positive.")
    return Settings(key, os.environ.get("GEMINI_FILE_SEARCH_STORE", "").strip(), timeout)
