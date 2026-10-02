"""Command-line options for the Help Center ingestion job."""
import argparse
from pathlib import Path
import re
from urllib.parse import urlsplit

from ingestion.scraper import DEFAULT_SOURCE


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Scrape Help Center articles and upload Markdown to Gemini File Search.")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--locale", default="en-us")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "data")
    parser.add_argument("--limit", type=int, default=30, help="Maximum articles; 0 means all")
    parser.add_argument("--minimum", type=int, default=30, help="Fail if fewer articles are retrieved")
    parser.add_argument("--include-query", default="YouTube", help="Include one matching article first; empty disables")
    parser.add_argument("--mode", choices=("scrape", "upload", "sync"), default="scrape", help="scrape only (default), upload saved files, or both")
    parser.add_argument("--upload-limit", type=int, default=0, help="Maximum saved articles checked for upload; 0 means all")
    args = parser.parse_args(argv)
    if args.upload_limit < 0:
        parser.error("upload-limit cannot be negative")
    if args.limit < 0 or args.minimum < 1 or (args.limit and args.limit < args.minimum):
        parser.error("limit must be 0 or >= minimum; minimum must be positive")
    if not re.fullmatch(r"[a-zA-Z0-9-]+", args.locale):
        parser.error("invalid locale")
    source_parts = urlsplit(args.source)
    if source_parts.scheme != "https" or not source_parts.netloc or source_parts.path not in ("", "/") or source_parts.query or source_parts.fragment:
        parser.error("source must be an HTTPS origin, e.g. https://support.optisigns.com")
    return args
