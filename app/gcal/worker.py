"""סבב סנכרון. ברירת מחדל כל 15 דקות.

מהשורש:

    python scripts/gcal_sync_worker.py
    python scripts/gcal_sync_worker.py --once

Worker התזכורות מפעיל את אותו סבב, כדי שבית שמריץ תהליך אחד יקבל גם את היומן.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time


def sync_interval_seconds() -> int:
    raw = (os.getenv("GCAL_SYNC_SECONDS") or "900").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 900
    return max(60, min(value, 24 * 60 * 60))


def run_once(*, today=None) -> int:
    from app.gcal.sync import sync_enabled

    results = sync_enabled(today=today)
    failed = 0
    for item in results:
        if item.get("last_error"):
            failed += 1
            print(f"gcal source {item.get('id')} failed", file=sys.stderr)
        else:
            stats = item.get("sync") or {}
            print(
                "gcal source {id} ok inserted={inserted} updated={updated} deleted={deleted}".format(
                    id=item.get("id"),
                    inserted=stats.get("inserted", 0),
                    updated=stats.get("updated", 0),
                    deleted=stats.get("deleted", 0),
                )
            )
    return failed


def run_loop(stop: threading.Event | None = None, interval: int | None = None) -> None:
    interval = sync_interval_seconds() if interval is None else max(60, int(interval))
    stop = stop or threading.Event()
    from app import app

    print(f"gcal sync worker started, every {interval}s")
    while not stop.is_set():
        started = time.monotonic()
        try:
            with app.app_context():
                run_once()
        except Exception as exc:
            print(f"gcal sync failed: {type(exc).__name__}", file=sys.stderr)
        remaining = interval - (time.monotonic() - started)
        if stop.wait(max(0.0, remaining)):
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="סנכרון חד-כיווני מיומן גוגל")
    parser.add_argument("--once", action="store_true", help="סבב אחד ואז יציאה")
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="שניות בין סבבים (ברירת מחדל GCAL_SYNC_SECONDS או 900)",
    )
    args = parser.parse_args(argv)
    from app import app

    with app.app_context():
        if args.once:
            run_once()
            return 0
        try:
            run_loop(interval=args.interval)
        except KeyboardInterrupt:
            print("gcal sync worker stopped")
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
