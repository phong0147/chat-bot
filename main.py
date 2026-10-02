"""Run scraping, Gemini upload, or both sequentially."""
import logging
import os
from pathlib import Path

from cli import parse_args
from ingestion.pipeline import sync
from ingestion.scraper import ZendeskClient

LOG = logging.getLogger("job")


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.StreamHandler(), logging.FileHandler(args.output / "scrape.log", encoding="utf-8")])
    for name in ("httpx", "httpcore", "google.genai"):
        logging.getLogger(name).setLevel(logging.WARNING)
    # Same lock as the old scraper: upload and scrape must not race on these files.
    lock_path = args.output / ".scrape.lock"
    try:
        lock = lock_path.open("x", encoding="utf-8")
    except FileExistsError:
        LOG.error("Another run may be active. Check %s before removing a stale lock.", lock_path)
        return 1
    client = None
    try:
        with lock:
            lock.write(str(os.getpid()))
        if args.mode in ("upload", "sync"):
            from upload.config import load_settings
            from upload.client import GeminiStore
            from upload.pipeline import sync_upload
            settings = load_settings(Path(__file__).resolve().parent)
            client = GeminiStore(settings)
        if args.mode in ("scrape", "sync"):
            sync(ZendeskClient(args.source, args.locale), args.output, args.limit, args.minimum, args.include_query)
        if client is not None:
            sync_upload(client, args.output, settings.store_name, args.upload_limit)
        return 0
    except Exception as exc:
        # Avoid SDK tracebacks containing request or credential details.
        LOG.error("Job failed: %s", exc)
        return 1
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
