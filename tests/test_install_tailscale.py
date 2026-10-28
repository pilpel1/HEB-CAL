"""שלב Tailscale Serve ב-install.sh: בלי דמון, עם CLI מזויף."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

SPEAKER_JSON = """{
  "TCP": {"443": {"HTTPS": true}},
  "Web": {
    "vostro.example.ts.net:443": {
      "Handlers": {
        "/": {"Proxy": "http://127.0.0.1:8765"}
      }
    }
  }
}
"""
SPEAKER_TEXT = """https://vostro.example.ts.net
|-- proxy http://127.0.0.1:8765
"""
EMPTY_JSON = "{}\n"
CAL_ON_8443_JSON = """{
  "TCP": {
    "443": {"HTTPS": true},
    "8443": {"HTTPS": true}
  },
  "Web": {
    "vostro.example.ts.net:443": {
      "Handlers": {"/": {"Proxy": "http://127.0.0.1:8765"}}
    },
    "vostro.example.ts.net:8443": {
      "Handlers": {"/": {"Proxy": "http://127.0.0.1:5000"}}
    }
  }
}
"""
OTHER_ON_8443_JSON = """{
  "TCP": {
    "443": {"HTTPS": true},
    "8443": {"HTTPS": true}
  },
  "Web": {
    "vostro.example.ts.net:443": {
      "Handlers": {"/": {"Proxy": "http://127.0.0.1:8765"}}
    },
    "vostro.example.ts.net:8443": {
      "Handlers": {"/": {"Proxy": "http://127.0.0.1:9000"}}
    }
  }
}
"""


def _run_serve(env: dict[str, str], extra_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    full = os.environ.copy()
    full.pop("HEB_CAL_TAILSCALE_SERVE", None)
    full.pop("HEB_CAL_TAILSCALE_HTTPS_PORT", None)
    full.update(env)
    path = full.get("PATH", os.environ.get("PATH", ""))
    if extra_path is not None:
        path = str(extra_path) + os.pathsep + path
    full["PATH"] = path
    script = r"""
set -euo pipefail
# shellcheck source=/dev/null
source ./install.sh
maybe_configure_tailscale_serve 5000
"""
    return subprocess.run(
        ["bash", "-c", script],
        cwd=REPO,
        env=full,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def _write_fake_tailscale(tmp: Path, body: str) -> Path:
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    path = bin_dir / "tailscale"
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return bin_dir


def test_install_sh_syntax():
    proc = subprocess.run(["bash", "-n", str(REPO / "install.sh")], check=False)
    assert proc.returncode == 0


def test_tailscale_absent_is_safe(tmp_path):
    path_dirs = [p for p in ("/bin", "/usr/bin") if not (Path(p) / "tailscale").exists()]
    if not path_dirs or not (Path(path_dirs[0]) / "bash").exists() and not (Path("/bin") / "bash").exists():
        pytest.skip("אין PATH בלי tailscale ועם bash")
    env = {
        "HOME": str(tmp_path),
        "HEB_CAL_TAILSCALE_SERVE": "1",
        "PATH": os.pathsep.join(path_dirs),
    }
    proc = _run_serve(env)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout + proc.stderr
    assert "Tailscale לא מותקן" in out
    assert "--https=8443" in out
    assert "serve reset" in out
    assert "לא מריצים tailscale serve reset" in out
    assert "docker compose" not in out


def test_permission_denied_prints_operator(tmp_path):
    bin_dir = _write_fake_tailscale(
        tmp_path,
        'echo "Access denied: serve config is locked; use sudo tailscale set --operator=$USER" >&2; exit 1\n',
    )
    proc = _run_serve({"HEB_CAL_TAILSCALE_SERVE": "1", "HOME": str(tmp_path)}, extra_path=bin_dir)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout + proc.stderr
    assert "אין הרשאה" in out
    assert "tailscale set --operator" in out
    assert "serve --bg --https=" in out


def test_existing_443_uses_8443_and_never_resets(tmp_path):
    log = tmp_path / "serve.log"
    json_file = tmp_path / "status.json"
    json_file.write_text(SPEAKER_JSON, encoding="utf-8")
    text_file = tmp_path / "status.txt"
    text_file.write_text(SPEAKER_TEXT, encoding="utf-8")
    bin_dir = _write_fake_tailscale(
        tmp_path,
        f"""
log='{log}'
json='{json_file}'
text='{text_file}'
printf '%s\\n' "$0 $*" >> "$log"
if [ "$1" = serve ] && [ "$2" = status ]; then
  if [ "$3" = --json ]; then cat "$json"; else cat "$text"; fi
  exit 0
fi
if [ "$1" = serve ]; then
  echo "Available within your tailnet:"
  echo "https://vostro.example.ts.net:8443"
  echo "|-- proxy http://127.0.0.1:5000"
  exit 0
fi
exit 0
""",
    )
    proc = _run_serve({"HEB_CAL_TAILSCALE_SERVE": "1", "HOME": str(tmp_path)}, extra_path=bin_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    out = proc.stdout
    assert "8443" in out
    assert "הנתיב / על 443 לא השתנה" in out
    argv = log.read_text(encoding="utf-8")
    assert "serve reset" not in argv
    assert "--set-path" not in argv
    assert "--https=8443" in argv
    assert "http://127.0.0.1:5000" in argv
    assert "--bg" in argv


def test_already_serving_heb_cal_skips_add(tmp_path):
    log = tmp_path / "serve.log"
    json_file = tmp_path / "status.json"
    json_file.write_text(CAL_ON_8443_JSON, encoding="utf-8")
    bin_dir = _write_fake_tailscale(
        tmp_path,
        f"""
log='{log}'
json='{json_file}'
printf '%s\\n' "$0 $*" >> "$log"
if [ "$1" = serve ] && [ "$2" = status ]; then
  cat "$json"
  exit 0
fi
echo unexpected-serve >&2
exit 2
""",
    )
    proc = _run_serve({"HEB_CAL_TAILSCALE_SERVE": "1", "HOME": str(tmp_path)}, extra_path=bin_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "כבר מפנה ליומן" in proc.stdout
    argv = log.read_text(encoding="utf-8")
    assert "--bg" not in argv
    assert "serve reset" not in argv


def test_8443_busy_skips_without_reset(tmp_path):
    json_file = tmp_path / "status.json"
    json_file.write_text(OTHER_ON_8443_JSON, encoding="utf-8")
    log = tmp_path / "serve.log"
    bin_dir = _write_fake_tailscale(
        tmp_path,
        f"""
log='{log}'
json='{json_file}'
printf '%s\\n' "$0 $*" >> "$log"
if [ "$1" = serve ] && [ "$2" = status ]; then
  cat "$json"
  exit 0
fi
echo should-not-serve >&2
exit 2
""",
    )
    proc = _run_serve({"HEB_CAL_TAILSCALE_SERVE": "1", "HOME": str(tmp_path)}, extra_path=bin_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "כבר בשימוש" in proc.stdout
    assert "לא דורסים" in proc.stdout
    argv = log.read_text(encoding="utf-8")
    assert "--bg" not in argv
    assert "serve reset" not in argv


def test_noninteractive_skips_but_prints_commands(tmp_path):
    json_file = tmp_path / "status.json"
    json_file.write_text(EMPTY_JSON, encoding="utf-8")
    log = tmp_path / "serve.log"
    bin_dir = _write_fake_tailscale(
        tmp_path,
        f"""
log='{log}'
json='{json_file}'
printf '%s\\n' "$0 $*" >> "$log"
if [ "$1" = serve ] && [ "$2" = status ]; then
  cat "$json"
  exit 0
fi
echo should-not-serve >&2
exit 2
""",
    )
    proc = _run_serve({"HOME": str(tmp_path)}, extra_path=bin_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "דילגתי על Tailscale Serve" in proc.stdout
    assert "--https=8443" in proc.stdout
    argv = log.read_text(encoding="utf-8")
    assert "--bg" not in argv


def test_empty_serve_with_auto_uses_443(tmp_path):
    json_file = tmp_path / "status.json"
    json_file.write_text(EMPTY_JSON, encoding="utf-8")
    log = tmp_path / "serve.log"
    bin_dir = _write_fake_tailscale(
        tmp_path,
        f"""
log='{log}'
json='{json_file}'
printf '%s\\n' "$0 $*" >> "$log"
if [ "$1" = serve ] && [ "$2" = status ]; then
  cat "$json"
  exit 0
fi
if [ "$1" = serve ]; then
  echo "https://vostro.example.ts.net"
  exit 0
fi
exit 0
""",
    )
    proc = _run_serve({"HEB_CAL_TAILSCALE_SERVE": "1", "HOME": str(tmp_path)}, extra_path=bin_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    argv = log.read_text(encoding="utf-8")
    assert "--https=443" in argv
    assert "--https=8443" not in argv
    assert "serve reset" not in argv


@pytest.mark.skipif(os.name == "nt", reason="bash test")
def test_install_sh_does_not_invoke_reset_literal():
    text = (REPO / "install.sh").read_text(encoding="utf-8")
    assert "maybe_configure_tailscale_serve" in text
    assert "tailscale serve reset" in text
    assert "לא מריצים tailscale serve reset" in text
    # אין קריאה ל-reset, רק אזהרה בעברית.
    assert "ts_capture serve reset" not in text
    assert "command tailscale serve reset" not in text
    assert "--set-path" not in text
