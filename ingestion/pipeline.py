"""Coordinate article fetching, conversion, persistence, and scrape reports."""
import logging
from pathlib import Path

from .converter import article_markdown
from .scraper import ZendeskClient
from .storage import atomic_write, digest, load_state, now, write_json

LOG = logging.getLogger("scraper")


def sync(client: ZendeskClient, output: Path, limit=30, minimum=30, include_query="YouTube") -> dict:
    output.mkdir(parents=True, exist_ok=True)
    report = {"started_at": now(), "status": "running", "added": 0, "updated": 0,
              "skipped": 0, "processed": 0, "changed_files": [],
              "source": client.source, "locale": client.locale, "limit": limit}
    state_path = output / "state.json"
    try:
        state = load_state(state_path, client.source, client.locale)
        records = state["articles"]
        for article in client.articles(include_query):
            if article.get("draft"):
                continue
            article_id = str(int(article["id"]))
            markdown = article_markdown(article)
            content_hash = digest(markdown)
            relative_path = f"articles/{article_id}.md"
            path = output / relative_path
            previous = records.get(article_id)
            file_matches = path.exists() and digest(path.read_text(encoding="utf-8")) == content_hash
            if previous and previous.get("content_hash") == content_hash and file_matches:
                action = "skipped"
            else:
                action = "updated" if previous else "added"
                atomic_write(path, markdown)
                report["changed_files"].append(relative_path)
            records[article_id] = {
                "id": article_id, "title": article["title"], "url": article["html_url"],
                "source_updated_at": article.get("updated_at"), "content_hash": content_hash,
                "path": relative_path,
            }
            report[action] += 1
            report["processed"] += 1
            LOG.info("%s article=%s path=%s", action, article_id, relative_path)
            if limit and report["processed"] >= limit:
                break
        if report["processed"] < minimum:
            raise ValueError(f"Only {report['processed']} articles retrieved; minimum required is {minimum}")
        state["last_success_at"] = now()
        write_json(state_path, state)
        report["status"] = "success"
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        # Markdown already saved is safe to retry; state is committed only on success.
        raise
    finally:
        report["finished_at"] = now()
        write_json(output / "last-run.json", report)
        LOG.info("status=%s added=%s updated=%s skipped=%s processed=%s",
                 report["status"], report["added"], report["updated"], report["skipped"], report["processed"])
