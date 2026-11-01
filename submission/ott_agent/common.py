"""Local serialization and explicit event-time conventions."""
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))
def ts(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None
def iso(value):
    return value.astimezone(UTC).isoformat(timespec='microseconds').replace('+00:00', 'Z')
def day(value):
    return value.astimezone(IST).date()
def event_time(event):
    lag = (ts(event['sent_at']) - ts(event['occurred_at'])).total_seconds()
    return ts(event['received_at']) - timedelta(seconds=max(0, lag)), lag
def jsonl(path):
    with Path(path).open(encoding='utf-8-sig') as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)
def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))
def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
def write_jsonl(path, rows):
    with Path(path).open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
