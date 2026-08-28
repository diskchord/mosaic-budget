from __future__ import annotations

import sys
from datetime import timedelta

import httpx

from .db import SessionLocal
from .models import WorkerHeartbeat
from .utils import ensure_utc, utcnow


def check_web() -> int:
    try:
        response = httpx.get("http://127.0.0.1:8000/health/live", timeout=5)
        return 0 if response.status_code == 200 else 1
    except Exception:
        return 1


def check_worker() -> int:
    db = SessionLocal()
    try:
        heartbeat = db.get(WorkerHeartbeat, "main")
        return 0 if heartbeat and ensure_utc(heartbeat.heartbeat_at) > utcnow() - timedelta(minutes=3) else 1
    except Exception:
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "web"
    raise SystemExit(check_worker() if mode == "worker" else check_web())
