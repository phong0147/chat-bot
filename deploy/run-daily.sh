#!/usr/bin/env bash
# Run once. Cron invokes this at 02:00 in the VPS timezone (Asia/Ho_Chi_Minh).
set -u
umask 027
cd /opt/script-chat-bot || exit 1
mkdir -p logs
exec >> logs/daily.log 2>&1
exec 9>data/.daily.lock
if ! flock -n 9; then
    printf '%s Another job is running; skipped.\n' "$(date -Is)"
    exit 0
fi
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '\n%s Daily sync started\n' "$started_at"
docker run --rm --name helpcenter-ingest-job \
    --cpus=1 --memory=512m --memory-swap=512m --pids-limit=128 \
    --env-file /opt/script-chat-bot/.env \
    --env TZ=Asia/Ho_Chi_Minh \
    --mount type=bind,source=/opt/script-chat-bot/data,target=/app/data \
    helpcenter-ingest:latest --mode sync --limit 0
result=$?
python3 - "$started_at" "$result" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

started = datetime.fromisoformat(sys.argv[1].replace('Z', '+00:00'))
exit_code = int(sys.argv[2])
report = {
    'started_at': started.isoformat(),
    'finished_at': datetime.now(timezone.utc).isoformat(),
    'status': 'success' if exit_code == 0 else 'failed',
    'exit_code': exit_code,
    'schedule': 'Daily 02:00 Asia/Ho_Chi_Minh',
    'command': 'python main.py --mode sync --limit 0',
}
for stage, filename in [('scrape', 'last-run.json'), ('upload', 'upload-last-run.json')]:
    path = Path('data') / filename
    summary = None
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
        stage_start = datetime.fromisoformat(data['started_at'].replace('Z', '+00:00'))
        if stage_start >= started:
            summary = {k: v for k, v in data.items() if k != 'changed_files'}
    report[stage] = summary
path = Path('data/daily-last-run.json')
temporary = path.with_suffix('.tmp')
temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
temporary.replace(path)
print(json.dumps(report))
PY
report_result=$?
printf '%s Daily sync finished; exit=%s report_exit=%s\n' "$(date -Is)" "$result" "$report_result"
if [ "$result" -eq 0 ] && [ "$report_result" -ne 0 ]; then
    result=$report_result
fi
exit "$result"
