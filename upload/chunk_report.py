"""Offline chunk audit: python -m upload.chunk_report --output data --report evidence/chunk-report.json."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .client import MAX_TOKENS, OVERLAP_TOKENS
from .metrics import ESTIMATE_METHOD, ESTIMATE_NOTE, estimate_chunks
from .pipeline import read_articles
from .state import save


def audit(output):
    manifest, articles = read_articles(output)
    path = output / "upload-state.json"
    uploaded = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if uploaded and (uploaded.get("source") != manifest["source"] or uploaded.get("locale") != manifest["locale"]):
        raise ValueError("Upload state does not match the source manifest")
    rows = []
    for article in articles:
        text = article["file"].read_text(encoding="utf-8")
        rows.append({
            "article_id": article["id"], "article_url": article["url"],
            "content_hash": article["content_hash"],
            "whitespace_tokens": len(text.split()),
            "estimated_chunks": estimate_chunks(text, MAX_TOKENS, OVERLAP_TOKENS),
            "upload_hash_matches_local_state": uploaded.get("articles", {}).get(article["id"], {}).get("uploaded_hash") == article["content_hash"],
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": manifest["source"], "locale": manifest["locale"],
        "files_in_manifest": len(rows),
        "files_matching_upload_state": sum(row["upload_hash_matches_local_state"] for row in rows),
        "remote_state_checked_live": False,
        "embedded_chunks": None,
        "estimated_chunks_in_manifest": sum(row["estimated_chunks"] for row in rows),
        "estimate_method": ESTIMATE_METHOD, "estimate_note": ESTIMATE_NOTE,
        "formula": "0 if N=0 else 1 + ceil(max(0, N-512) / 448)",
        "chunking": {"max_tokens_per_chunk": MAX_TOKENS, "max_overlap_tokens": OVERLAP_TOKENS},
        "articles": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--report", type=Path, default=Path("evidence/chunk-report.json"))
    args = parser.parse_args()
    report = audit(args.output)
    save(args.report, report)
    print(json.dumps({k: v for k, v in report.items() if k != "articles"}))


if __name__ == "__main__":
    main()
