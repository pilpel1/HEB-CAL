#!/usr/bin/env python3
"""בחירת שם ופורט למופע HEB-CAL מקומי.

קובץ עצמאי (stdlib בלבד) כדי ש-install_services.sh יוכל להריץ אותו בלי לטעון Flask.
השם והפורט נשמרים ב-data/instance.env (לא בגיט). ברירת מחדל: heb-cal על 5000.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_NAME = "heb-cal"
DEFAULT_PORT = 5000
NEW_INSTANCE_PORT_START = 5001
HTTPS_PORT_START = 10000
RESERVED_HTTPS_PORTS = frozenset({443, 8443})
CONFIG_REL = Path("data") / "instance.env"

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
PORT_RE = re.compile(r"--port(?:=|\s+)(\d+)")
WD_RE = re.compile(r"^WorkingDirectory=(.*)$", re.M)
ENV_PORT_RE = re.compile(r"^Environment=HEB_CAL_PORT=(\d+)\s*$", re.M)
KEY_RE = re.compile(r"^(HEB_CAL_INSTANCE_NAME|HEB_CAL_PORT|HEB_CAL_BIND_HOST|HEB_CAL_TAILSCALE_HTTPS_PORT)=(.*)$")

OVERWRITE_EXIT = 2


class InstanceError(Exception):
    """שגיאה עם הודעה בעברית למשתמש."""

    def __init__(self, message: str, *, overwrite: bool = False):
        super().__init__(message)
        self.message = message
        self.overwrite = overwrite


@dataclass(frozen=True)
class InstanceConfig:
    name: str | None = None
    port: int | None = None
    bind_host: str | None = None
    tailscale_https_port: int | None = None


@dataclass(frozen=True)
class InstallPlan:
    name: str
    port: int
    web_unit: str
    worker_unit: str
    reused: bool
    bind_host: str | None = None
    tailscale_https_port: int | None = None


def valid_instance_name(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not NAME_RE.fullmatch(text):
        return False
    if text.startswith("-") or "--" in text or text.endswith("-"):
        return False
    return True


def validate_name(value: str) -> str:
    text = (value or "").strip()
    if not valid_instance_name(text):
        raise InstanceError(
            "שם מופע לא תקין. רק אותיות אנגליות קטנות, ספרות ומקף, "
            "ומתחיל באות (למשל heb-cal או heb-cal2)."
        )
    return text


def validate_port(value) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise InstanceError("פורט לא תקין. צריך מספר בין 1 ל-65535.") from exc
    if port < 1 or port > 65535:
        raise InstanceError("פורט לא תקין. צריך מספר בין 1 ל-65535.")
    return port


def web_unit_name(name: str) -> str:
    return f"{validate_name(name)}-web.service"


def worker_unit_name(name: str) -> str:
    return f"{validate_name(name)}-worker.service"


def unit_names(name: str) -> tuple[str, str]:
    return web_unit_name(name), worker_unit_name(name)


def name_from_web_unit(filename: str) -> str | None:
    text = (filename or "").strip()
    suffix = "-web.service"
    if not text.endswith(suffix):
        return None
    name = text[: -len(suffix)]
    return name if valid_instance_name(name) else None


def config_path(root: Path) -> Path:
    return Path(root) / CONFIG_REL


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    found: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip().replace("\r", "")
        if not line or line.startswith("#"):
            continue
        match = KEY_RE.fullmatch(line)
        if not match:
            continue
        found[match.group(1)] = _strip_quotes(match.group(2))
    return found


def load_instance_config(root: Path) -> InstanceConfig:
    raw = parse_env_file(config_path(root))
    name = raw.get("HEB_CAL_INSTANCE_NAME")
    if name and not valid_instance_name(name):
        name = None
    port = None
    if raw.get("HEB_CAL_PORT"):
        try:
            port = validate_port(raw["HEB_CAL_PORT"])
        except InstanceError:
            port = None
    host = raw.get("HEB_CAL_BIND_HOST") or None
    https = None
    if raw.get("HEB_CAL_TAILSCALE_HTTPS_PORT"):
        try:
            https = validate_port(raw["HEB_CAL_TAILSCALE_HTTPS_PORT"])
        except InstanceError:
            https = None
    return InstanceConfig(name=name, port=port, bind_host=host, tailscale_https_port=https)


def save_instance_config(root: Path, cfg: InstanceConfig | InstallPlan) -> Path:
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = cfg.name or DEFAULT_NAME
    port = cfg.port if cfg.port is not None else DEFAULT_PORT
    lines = [
        "# קונפיגורציה מקומית של המופע. לא לשים כאן טוקנים או סודות.",
        f"HEB_CAL_INSTANCE_NAME={validate_name(name)}",
        f"HEB_CAL_PORT={validate_port(port)}",
    ]
    host = getattr(cfg, "bind_host", None)
    if host:
        lines.append(f"HEB_CAL_BIND_HOST={host}")
    https = getattr(cfg, "tailscale_https_port", None)
    if https:
        lines.append(f"HEB_CAL_TAILSCALE_HTTPS_PORT={int(https)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o644)
    except OSError:
        pass
    return path


def parse_working_directory(text: str) -> Path | None:
    if not isinstance(text, str) or not text.strip():
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = WD_RE.match(line)
        if not match:
            continue
        value = _strip_quotes(match.group(1).strip())
        if not value or value.startswith("-"):
            return None
        try:
            return Path(value).expanduser()
        except (OSError, ValueError):
            return None
    return None


def parse_unit_port(text: str) -> int | None:
    if not isinstance(text, str) or not text:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        env_match = ENV_PORT_RE.match(line)
        if env_match:
            try:
                return validate_port(env_match.group(1))
            except InstanceError:
                continue
        exec_match = PORT_RE.search(line)
        if exec_match:
            try:
                return validate_port(exec_match.group(1))
            except InstanceError:
                continue
    return None


def _same_dir(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return os.path.normpath(str(left)) == os.path.normpath(str(right))


def read_unit_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def unit_owner(unit_dir: Path, unit_filename: str, root: Path) -> Path | None:
    """תיקייה אחרת שכבר מחזיקה את היחידה, או None אם פנויה/שלנו."""
    path = Path(unit_dir) / unit_filename
    if not path.is_file():
        return None
    text = read_unit_text(path)
    if text is None:
        return Path("<unreadable>")
    wd = parse_working_directory(text)
    if wd is None:
        return Path("<unknown>")
    if _same_dir(wd, Path(root)):
        return None
    return wd


def name_taken_by_other(unit_dir: Path, name: str, root: Path) -> Path | None:
    for filename in unit_names(name):
        other = unit_owner(unit_dir, filename, root)
        if other is not None:
            return other
    return None


def name_claimed_by_root(unit_dir: Path, root: Path) -> str | None:
    """שם שכבר מותקן לתיקייה הזו, לפי WorkingDirectory."""
    found: list[str] = []
    try:
        entries = list(Path(unit_dir).glob("*-web.service"))
    except OSError:
        return None
    for path in sorted(entries):
        name = name_from_web_unit(path.name)
        if not name:
            continue
        text = read_unit_text(path)
        if text is None:
            continue
        wd = parse_working_directory(text)
        if wd is not None and _same_dir(wd, Path(root)):
            found.append(name)
    if DEFAULT_NAME in found:
        return DEFAULT_NAME
    return found[0] if found else None


def candidate_names():
    yield DEFAULT_NAME
    n = 2
    while n < 10000:
        yield f"{DEFAULT_NAME}{n}"
        n += 1


def pick_instance_name(
    unit_dir: Path,
    root: Path,
    *,
    requested: str | None = None,
    saved: str | None = None,
) -> str:
    if requested:
        name = validate_name(requested)
        other = name_taken_by_other(unit_dir, name, root)
        if other is not None:
            raise InstanceError(_overwrite_message(name, other), overwrite=True)
        return name
    if saved:
        name = validate_name(saved)
        other = name_taken_by_other(unit_dir, name, root)
        if other is not None:
            raise InstanceError(_overwrite_message(name, other), overwrite=True)
        return name
    claimed = name_claimed_by_root(unit_dir, root)
    if claimed:
        return claimed
    for name in candidate_names():
        if name_taken_by_other(unit_dir, name, root) is None:
            return name
    raise InstanceError("לא נמצא שם פנוי למופע.")


def _overwrite_message(name: str, other: Path) -> str:
    web, worker = unit_names(name)
    other_text = str(other)
    if other_text in {"<unknown>", "<unreadable>"}:
        other_text = "תיקייה אחרת (לא זוהה WorkingDirectory)"
    return (
        f"היחידות {web} / {worker} כבר שייכות לתיקייה אחרת:\n"
        f"  {other_text}\n"
        "לא דורסים יחידות של מופע אחר. "
        f"הריצו עם --name {DEFAULT_NAME}2 (או שם אחר), או מתוך התיקייה הקיימת."
    )


def port_from_own_units(unit_dir: Path, name: str, root: Path) -> int | None:
    for filename in unit_names(name):
        path = Path(unit_dir) / filename
        if not path.is_file():
            continue
        text = read_unit_text(path)
        if text is None:
            continue
        wd = parse_working_directory(text)
        if wd is None or not _same_dir(wd, Path(root)):
            continue
        port = parse_unit_port(text)
        if port is not None:
            return port
    return None


def occupied_unit_ports(unit_dir: Path, root: Path) -> set[int]:
    occupied: set[int] = set()
    try:
        entries = list(Path(unit_dir).glob("*.service"))
    except OSError:
        return occupied
    for path in entries:
        text = read_unit_text(path)
        if text is None:
            continue
        wd = parse_working_directory(text)
        if wd is not None and _same_dir(wd, Path(root)):
            continue
        port = parse_unit_port(text)
        if port is not None:
            occupied.add(port)
    return occupied


def default_port_in_use(port: int) -> bool:
    for host in ("127.0.0.1", "0.0.0.0"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((host, port))
        except OSError:
            return True
    return False


def pick_port(
    *,
    requested: int | None,
    saved: int | None,
    env_port: int | None,
    is_first_instance: bool,
    occupied: set[int],
    port_in_use: Callable[[int], bool] | None = None,
) -> int:
    checker = port_in_use or default_port_in_use
    if requested is not None:
        port = validate_port(requested)
        if port in occupied:
            raise InstanceError(
                f"פורט {port} כבר מוגדר ביחידת systemd של מופע אחר. בחרו --port אחר.",
                overwrite=True,
            )
        return port
    if saved is not None:
        return validate_port(saved)
    if is_first_instance:
        if env_port is not None:
            return validate_port(env_port)
        return DEFAULT_PORT
    port = NEW_INSTANCE_PORT_START
    while port <= 65535:
        if port not in occupied and not checker(port):
            return port
        port += 1
    raise InstanceError("אין פורט TCP פנוי מ-5001 ומעלה.")


def resolve_install(
    root: Path,
    unit_dir: Path,
    *,
    requested_name: str | None = None,
    requested_port: int | None = None,
    env_port: int | None = None,
    port_in_use: Callable[[int], bool] | None = None,
) -> InstallPlan:
    root = Path(root)
    unit_dir = Path(unit_dir)
    saved = load_instance_config(root)
    claimed = name_claimed_by_root(unit_dir, root)
    name = pick_instance_name(
        unit_dir,
        root,
        requested=requested_name,
        saved=saved.name,
    )
    reused = bool(saved.name or claimed)
    is_first = name == DEFAULT_NAME and (
        reused or name_taken_by_other(unit_dir, DEFAULT_NAME, root) is None
    )
    own_port = port_from_own_units(unit_dir, name, root) if reused else None
    port = pick_port(
        requested=requested_port,
        saved=(saved.port or own_port) if reused else None,
        env_port=env_port if is_first else None,
        is_first_instance=is_first,
        occupied=occupied_unit_ports(unit_dir, root),
        port_in_use=port_in_use,
    )
    web, worker = unit_names(name)
    return InstallPlan(
        name=name,
        port=port,
        web_unit=web,
        worker_unit=worker,
        reused=reused,
        bind_host=saved.bind_host,
        tailscale_https_port=saved.tailscale_https_port,
    )


def env_port_from_dotenv(root: Path) -> int | None:
    explicit = (os.environ.get("HEB_CAL_PORT") or "").strip()
    if explicit:
        try:
            return validate_port(explicit)
        except InstanceError:
            pass
    path = Path(root) / ".env"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    found = None
    for raw in text.splitlines():
        line = raw.strip().replace("\r", "")
        if line.startswith("HEB_CAL_PORT="):
            value = _strip_quotes(line.split("=", 1)[1])
            try:
                found = validate_port(value)
            except InstanceError:
                found = None
    return found


def used_https_ports(status_text: str = "", status_json: str = "") -> set[int]:
    used: set[int] = set()
    blob = status_json.strip() if isinstance(status_json, str) else ""
    if blob:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            tcp = data.get("TCP")
            if isinstance(tcp, dict):
                for key in tcp:
                    try:
                        used.add(int(key))
                    except (TypeError, ValueError):
                        continue
            web = data.get("Web")
            if isinstance(web, dict):
                for key in web:
                    if not isinstance(key, str):
                        continue
                    host, sep, port_text = key.rpartition(":")
                    if sep and port_text.isdigit():
                        used.add(int(port_text))
                    else:
                        used.add(443)
    text = status_text if isinstance(status_text, str) else ""
    for match in re.finditer(r"https://[A-Za-z0-9._-]+(?::(\d+))?", text):
        if match.group(1):
            used.add(int(match.group(1)))
        else:
            used.add(443)
    for match in re.finditer(r'":(\d+)"', text):
        used.add(int(match.group(1)))
    return used


def existing_https_port_for_proxy(
    proxy_port: int,
    status_text: str = "",
    status_json: str = "",
) -> int | None:
    needles = (
        f"127.0.0.1:{proxy_port}",
        f"localhost:{proxy_port}",
        f"[::1]:{proxy_port}",
    )
    blob = status_json.strip() if isinstance(status_json, str) else ""
    if blob:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            web = data.get("Web")
            if isinstance(web, dict):
                for key, spec in web.items():
                    if not isinstance(spec, dict):
                        continue
                    handlers = spec.get("Handlers") or {}
                    dumped = json.dumps(handlers)
                    if any(n in dumped for n in needles):
                        if isinstance(key, str) and ":" in key:
                            _, _, port_text = key.rpartition(":")
                            if port_text.isdigit():
                                return int(port_text)
                        return 443
    text = status_text if isinstance(status_text, str) else ""
    if any(n in text for n in needles):
        # נסה לשלוף את פורט ה-HTTPS מהשורה הקודמת.
        lines = text.splitlines()
        last_https = None
        for line in lines:
            match = re.search(r"https://[A-Za-z0-9._-]+(?::(\d+))?", line)
            if match:
                last_https = int(match.group(1)) if match.group(1) else 443
            if any(n in line for n in needles):
                return last_https
    return None


def pick_https_port(
    status_text: str = "",
    status_json: str = "",
    *,
    proxy_port: int | None = None,
    start: int = HTTPS_PORT_START,
) -> tuple[int, bool]:
    """מחזיר (פורט HTTPS, האם מיפוי קיים כבר ל-proxy_port)."""
    if proxy_port is not None:
        existing = existing_https_port_for_proxy(proxy_port, status_text, status_json)
        if existing is not None:
            return existing, True
    used = used_https_ports(status_text, status_json)
    used |= set(RESERVED_HTTPS_PORTS)
    port = start
    while port <= 65535:
        if port not in used:
            return port, False
        port += 1
    raise InstanceError("אין פורט HTTPS פנוי מ-10000 ומעלה.")


def magic_dns_name(status_json: str = "") -> str | None:
    blob = (status_json or "").strip()
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    self = data.get("Self")
    if isinstance(self, dict):
        name = self.get("DNSName") or self.get("HostName")
        if isinstance(name, str) and name.strip():
            return name.strip().rstrip(".")
    return None


def format_plan(plan: InstallPlan) -> str:
    lines = [
        f"INSTANCE_NAME={plan.name}",
        f"PORT={plan.port}",
        f"WEB_UNIT={plan.web_unit}",
        f"WORKER_UNIT={plan.worker_unit}",
        f"REUSED={'1' if plan.reused else '0'}",
    ]
    if plan.tailscale_https_port:
        lines.append(f"TAILSCALE_HTTPS_PORT={plan.tailscale_https_port}")
    return "\n".join(lines) + "\n"


def _cmd_resolve(args: argparse.Namespace) -> int:
    try:
        requested_port = validate_port(args.port) if args.port is not None else None
        env_port = env_port_from_dotenv(Path(args.root))
        plan = resolve_install(
            Path(args.root),
            Path(args.unit_dir),
            requested_name=args.name,
            requested_port=requested_port,
            env_port=env_port,
        )
    except InstanceError as exc:
        sys.stderr.write(exc.message + "\n")
        return OVERWRITE_EXIT if exc.overwrite else 1
    save_instance_config(Path(args.root), plan)
    sys.stdout.write(format_plan(plan))
    return 0


def _read_optional(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _cmd_pick_https(args: argparse.Namespace) -> int:
    status = args.status or _read_optional(args.status_file)
    payload = args.json or _read_optional(args.json_file)
    try:
        proxy = validate_port(args.proxy_port) if args.proxy_port is not None else None
        port, existing = pick_https_port(status, payload, proxy_port=proxy)
    except InstanceError as exc:
        sys.stderr.write(exc.message + "\n")
        return 1
    sys.stdout.write(f"HTTPS_PORT={port}\nEXISTING={'1' if existing else '0'}\n")
    return 0


def _cmd_magic_dns(args: argparse.Namespace) -> int:
    payload = args.json or _read_optional(args.json_file)
    name = magic_dns_name(payload)
    if name:
        sys.stdout.write(name + "\n")
        return 0
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="בחירת שם ופורט למופע HEB-CAL")
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve", help="בחר שם ופורט ושמור ל-data/instance.env")
    resolve.add_argument("--root", required=True)
    resolve.add_argument("--unit-dir", required=True)
    resolve.add_argument("--name", default=None)
    resolve.add_argument("--port", default=None)
    resolve.set_defaults(func=_cmd_resolve)

    https = sub.add_parser("pick-https", help="פורט HTTPS פנוי ל-tailscale serve")
    https.add_argument("--status", default="")
    https.add_argument("--json", default="")
    https.add_argument("--status-file", default=None)
    https.add_argument("--json-file", default=None)
    https.add_argument("--proxy-port", default=None)
    https.set_defaults(func=_cmd_pick_https)

    dns = sub.add_parser("magic-dns", help="שם MagicDNS מ-tailscale status --json")
    dns.add_argument("--json", default="")
    dns.add_argument("--json-file", default=None)
    dns.set_defaults(func=_cmd_magic_dns)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
