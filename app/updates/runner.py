"""תהליך העדכון עצמו. רץ מנותק מהאפליקציה, וכותב התקדמות לקובץ."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.updates.envconfig import load_config
from app.updates.errors import UpdateError
from app.updates.flow import Plan, execute_update
from app.updates.gitops import LiveOps
from app.updates.github_api import fetch_latest
from app.updates.store import read_json, release_lock, write_status
from app.updates.version import installed_version, normalize_version, tag_matches_version, validate_tag


def _mark_failed(status: Path, message: str, step: str) -> None:
    current = read_json(status) or {}
    current.update({
        "state": "failed",
        "step": step,
        "message": message,
        "error": message,
        "current": current.get("current") or installed_version(),
    })
    try:
        write_status(status, current)
    except OSError:
        return


def run_job(target: str, tag: str, mode: str, status: Path) -> None:
    version = normalize_version(target)
    checked_tag = validate_tag(tag)
    if mode not in {"git", "hook"}:
        raise UpdateError("מצב עדכון לא תקין.", step="start")
    if not tag_matches_version(checked_tag, version):
        raise UpdateError("תג הגרסה לא תואם למספר.", step="version")
    cfg = load_config()
    release = fetch_latest(cfg.repo, cfg.token)
    if release is None or release.version != version or release.tag != checked_tag:
        raise UpdateError("הגרסה שביקשתם לא תואמת למה שמפורסם ב-GitHub.", step="fetch")
    if mode == "git" and not cfg.restart_command:
        raise UpdateError("לא הוגדרה פקודת הפעלה מחדש.", step="restart")
    ops = LiveOps(cfg, status, version)
    ops.write(
        state="running",
        step="start",
        message="מתחילים את העדכון",
        target=version,
        pid=os.getpid(),
        current=installed_version(),
    )
    # התג שנבדק מול GitHub, לא מחרוזת שבאה מהדפדפן.
    execute_update(ops, Plan(mode=mode, tag=release.tag, version=release.version))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="heb-cal-update")
    parser.add_argument("--target", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--mode", required=True, choices=["git", "hook"])
    parser.add_argument("--status", required=True)
    args = parser.parse_args(argv)
    status = Path(args.status)
    try:
        run_job(args.target, args.tag, args.mode, status)
    except UpdateError as exc:
        _mark_failed(status, exc.message, exc.step)
    except Exception:
        _mark_failed(status, "תקלה לא צפויה בעדכון.", "error")
    finally:
        release_lock(status.parent)
    payload = read_json(status) or {}
    return 0 if payload.get("state") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
