"""אריזת Docker: בלי דמון, חוץ מ-`docker compose config` אם הכלי קיים."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IMAGE = "ghcr.io/pilpel1/heb-cal:latest"
UPDATE = "docker compose pull && docker compose up -d"


def _text(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def test_dockerfile_binds_all_interfaces_and_copies_no_secrets():
    text = _text("Dockerfile")
    assert "AS builder" in text
    assert "AS runtime" in text
    assert '--host", "0.0.0.0"' in text
    assert '"5000"' in text
    assert "COPY .env" not in text
    assert not any(line.strip().startswith("ARG ") for line in text.splitlines())
    assert "COPY . " not in text
    assert "TELEGRAM_BOT_TOKEN=" not in text
    assert "ghp_" not in text
    assert "SECRET_KEY=" not in text


def test_compose_starts_web_and_reminder_and_documents_gcal():
    text = _text("docker-compose.yml")
    assert IMAGE in text
    assert "127.0.0.1" in text
    assert ":5000" in text
    assert "./data:/app/data" in text
    assert "./logs:/app/logs" in text
    assert "./backups:/app/backups" in text
    assert "HEB_CAL_UPDATE_MODE: docker" in text
    assert "HEB_CAL_DOCKER:" in text
    assert 'command: ["python", "scripts/reminder_worker.py"]' in text
    assert 'command: ["python", "scripts/gcal_sync_worker.py"]' in text
    assert 'profiles: ["gcal"]' in text
    assert "tailscale/" not in text.lower()
    assert "image: tailscale" not in text.lower()
    assert "ghp_" not in text
    assert "BOT_TOKEN:" not in text
    assert "TELEGRAM_BOT_TOKEN:" not in text


def test_dockerignore_and_entrypoint_keep_secrets_out():
    ignored = _text(".dockerignore")
    assert ".env" in ignored
    assert ".git" in ignored
    entry = _text("docker/entrypoint.sh")
    assert "SECRET_KEY" in entry
    assert "change-me-before-production" in entry
    assert "printenv" not in entry
    assert "echo \"${SECRET_KEY" not in entry
    assert "echo \"${TELEGRAM" not in entry


def test_env_example_documents_bind_and_restart():
    env = _text(".env.example")
    assert "TELEGRAM_BOT_TOKEN=" in env
    assert "BOT_TOKEN=" in env
    assert "SECRET_KEY=" in env
    assert "HEB_CAL_RESTART_COMMAND=" in env
    assert "HEB_CAL_BIND_HOST=" in env
    assert "HEB_CAL_PORT=" in env
    assert "127.0.0.1" in env
    assert UPDATE in env
    assert "ghp_" not in env


def test_readme_update_command_matches_docker_mode():
    readme = _text("README.md")
    assert UPDATE in readme
    assert "HEB_CAL_UPDATE_MODE=docker" in readme
    assert "tailscale serve" in readme
    assert "127.0.0.1" in readme
    assert "gcal_sync_worker.py" in readme
    changelog = _text("CHANGELOG.md")
    version = _text("VERSION").strip()
    assert version == "1.0.2"
    assert f"## {version}" in changelog
    assert "Docker" in changelog


def test_compose_config_when_docker_is_installed():
    docker = shutil.which("docker")
    if docker is None:
        return
    env = os.environ.copy()
    env["HEB_CAL_BIND_HOST"] = "127.0.0.1"
    env["HEB_CAL_PORT"] = "5000"
    env.pop("HEB_CAL_IMAGE", None)
    proc = subprocess.run(
        [docker, "compose", "--profile", "gcal", "config"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or "").lower()
        if any(token in err for token in ("docker daemon", "permission denied", "cannot connect")):
            return
    assert proc.returncode == 0, proc.stderr
    rendered = proc.stdout
    assert "image: ghcr.io/pilpel1/heb-cal:latest" in rendered
    assert 'host_ip: 127.0.0.1' in rendered
    assert 'published: "5000"' in rendered
    assert "target: 5000" in rendered
    assert "scripts/reminder_worker.py" in rendered
    assert "scripts/gcal_sync_worker.py" in rendered
    assert "HEB_CAL_UPDATE_MODE" in rendered
    assert "change-me-before-production" not in rendered
    assert "ghp_" not in rendered
    default = subprocess.run(
        [docker, "compose", "config", "--services"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert default.returncode == 0, default.stderr
    assert set(default.stdout.split()) == {"web", "reminder"}
