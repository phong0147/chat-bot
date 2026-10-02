"""Upload changed Markdown and resume unfinished operations on subsequent runs."""
import hashlib
import json
import logging
import time
from pathlib import Path

from .client import MAX_TOKENS, OVERLAP_TOKENS, OperationFailed, RetryableGeminiError
from .state import load, now, save
from .metrics import ESTIMATE_METHOD, ESTIMATE_NOTE, estimate_chunks

LOG = logging.getLogger("upload")


def read_articles(output):
    path = output / "state.json"
    if not path.exists():
        raise ValueError("No scrape state found. Run main.py --mode scrape first.")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("version") != 1 or not isinstance(state.get("articles"), dict):
        raise ValueError("Invalid scrape state.json.")
    articles = []
    for article_id, record in state["articles"].items():
        if not article_id.isdigit() or record.get("path") != f"articles/{article_id}.md":
            raise ValueError("Invalid article path in scrape state.")
        path = output / record["path"]
        if not path.resolve().is_relative_to(output.resolve()):
            raise ValueError("Article path escapes the data directory.")
        body = path.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if content_hash != record.get("content_hash"):
            raise ValueError(f"Article {article_id} changed locally; run scrape again before upload.")
        articles.append({**record, "id": article_id, "file": path})
    if not articles:
        raise ValueError("No articles available to upload.")
    return state, articles


def sync_upload(client, output: Path, store_name="", limit=0):
    report = {"started_at": now(), "status": "running", "added": 0, "updated": 0,
              "skipped": 0, "failed": 0, "retries": 0, "processed": 0, "files_embedded": 0,
              "estimated_chunks_embedded": 0, "chunk_estimate_method": ESTIMATE_METHOD,
              "chunk_estimate_note": ESTIMATE_NOTE,
              "embedded_chunks": None, "chunk_count_note": "Gemini does not expose the actual chunk count in document responses.",
              "chunking": {"max_tokens_per_chunk": MAX_TOKENS, "max_overlap_tokens": OVERLAP_TOKENS}}
    current_article = None
    state_path = output / "upload-state.json"
    try:
        scrape, articles = read_articles(output)
        state = load(state_path, scrape["source"], scrape["locale"])
        if store_name and state["store_name"] and store_name != state["store_name"]:
            raise ValueError("GEMINI_FILE_SEARCH_STORE differs from upload-state.json; refusing to mix stores.")
        state["store_name"] = client.ensure_store(state["store_name"] or store_name, state["owner"])
        save(state_path, state)
        store = state["store_name"]
        report["store_name"] = store
        documents = client.documents(store)
        # Only documents tagged as ours may be replaced or removed.
        catalog = {item["name"]: item for item in documents
                   if item["metadata"].get("ingest_owner") == state["owner"]}
        for article in articles[:limit or None]:
            article_id = article["id"]
            current_article = article_id
            previous = state["articles"].get(article_id)
            for attempt in range(3):
                try:
                    desired_hash = article["content_hash"]
                    pending = state["pending"].get(article_id)
                    if pending:
                        try:
                            item = client.wait(pending["operation"])
                        except OperationFailed:
                            del state["pending"][article_id]
                            save(state_path, state)
                            raise
                        catalog[item["name"]] = item
                        # A completed older operation is recovered, but not mistaken for today's hash.
                        del state["pending"][article_id]
                        save(state_path, state)
                    owned = [item for item in catalog.values() if item["metadata"].get("article_id") == article_id]
                    matching = [item for item in owned if item["metadata"].get("content_hash") == desired_hash
                                and item["state"] != "STATE_FAILED"]
                    matching.sort(key=lambda item: item["state"] != "STATE_ACTIVE")
                    if matching:
                        # The freshly fetched catalog already confirms active documents.
                        item = matching[0]
                        if item["state"] != "STATE_ACTIVE":
                            item = client.wait_document(item["name"])
                    else:
                        metadata = {"ingest_owner": state["owner"], "article_id": article_id,
                                    "content_hash": desired_hash, "article_url": article["url"]}
                        LOG.info("upload starting article=%s bytes=%s", article_id, article["file"].stat().st_size)
                        operation = client.start(store, article["file"], metadata)
                        if not operation.name:
                            raise RuntimeError("Upload operation has no name; rerun to reconcile remote documents.")
                        state["pending"][article_id] = {"operation": operation.name, "content_hash": desired_hash}
                        save(state_path, state)
                        LOG.info("indexing article=%s", article_id)
                        try:
                            item = client.wait(operation.name)
                        except OperationFailed:
                            del state["pending"][article_id]
                            save(state_path, state)
                            raise
                        del state["pending"][article_id]
                    if not item["name"].startswith(store + "/documents/") or item["state"] != "STATE_ACTIVE":
                        raise RuntimeError("Indexed document does not belong to the active store or is not ready.")
                    action = ("skipped" if previous and previous.get("uploaded_hash") == desired_hash
                              and previous.get("document_name") == item["name"] else "updated" if previous else "added")
                    state["articles"][article_id] = {"uploaded_hash": desired_hash, "document_name": item["name"],
                                                      "url": article["url"], "uploaded_at": now() if action != "skipped" else previous["uploaded_at"]}
                    save(state_path, state)
                    catalog[item["name"]] = item
                    # Delete superseded owned versions only after the replacement is indexed and saved.
                    for obsolete in owned:
                        if obsolete["name"] != item["name"]:
                            client.delete(obsolete["name"])
                            catalog.pop(obsolete["name"], None)
                    report[action] += 1
                    report["processed"] += 1
                    report["files_embedded"] += action != "skipped"
                    if action != "skipped":
                        report["estimated_chunks_embedded"] += estimate_chunks(
                            article["file"].read_text(encoding="utf-8"), MAX_TOKENS, OVERLAP_TOKENS)
                    LOG.info("upload %s article=%s", action, article_id)
                    break
                except RetryableGeminiError as exc:
                    if attempt == 2:
                        raise
                    report["retries"] += 1
                    LOG.warning("Temporary failure article=%s; reconcile and retry %s/2: %s",
                                article_id, attempt + 1, exc)
                    time.sleep(2 ** attempt)
                    # An upload may have succeeded remotely before its response
                    # was lost. Refresh the catalog and resume pending operations.
                    catalog = {item["name"]: item for item in client.documents(store)
                               if item["metadata"].get("ingest_owner") == state["owner"]}
        state["last_success_at"] = now()
        save(state_path, state)
        report["status"] = "success"
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["failed"] = 1
        report["error"] = str(exc)
        report["failed_article_id"] = current_article
        raise
    finally:
        report["finished_at"] = now()
        save(output / "upload-last-run.json", report)
        LOG.info("upload status=%s added=%s updated=%s skipped=%s failed=%s files_embedded=%s estimated_chunks_embedded=%s embedded_chunks=unavailable",
                 report["status"], report["added"], report["updated"], report["skipped"], report["failed"],
                 report["files_embedded"], report["estimated_chunks_embedded"])
