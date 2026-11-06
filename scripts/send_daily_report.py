"""Run from project root with .venv Python; used by Windows Task Scheduler."""
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.email_reports import send_report  # noqa: E402

if __name__ == '__main__':
    try:
        result = send_report()
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S} Email sent: {result}")
    except Exception as exc:
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S} Report failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
