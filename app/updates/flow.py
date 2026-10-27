"""סדר העדכון והחזרה לאחור. בלי רשת ובלי git — את זה מספקת שכבת הפעולות."""
from __future__ import annotations

from dataclasses import dataclass

from app.updates.errors import UpdateError, redact, safe_detail

_CODE_STEPS = {"checkout", "install"}
_DB_STEPS = {"migrate", "hook"}


@dataclass
class Plan:
    mode: str
    tag: str
    version: str


def outcome_text(done: set[str], rollback_ok: bool | str) -> str:
    code = bool(done & _CODE_STEPS)
    database = bool(done & _DB_STEPS)
    restarted = "restart" in done
    if not (code or database or restarted):
        return "לא שינינו את הקוד."
    if rollback_ok == "partial-both":
        return "הקוד ומסד הנתונים חזרו לגיבוי, אבל ההפעלה מחדש נכשלה."
    if rollback_ok == "partial-code":
        return "הקוד חזר לגרסה הקודמת, אבל ההפעלה מחדש נכשלה."
    if rollback_ok == "partial-db":
        return "מסד הנתונים שוחזר מהגיבוי, אבל ההפעלה מחדש נכשלה."
    if rollback_ok in {False, "failed"}:
        return "החזרה לאחור לא הושלמה. הגיבוי נשמר בתיקיית backups."
    if code and database:
        return "חזרנו לגרסה הקודמת ולגיבוי של מסד הנתונים."
    if code:
        return "חזרנו לגרסה הקודמת. מסד הנתונים לא השתנה."
    if database:
        return "מסד הנתונים שוחזר מהגיבוי."
    return "חזרנו למצב הקודם."


def failure_message(cause: str, done: set[str], rollback_ok: bool | str) -> str:
    detail = cause if safe_detail(cause) else "העדכון נכשל."
    return f"{detail} {outcome_text(done, rollback_ok)}"


def _rollback(ops, done: set[str], backup, sha: str | None) -> bool | str:
    restored_code = False
    restored_db = False
    try:
        if done & _CODE_STEPS:
            if not sha:
                raise UpdateError("אין נקודת חזרה לקוד.", step="rollback")
            ops.checkout_sha(sha)
            ops.pip_install()
            restored_code = True
        if done & _DB_STEPS:
            if backup is None:
                raise UpdateError("אין גיבוי לשחזור.", step="rollback")
            try:
                ops.stop_app()
            except UpdateError:
                # גם אם העצירה נכשלה מנסים לשחזר, ואז להפעיל מחדש.
                pass
            ops.restore_database(backup)
            restored_db = True
        if "restart" in done or restored_code or restored_db:
            if ops.restart_configured():
                ops.restart()
        return True
    except Exception as exc:
        redact(str(exc))
        if restored_code and restored_db:
            return "partial-both"
        if restored_code:
            return "partial-code"
        if restored_db:
            return "partial-db"
        return False


def execute_update(ops, plan: Plan) -> None:
    done: set[str] = set()
    backup = None
    sha = None
    try:
        if plan.mode not in {"git", "hook"}:
            raise UpdateError("במצב הזה אין עדכון מתוך האפליקציה.", step="start")
        ops.write(state="running", step="backup", message="מגבה את מסד הנתונים")
        backup = ops.backup_database()
        if plan.mode == "git":
            ops.write(step="fetch", message="מוריד את הגרסה")
            sha = ops.current_sha()
            ops.ensure_not_shallow()
            ops.ensure_clean()
            ops.fetch(plan.tag)
            ops.ensure_fast_forward(sha, plan.tag)
            ops.write(step="checkout", message="עובר לגרסה החדשה")
            done.add("checkout")
            ops.checkout(plan.tag)
            ops.write(step="install", message="מתקין חבילות")
            done.add("install")
            ops.pip_install()
            ops.write(step="migrate", message="מעדכן את מסד הנתונים")
            done.add("migrate")
            ops.migrate()
        else:
            ops.write(step="hook", message="מריץ את סקריפט העדכון")
            done.add("hook")
            ops.run_hook(plan.version)
        if plan.mode == "git" or ops.restart_configured():
            ops.write(step="restart", message="מפעיל מחדש")
            done.add("restart")
            ops.restart()
        ops.write(step="health", message="בודק שהאפליקציה עלתה")
        ops.wait_healthy(plan.version)
        ops.write(
            state="success",
            step="done",
            message="העדכון הושלם. הדף ייטען מחדש.",
            error=None,
            finished_at=_finished(),
        )
    except UpdateError as exc:
        _fail(ops, done, backup, sha, exc)
    except Exception:
        _fail(ops, done, backup, sha, UpdateError("תקלה לא צפויה בעדכון.", step="error"))


def _finished() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _fail(ops, done: set[str], backup, sha, exc: UpdateError) -> None:
    rollback_ok = True
    if done:
        rollback_ok = _rollback(ops, done, backup, sha)
    message = failure_message(exc.message, done, rollback_ok)
    ops.write(
        state="failed",
        step=exc.step,
        message=message,
        error=message,
        finished_at=_finished(),
    )
