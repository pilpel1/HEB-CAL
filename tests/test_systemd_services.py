"""יחידות systemd --user, מתקין, ו-restart דרך systemctl."""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

from app.database import BASE_DIR
from app.updates.envconfig import UpdateConfig
from app.updates.gitops import LiveOps, restart_block
from app.updates.systemd import instance_name, systemd_user_units_installed, unit_filenames

REPO = Path(__file__).resolve().parent.parent


def _stub_bin(bin_dir: Path, log: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = (
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$0 $*\" >> '{log}'\n"
        "exit 0\n"
    )
    for name in ("systemctl", "systemd-run", "loginctl", "pgrep", "fuser", "lsof"):
        path = bin_dir / name
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)


def _cfg(tmp_path: Path, **kwargs) -> UpdateConfig:
    return UpdateConfig(
        mode="git",
        repo="pilpel1/HEB-CAL",
        token=None,
        restart_command=kwargs.get("restart_command"),
        hook_path=None,
        hook_error=None,
        health_url="http://127.0.0.1:5000/api/updates/health",
        health_error=None,
        backup_dir=tmp_path / "backups",
        db_path=tmp_path / "cal.sqlite",
        repo_root=kwargs.get("repo_root", tmp_path),
        autocheck=False,
        update_dir=tmp_path,
        repo_error=None,
    )


def test_systemd_units_detected_only_for_this_repo(tmp_path, monkeypatch):
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(unit_dir))
    root = tmp_path / "HEB-CAL"
    root.mkdir()
    assert systemd_user_units_installed(root) is False
    (unit_dir / "heb-cal-web.service").write_text(
        f"WorkingDirectory={root}\nExecStart=/usr/bin/true\n",
        encoding="utf-8",
    )
    (unit_dir / "heb-cal-worker.service").write_text(
        "WorkingDirectory=/elsewhere\n",
        encoding="utf-8",
    )
    assert systemd_user_units_installed(root) is False
    (unit_dir / "heb-cal-worker.service").write_text(
        f"WorkingDirectory={root}\n",
        encoding="utf-8",
    )
    assert systemd_user_units_installed(root) is True
    assert restart_block(None, root) is None
    assert restart_block("scripts/does-not-exist.sh", REPO) == "סקריפט ההפעלה מחדש לא נמצא."


def test_restart_block_without_units_still_needs_command(tmp_path, monkeypatch):
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(tmp_path / "empty"))
    assert restart_block(None, tmp_path) == "לא הוגדרה פקודת הפעלה מחדש (HEB_CAL_RESTART_COMMAND)."


def test_liveops_restart_uses_bundled_script_when_units_exist(tmp_path, monkeypatch):
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    repo = tmp_path / "HEB-CAL"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (unit_dir / "heb-cal-web.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    log = tmp_path / "restart.log"
    script = scripts / "restart.sh"
    script.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"ACTION=${{HEB_CAL_UPDATE_ACTION-}}\" >> '{log}'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(unit_dir))
    ops = LiveOps(_cfg(tmp_path, repo_root=repo, restart_command=None), tmp_path / "status.json", "1.0.23")
    ops.restart()
    ops.stop_app()
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines == ["ACTION=restart", "ACTION=stop"]


def test_liveops_restart_configured_follows_units(tmp_path, monkeypatch):
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    repo = tmp_path / "HEB-CAL"
    repo.mkdir()
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(unit_dir))
    ops = LiveOps(_cfg(tmp_path, repo_root=repo, restart_command=None), tmp_path / "status.json", "1.0.23")
    assert ops.restart_configured() is False
    (unit_dir / "heb-cal-web.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    assert ops.restart_configured() is True


def test_restart_script_uses_systemctl_when_user_units_exist(tmp_path):
    src = REPO / "scripts" / "restart.sh"
    root = tmp_path / "home"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    dest = scripts / "restart.sh"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    dest.chmod(0o755)
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    (unit_dir / "heb-cal-web.service").write_text("WorkingDirectory=/tmp\n", encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text("WorkingDirectory=/tmp\n", encoding="utf-8")
    (unit_dir / "heb-cal-web.socket").write_text("ListenStream=127.0.0.1:59991\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    log = tmp_path / "systemctl.log"
    _stub_bin(bin_dir, log)
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["HOME"] = str(root)
    env["HEB_CAL_UNIT_DIR"] = str(unit_dir)
    env["HEB_CAL_UPDATE_ACTION"] = "restart"
    env["HEB_CAL_PORT"] = "59991"
    proc = subprocess.run(
        ["sh", str(dest)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    logged = log.read_text(encoding="utf-8")
    assert "systemd-run" in logged
    assert "--unit=heb-cal-update-restart" in logged
    assert "restart heb-cal-web.service heb-cal-worker.service" in logged
    assert "heb-cal-web.socket" not in logged
    assert "stop heb-cal-web.service heb-cal-worker.service" not in logged
    assert " start heb-cal-web.service heb-cal-worker.service" not in logged
    assert not (root / "data" / "flask.pid").exists()
    env["HEB_CAL_UPDATE_ACTION"] = "stop"
    log.write_text("", encoding="utf-8")
    proc = subprocess.run(
        ["sh", str(dest)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    logged = log.read_text(encoding="utf-8")
    assert "--no-block stop heb-cal-web.service heb-cal-worker.service" in logged
    assert "heb-cal-web.socket" not in logged
    assert "start " not in logged


def _copy_install_tree(root: Path) -> None:
    (root / "deploy" / "systemd").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(exist_ok=True)
    shutil.copy(REPO / "deploy/systemd/heb-cal-web.service", root / "deploy/systemd/heb-cal-web.service")
    shutil.copy(REPO / "deploy/systemd/heb-cal-worker.service", root / "deploy/systemd/heb-cal-worker.service")
    shutil.copy(REPO / "deploy/systemd/heb-cal-web.socket", root / "deploy/systemd/heb-cal-web.socket")
    shutil.copy(REPO / "scripts/install_services.sh", root / "scripts/install_services.sh")
    shutil.copy(REPO / "scripts/restart.sh", root / "scripts/restart.sh")
    shutil.copy(REPO / "scripts/instance_select.py", root / "scripts/instance_select.py")
    shutil.copy(REPO / "scripts/run_web.py", root / "scripts/run_web.py")
    (root / "scripts" / "install_services.sh").chmod(0o755)
    (root / "scripts" / "restart.sh").chmod(0o755)
    (root / "scripts" / "run_web.py").chmod(0o755)


def test_install_services_script_is_idempotent(tmp_path):
    root = tmp_path / "HEB-CAL"
    _copy_install_tree(root)
    (root / ".env").write_text(
        "HEB_CAL_BIND_HOST=0.0.0.0\nHEB_CAL_PORT=59992\nHEB_CAL_RESTART_COMMAND=\n",
        encoding="utf-8",
    )
    unit_dir = tmp_path / "units"
    bin_dir = tmp_path / "bin"
    log = tmp_path / "systemctl.log"
    _stub_bin(bin_dir, log)
    python = shutil.which("python3") or shutil.which("python")
    assert python
    venv_python = root / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(python)
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["HOME"] = str(tmp_path / "home")
    env["HEB_CAL_UNIT_DIR"] = str(unit_dir)
    env["HEB_CAL_SKIP_LINGER"] = "1"
    env["HEB_CAL_BIND_HOST"] = "0.0.0.0"
    env["HEB_CAL_PORT"] = "59992"
    env.pop("HEB_CAL_INSTANCE_NAME", None)
    for _ in range(2):
        proc = subprocess.run(
            ["bash", str(root / "scripts" / "install_services.sh")],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
    web = (unit_dir / "heb-cal-web.service").read_text(encoding="utf-8")
    worker = (unit_dir / "heb-cal-worker.service").read_text(encoding="utf-8")
    assert str(root) in web
    assert str(root) in worker
    assert "@INSTALL_DIR@" not in web
    assert "0.0.0.0" in web
    assert "59992" in web
    assert "Restart=always" in web
    assert "RestartPreventExitStatus=75" in worker
    assert "SyslogIdentifier=heb-cal-web" in web
    assert "@INSTANCE@" not in web
    assert "TELEGRAM_BOT_TOKEN" not in web
    assert "SECRET_KEY" not in worker
    instance_env = (root / "data" / "instance.env").read_text(encoding="utf-8")
    assert "HEB_CAL_INSTANCE_NAME=heb-cal" in instance_env
    assert "HEB_CAL_PORT=59992" in instance_env
    assert "TELEGRAM" not in instance_env
    env_text = (root / ".env").read_text(encoding="utf-8")
    assert "HEB_CAL_RESTART_COMMAND=scripts/restart.sh" in env_text
    assert "HEB_CAL_HEALTH_URL=http://127.0.0.1:59992/api/updates/health" in env_text
    logged = log.read_text(encoding="utf-8")
    assert "daemon-reload" in logged
    assert "enable heb-cal-web.socket heb-cal-web.service heb-cal-worker.service" in logged
    assert "start heb-cal-web.socket heb-cal-web.service heb-cal-worker.service" in logged
    socket = (unit_dir / "heb-cal-web.socket").read_text(encoding="utf-8")
    assert "ListenStream=0.0.0.0:59992" in socket
    assert "Accept=no" in socket
    assert "BindsTo=" not in socket
    assert "run_web.py" in web
    assert "HEB_CAL_PORT=59992" in web
    assert "Requires=heb-cal-web.socket" in web
    mode = (unit_dir / "heb-cal-web.service").stat().st_mode
    assert stat.S_IMODE(mode) == 0o644


def test_settings_apply_unblocked_when_units_match_repo(client, monkeypatch, tmp_path):
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    (unit_dir / "heb-cal-web.service").write_text(
        f"WorkingDirectory={BASE_DIR}\n",
        encoding="utf-8",
    )
    (unit_dir / "heb-cal-worker.service").write_text(
        f"WorkingDirectory={BASE_DIR}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(unit_dir))
    monkeypatch.setenv("HEB_CAL_RESTART_COMMAND", "")
    body = client.get("/api/updates").get_json()
    assert body["can_apply"] is True
    assert body["restart_configured"] is True
    assert body["block"] is None


def _install_env(tmp_path, root, unit_dir, extra=None):
    bin_dir = tmp_path / "bin"
    log = tmp_path / "systemctl.log"
    _stub_bin(bin_dir, log)
    python = shutil.which("python3") or shutil.which("python")
    assert python
    venv_python = root / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    if not venv_python.exists():
        venv_python.symlink_to(python)
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["HOME"] = str(tmp_path / "home")
    env["HEB_CAL_UNIT_DIR"] = str(unit_dir)
    env["HEB_CAL_SKIP_LINGER"] = "1"
    env.pop("HEB_CAL_INSTANCE_NAME", None)
    env.pop("HEB_CAL_PORT", None)
    if extra:
        env.update(extra)
    return env, log


def test_install_second_instance_does_not_overwrite_first(tmp_path):
    first = tmp_path / "family1"
    second = tmp_path / "family2"
    _copy_install_tree(first)
    _copy_install_tree(second)
    (first / ".env").write_text("HEB_CAL_RESTART_COMMAND=\nSECRET_KEY=one\n", encoding="utf-8")
    (second / ".env").write_text("HEB_CAL_RESTART_COMMAND=\nSECRET_KEY=two\n", encoding="utf-8")
    unit_dir = tmp_path / "units"
    env1, log = _install_env(tmp_path, first, unit_dir, {"HEB_CAL_PORT": "59981"})
    proc = subprocess.run(
        ["bash", str(first / "scripts" / "install_services.sh")],
        cwd=first,
        env=env1,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    first_web = (unit_dir / "heb-cal-web.service").read_text(encoding="utf-8")
    env2, log = _install_env(tmp_path, second, unit_dir)
    log.write_text("", encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(second / "scripts" / "install_services.sh")],
        cwd=second,
        env=env2,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert (unit_dir / "heb-cal-web.service").read_text(encoding="utf-8") == first_web
    second_web = (unit_dir / "heb-cal2-web.service").read_text(encoding="utf-8")
    assert str(second) in second_web
    assert str(first) not in second_web
    assert str(first) in first_web
    assert "59981" in first_web
    match = re.search(r"Environment=HEB_CAL_PORT=(\d+)", second_web)
    assert match is not None
    assert int(match.group(1)) >= 5001
    second_socket = (unit_dir / "heb-cal2-web.socket").read_text(encoding="utf-8")
    first_socket = (unit_dir / "heb-cal-web.socket").read_text(encoding="utf-8")
    assert f":{match.group(1)}" in second_socket
    assert "59981" in first_socket
    assert str(second) not in first_web
    instance = (second / "data" / "instance.env").read_text(encoding="utf-8")
    assert "HEB_CAL_INSTANCE_NAME=heb-cal2" in instance
    logged = log.read_text(encoding="utf-8")
    assert "enable heb-cal2-web.socket heb-cal2-web.service heb-cal2-worker.service" in logged
    assert "enable heb-cal-web.service heb-cal-worker.service" not in logged


def test_install_refuses_to_overwrite_named_units(tmp_path):
    root = tmp_path / "intruder"
    _copy_install_tree(root)
    (root / ".env").write_text("HEB_CAL_RESTART_COMMAND=\n", encoding="utf-8")
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    original = f"WorkingDirectory={tmp_path / 'owner'}\nExecStart=/bin/true --port 5000\n"
    (unit_dir / "heb-cal-web.service").write_text(original, encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text(
        f"WorkingDirectory={tmp_path / 'owner'}\n",
        encoding="utf-8",
    )
    env, _log = _install_env(tmp_path, root, unit_dir)
    proc = subprocess.run(
        ["bash", str(root / "scripts" / "install_services.sh"), "--name", "heb-cal"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode != 0
    assert "heb-cal-web.service" in proc.stderr
    assert (unit_dir / "heb-cal-web.service").read_text(encoding="utf-8") == original
    assert not (unit_dir / "heb-cal2-web.service").exists()


def test_restart_script_uses_instance_units_only(tmp_path):
    src = REPO / "scripts" / "restart.sh"
    root = tmp_path / "home"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    dest = scripts / "restart.sh"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    dest.chmod(0o755)
    (root / "data").mkdir()
    (root / "data" / "instance.env").write_text(
        "HEB_CAL_INSTANCE_NAME=heb-cal2\nHEB_CAL_PORT=5001\n",
        encoding="utf-8",
    )
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    (unit_dir / "heb-cal-web.service").write_text("WorkingDirectory=/other\n", encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text("WorkingDirectory=/other\n", encoding="utf-8")
    (unit_dir / "heb-cal2-web.service").write_text(f"WorkingDirectory={root}\n", encoding="utf-8")
    (unit_dir / "heb-cal2-worker.service").write_text(f"WorkingDirectory={root}\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    log = tmp_path / "systemctl.log"
    _stub_bin(bin_dir, log)
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["HOME"] = str(root)
    env["HEB_CAL_UNIT_DIR"] = str(unit_dir)
    env.pop("HEB_CAL_INSTANCE_NAME", None)
    proc = subprocess.run(
        ["sh", str(dest)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    logged = log.read_text(encoding="utf-8")
    assert "--unit=heb-cal2-update-restart" in logged
    assert "restart heb-cal2-web.service heb-cal2-worker.service" in logged
    assert "stop heb-cal2-web.service heb-cal2-worker.service" not in logged
    assert "heb-cal-web.service heb-cal-worker.service" not in logged


def test_restart_script_falls_back_to_noblock_without_systemd_run(tmp_path):
    src = REPO / "scripts" / "restart.sh"
    root = tmp_path / "home"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    dest = scripts / "restart.sh"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    dest.chmod(0o755)
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    (unit_dir / "heb-cal-web.service").write_text(f"WorkingDirectory={root}\n", encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text(f"WorkingDirectory={root}\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    log = tmp_path / "systemctl.log"
    _stub_bin(bin_dir, log)
    (bin_dir / "systemd-run").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin_dir / "systemd-run").chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["HOME"] = str(root)
    env["HEB_CAL_UNIT_DIR"] = str(unit_dir)
    env["HEB_CAL_UPDATE_ACTION"] = "restart"
    proc = subprocess.run(
        ["sh", str(dest)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    logged = log.read_text(encoding="utf-8")
    assert "--no-block restart heb-cal-web.service heb-cal-worker.service" in logged
    assert "stop heb-cal-web.service heb-cal-worker.service" not in logged


def test_unit_filenames_follow_instance_env(tmp_path, monkeypatch):
    repo = tmp_path / "family2"
    repo.mkdir()
    (repo / "data").mkdir()
    (repo / "data" / "instance.env").write_text(
        "HEB_CAL_INSTANCE_NAME=heb-cal2\nHEB_CAL_PORT=5001\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("HEB_CAL_INSTANCE_NAME", raising=False)
    assert instance_name(repo) == "heb-cal2"
    assert unit_filenames(repo) == ("heb-cal2-web.service", "heb-cal2-worker.service")
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(unit_dir))
    (unit_dir / "heb-cal-web.service").write_text("WorkingDirectory=/other\n", encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text("WorkingDirectory=/other\n", encoding="utf-8")
    assert systemd_user_units_installed(repo) is False
    (unit_dir / "heb-cal2-web.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    (unit_dir / "heb-cal2-worker.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    assert systemd_user_units_installed(repo) is True


def test_install_units_only_does_not_stop_or_start(tmp_path):
    root = tmp_path / "HEB-CAL"
    _copy_install_tree(root)
    (root / ".env").write_text("HEB_CAL_RESTART_COMMAND=\n", encoding="utf-8")
    unit_dir = tmp_path / "units"
    env, log = _install_env(tmp_path, root, unit_dir, {"HEB_CAL_PORT": "5000"})
    proc = subprocess.run(
        ["bash", str(root / "scripts" / "install_services.sh"), "--units-only"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    logged = log.read_text(encoding="utf-8")
    assert "enable heb-cal-web.socket heb-cal-web.service heb-cal-worker.service" in logged
    assert "daemon-reload" in logged
    assert " start " not in logged
    assert " stop " not in logged
    assert "tailscale" not in logged.lower()
    socket = (unit_dir / "heb-cal-web.socket").read_text(encoding="utf-8")
    assert "ListenStream=127.0.0.1:5000" in socket


def test_install_gisim_keeps_separate_listen_stream(tmp_path):
    main = tmp_path / "main"
    gisim = tmp_path / "gisim"
    _copy_install_tree(main)
    _copy_install_tree(gisim)
    (main / ".env").write_text("HEB_CAL_RESTART_COMMAND=\n", encoding="utf-8")
    (gisim / ".env").write_text("HEB_CAL_RESTART_COMMAND=\n", encoding="utf-8")
    unit_dir = tmp_path / "units"
    env_main, log = _install_env(tmp_path, main, unit_dir, {"HEB_CAL_PORT": "5000"})
    proc = subprocess.run(
        ["bash", str(main / "scripts" / "install_services.sh")],
        cwd=main,
        env=env_main,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    main_web = (unit_dir / "heb-cal-web.service").read_text(encoding="utf-8")
    env_g, log = _install_env(tmp_path, gisim, unit_dir)
    log.write_text("", encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(gisim / "scripts" / "install_services.sh"), "--name", "gisim", "--port", "5001"],
        cwd=gisim,
        env=env_g,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert (unit_dir / "heb-cal-web.service").read_text(encoding="utf-8") == main_web
    gisim_web = (unit_dir / "gisim-web.service").read_text(encoding="utf-8")
    gisim_socket = (unit_dir / "gisim-web.socket").read_text(encoding="utf-8")
    main_socket = (unit_dir / "heb-cal-web.socket").read_text(encoding="utf-8")
    assert "HEB_CAL_PORT=5001" in gisim_web
    assert "ListenStream=127.0.0.1:5001" in gisim_socket
    assert "ListenStream=127.0.0.1:5000" in main_socket
    assert str(gisim) in gisim_web
    assert str(main) not in gisim_web
    logged = log.read_text(encoding="utf-8")
    assert "enable gisim-web.socket gisim-web.service gisim-worker.service" in logged
    assert "heb-cal-web.service" not in logged
    instance = (gisim / "data" / "instance.env").read_text(encoding="utf-8")
    assert "HEB_CAL_INSTANCE_NAME=gisim" in instance
    assert "HEB_CAL_PORT=5001" in instance


def test_liveops_restart_returns_may_die_only_when_flag_set(tmp_path, monkeypatch):
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    repo = tmp_path / "HEB-CAL"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (unit_dir / "heb-cal-web.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    script = scripts / "restart.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(unit_dir))
    monkeypatch.delenv("HEB_CAL_UPDATE_MAY_DIE", raising=False)
    ops = LiveOps(_cfg(tmp_path, repo_root=repo, restart_command=None), tmp_path / "status.json", "1.0.29")
    assert ops.restart() is False
    monkeypatch.setenv("HEB_CAL_UPDATE_MAY_DIE", "1")
    assert ops.restart() is True


def test_unit_backup_restore_drops_socket_added_after_upgrade(tmp_path, monkeypatch):
    from app.updates import units as unitmod

    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    repo = tmp_path / "HEB-CAL"
    repo.mkdir()
    (repo / "data").mkdir()
    (repo / "data" / "instance.env").write_text(
        "HEB_CAL_INSTANCE_NAME=heb-cal\nHEB_CAL_PORT=5000\n",
        encoding="utf-8",
    )
    web = "WorkingDirectory=%s\nEnvironment=HEB_CAL_PORT=5000\n" % repo
    (unit_dir / "heb-cal-web.service").write_text(web, encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    (unit_dir / "heb-cal-web.socket").write_text("ListenStream=127.0.0.1:5000\n", encoding="utf-8")
    (unit_dir / "gisim-web.service").write_text("WorkingDirectory=/other\n", encoding="utf-8")
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(unit_dir))
    monkeypatch.delenv("HEB_CAL_INSTANCE_NAME", raising=False)
    argv_log = []

    def fake_run(args, **kwargs):
        argv_log.append(args)

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return Proc()

    monkeypatch.setattr(unitmod, "run_argv", fake_run)
    backup = tmp_path / "unit-backup"
    # גיבוי בלי socket — כמו לפני 1.0.29
    (unit_dir / "heb-cal-web.socket").unlink()
    saved = unitmod.backup_instance_units(repo, backup)
    assert saved is not None
    assert (backup / "heb-cal-web.service").is_file()
    assert not (backup / "heb-cal-web.socket").exists()
    assert not (backup / "gisim-web.service").exists()
    (unit_dir / "heb-cal-web.socket").write_text("ListenStream=127.0.0.1:5000\n", encoding="utf-8")
    (unit_dir / "heb-cal-web.service").write_text("CHANGED\n", encoding="utf-8")
    unitmod.restore_instance_units(repo, saved)
    assert (unit_dir / "heb-cal-web.service").read_text(encoding="utf-8") == web
    assert not (unit_dir / "heb-cal-web.socket").exists()
    assert (unit_dir / "gisim-web.service").is_file()
    joined = " ".join(" ".join(a) for a in argv_log)
    assert "heb-cal-web.socket" in joined
    assert "gisim" not in joined
    assert "daemon-reload" in joined

    def _idx(needle):
        for i, args in enumerate(argv_log):
            if needle in args:
                return i
        raise AssertionError(needle, argv_log)

    assert _idx("heb-cal-web.service") < _idx("heb-cal-web.socket")
    web_stop = next(a for a in argv_log if "heb-cal-web.service" in a and "stop" in a)
    assert "--no-block" not in web_stop
    assert "heb-cal-worker.service" in web_stop


def test_restore_units_keeps_socket_when_it_was_backed_up(tmp_path, monkeypatch):
    from app.updates import units as unitmod

    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    repo = tmp_path / "HEB-CAL"
    repo.mkdir()
    (repo / "data").mkdir()
    (repo / "data" / "instance.env").write_text(
        "HEB_CAL_INSTANCE_NAME=heb-cal\nHEB_CAL_PORT=5000\n",
        encoding="utf-8",
    )
    (unit_dir / "heb-cal-web.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    (unit_dir / "heb-cal-web.socket").write_text("ListenStream=127.0.0.1:5000\n", encoding="utf-8")
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(unit_dir))
    monkeypatch.delenv("HEB_CAL_INSTANCE_NAME", raising=False)
    argv_log = []

    def fake_run(args, **kwargs):
        argv_log.append(args)

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return Proc()

    monkeypatch.setattr(unitmod, "run_argv", fake_run)
    backup = tmp_path / "unit-backup"
    saved = unitmod.backup_instance_units(repo, backup)
    (unit_dir / "heb-cal-web.service").write_text("CHANGED\n", encoding="utf-8")
    unitmod.restore_instance_units(repo, saved)
    assert "WorkingDirectory=" in (unit_dir / "heb-cal-web.service").read_text(encoding="utf-8")
    assert (unit_dir / "heb-cal-web.socket").is_file()
    joined = " ".join(" ".join(a) for a in argv_log)
    assert "daemon-reload" in joined
    assert "stop" not in joined
    assert "disable" not in joined


def test_install_runtime_units_calls_units_only(tmp_path, monkeypatch):
    from app.updates import units as unitmod

    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    repo = tmp_path / "HEB-CAL"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (unit_dir / "heb-cal-web.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    (unit_dir / "heb-cal-worker.service").write_text(f"WorkingDirectory={repo}\n", encoding="utf-8")
    script = scripts / "install_services.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(unit_dir))
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["env"] = kwargs.get("env") or {}

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return Proc()

    monkeypatch.setattr(unitmod, "run_argv", fake_run)
    dest = tmp_path / "backup"
    saved = unitmod.install_runtime_units(repo, dest)
    assert saved is not None
    assert seen["args"][:3] == ["bash", str(script), "--units-only"]
    assert seen["env"].get("HEB_CAL_SKIP_LINGER") == "1"
    empty = tmp_path / "none"
    empty.mkdir()
    monkeypatch.setenv("HEB_CAL_UNIT_DIR", str(empty))
    assert unitmod.install_runtime_units(repo, tmp_path / "other") is None
