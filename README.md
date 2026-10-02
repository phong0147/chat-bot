# Chat bot

Python ingestion for the OptiSigns Help Center and a grounded assistant in Google AI Studio. Markdown preserves headings, code blocks and relative links, with an `Article URL:` on every file.

## Setup and run

Python 3.10+; Docker uses 3.13. Create and activate a virtual environment, install dependencies, and copy `.env.sample` to `.env` with your `GEMINI_API_KEY`:

```bash
python -m pip install -r requirements.txt
python main.py --mode sync --limit 30
python -m unittest discover -s tests -q
```

Use `--mode scrape` or `--mode upload` for one stage, and `--limit 0` for the full source. Preserve `data/` across runs: hashes detect changes; saved operations and remote metadata support recovery. Uploads use the Python API. Only changed/missing files are indexed; old versions are removed after replacements are active. Temporary failures have bounded retries.

## Docker and daily job

```bash
docker build -t helpcenter-ingest .
docker run --rm --env-file .env -v "$PWD/data:/app/data" helpcenter-ingest --mode sync --limit 0
```

VPS: `/opt/script-chat-bot`, daily **02:00 Asia/Ho_Chi_Minh**. [Operations](deploy/README.md). Evidence snapshots: [completed run](evidence/vps-completion-run.json), [last run](evidence/vps-daily-last-run.json), [416 active documents](evidence/store-verification.json), [VPS tests](evidence/vps-tests.txt), [local tests](evidence/local-tests.txt). Live logs: `logs/daily.log`; final report: `data/daily-last-run.json` on the VPS.

## Assistant and chunking

Follow [AI Studio setup](playground/README.md) using the [verbatim system prompt](playground/system-prompt.txt). The helper queries the uploaded store from the existing Playground agent; no separate web application is required.

[YouTube question and cited answer — screenshot](result.png)

Managed chunking: 512 whitespace tokens, overlap 64. Inline base64 images become captions pointing to the source. Logs distinguish confirmed files from locally **estimated** chunks; `embedded_chunks` stays `null` because the Document API does not expose the actual count. This requirement is partially fulfilled, not claimed complete. [Audit method and limitations](upload/README.md).

Source-deletion sync is out of scope. Never commit `.env` or keys. Avoid concurrent local/VPS writers to the same store.
