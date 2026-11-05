"""בחירת שם ופורט למופע, בלי systemd אמיתי — קבצים ופורטים מדומים."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load():
    path = REPO / "scripts" / "instance_select.py"
    spec = importlib.util.spec_from_file_location("instance_select", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name or "instance_select"] = mod
    spec.loader.exec_module(mod)
    return mod


select = _load()


def _write_unit(unit_dir: Path, name: str, root: Path, port: int) -> None:
    unit_dir.mkdir(parents=True, exist_ok=True)
    web, worker = select.unit_names(name)
    body = (
        f"[Service]\nWorkingDirectory={root}\n"
        f"ExecStart=/usr/bin/python -m flask --app app run --host 127.0.0.1 --port {port}\n"
    )
    (unit_dir / web).write_text(body, encoding="utf-8")
    (unit_dir / worker).write_text(f"WorkingDirectory={root}\n", encoding="utf-8")


def test_default_name_and_port_when_nothing_exists(tmp_path):
    root = tmp_path / "HEB-CAL"
    root.mkdir()
    plan = select.resolve_install(root, tmp_path / "units")
    assert plan.name == "heb-cal"
    assert plan.port == 5000
    assert plan.web_unit == "heb-cal-web.service"
    assert plan.worker_unit == "heb-cal-worker.service"
    assert plan.socket_unit == "heb-cal-web.socket"
    assert plan.reused is False
    text = select.format_plan(plan)
    assert "SOCKET_UNIT=heb-cal-web.socket" in text
    assert "WEB_UNIT=heb-cal-web.service" in text


def test_parse_unit_port_from_environment_and_listen_stream():
    assert select.parse_unit_port("Environment=HEB_CAL_PORT=5001\n") == 5001
    assert select.parse_unit_port("ListenStream=127.0.0.1:5002\n") == 5002
    assert select.parse_unit_port("ListenStream=[::1]:5003\n") == 5003
    assert select.parse_unit_port(
        "ExecStart=/usr/bin/python scripts/run_web.py\nEnvironment=HEB_CAL_PORT=5004\n"
    ) == 5004
    assert select.parse_unit_port(
        "ExecStart=/usr/bin/python -m flask --app app run --port 5005\n"
    ) == 5005
    assert select.parse_listen_stream_port("0.0.0.0:5000") == 5000
    assert select.socket_unit_name("gisim") == "gisim-web.socket"


def test_occupied_ports_from_env_not_from_own_socket_without_wd(tmp_path):
    units = tmp_path / "units"
    other = tmp_path / "other"
    other.mkdir()
    root = tmp_path / "new"
    root.mkdir()
    units.mkdir()
    (units / "heb-cal-web.service").write_text(
        f"[Service]\nWorkingDirectory={other}\nEnvironment=HEB_CAL_PORT=5000\n"
        "ExecStart=/usr/bin/python scripts/run_web.py\n",
        encoding="utf-8",
    )
    (units / "heb-cal-worker.service").write_text(
        f"WorkingDirectory={other}\n",
        encoding="utf-8",
    )
    (units / "heb-cal-web.socket").write_text(
        "ListenStream=127.0.0.1:5000\n",
        encoding="utf-8",
    )
    occupied = select.occupied_unit_ports(units, root)
    assert 5000 in occupied
    with pytest.raises(select.InstanceError) as exc:
        select.resolve_install(root, units, requested_name="gisim", requested_port=5000)
    assert exc.value.overwrite is True


def test_first_instance_keeps_env_port(tmp_path):
    root = tmp_path / "HEB-CAL"
    root.mkdir()
    plan = select.resolve_install(root, tmp_path / "units", env_port=5000)
    assert plan.name == "heb-cal"
    assert plan.port == 5000


def test_reuses_saved_instance_name_and_port(tmp_path):
    root = tmp_path / "family2"
    root.mkdir()
    select.save_instance_config(
        root, select.InstanceConfig(name="heb-cal2", port=5007)
    )
    other = tmp_path / "first"
    other.mkdir()
    _write_unit(tmp_path / "units", "heb-cal", other, 5000)
    plan = select.resolve_install(root, tmp_path / "units")
    assert plan.name == "heb-cal2"
    assert plan.port == 5007
    assert plan.reused is True


def test_reuses_units_already_pointing_at_this_dir(tmp_path):
    root = tmp_path / "HEB-CAL"
    root.mkdir()
    units = tmp_path / "units"
    _write_unit(units, "heb-cal", root, 5000)
    plan = select.resolve_install(root, units)
    assert plan.name == "heb-cal"
    assert plan.port == 5000
    assert plan.reused is True


def test_auto_picks_heb_cal2_when_default_belongs_to_other_dir(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    units = tmp_path / "units"
    _write_unit(units, "heb-cal", first, 5000)
    busy = {5001, 5002}

    def port_in_use(port: int) -> bool:
        return port in busy

    plan = select.resolve_install(second, units, port_in_use=port_in_use)
    assert plan.name == "heb-cal2"
    assert plan.port == 5003
    assert plan.web_unit == "heb-cal2-web.service"
    assert plan.reused is False


def test_auto_picks_heb_cal3_when_two_and_three_needed(tmp_path):
    units = tmp_path / "units"
    _write_unit(units, "heb-cal", tmp_path / "a", 5000)
    _write_unit(units, "heb-cal2", tmp_path / "b", 5001)
    root = tmp_path / "c"
    root.mkdir()
    plan = select.resolve_install(
        root, units, port_in_use=lambda port: port in {5001, 5002}
    )
    assert plan.name == "heb-cal3"
    assert plan.port == 5003


def test_requested_name_refuses_to_overwrite_other_dir(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    units = tmp_path / "units"
    _write_unit(units, "heb-cal", other, 5000)
    before = (units / "heb-cal-web.service").read_text(encoding="utf-8")
    root = tmp_path / "new"
    root.mkdir()
    with pytest.raises(select.InstanceError) as exc:
        select.resolve_install(root, units, requested_name="heb-cal")
    assert exc.value.overwrite is True
    assert "heb-cal-web.service" in exc.value.message
    assert str(other) in exc.value.message
    assert (units / "heb-cal-web.service").read_text(encoding="utf-8") == before


def test_requested_port_refuses_if_other_unit_uses_it(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    units = tmp_path / "units"
    _write_unit(units, "heb-cal", other, 5000)
    root = tmp_path / "new"
    root.mkdir()
    with pytest.raises(select.InstanceError) as exc:
        select.resolve_install(root, units, requested_name="heb-cal2", requested_port=5000)
    assert exc.value.overwrite is True
    assert "5000" in exc.value.message


def test_new_instance_does_not_take_port_5000(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    units = tmp_path / "units"
    _write_unit(units, "heb-cal", other, 5000)
    root = tmp_path / "new"
    root.mkdir()
    plan = select.resolve_install(root, units, port_in_use=lambda port: False)
    assert plan.name == "heb-cal2"
    assert plan.port == 5001


def test_save_instance_config_is_gitignored_shape(tmp_path):
    root = tmp_path / "HEB-CAL"
    root.mkdir()
    path = select.save_instance_config(
        root, select.InstallPlan("heb-cal", 5000, "heb-cal-web.service", "heb-cal-worker.service", True)
    )
    text = path.read_text(encoding="utf-8")
    assert path == root / "data" / "instance.env"
    assert "HEB_CAL_INSTANCE_NAME=heb-cal" in text
    assert "HEB_CAL_PORT=5000" in text
    assert "TELEGRAM" not in text
    assert "SECRET" not in text
    loaded = select.load_instance_config(root)
    assert loaded.name == "heb-cal"
    assert loaded.port == 5000


def test_invalid_name_rejected():
    with pytest.raises(select.InstanceError):
        select.validate_name("HEB-CAL")
    with pytest.raises(select.InstanceError):
        select.validate_name("../etc")
    with pytest.raises(select.InstanceError):
        select.validate_name("heb cal")


def test_used_https_ports_and_pick(tmp_path):
    status = (
        "https://box.tailnet.ts.net (tailnet only)\n"
        "|-- / proxy http://127.0.0.1:80\n"
        "https://box.tailnet.ts.net:8443\n"
        "|-- / proxy http://127.0.0.1:9000\n"
        "https://box.tailnet.ts.net:10000\n"
        "|-- / proxy http://127.0.0.1:5000\n"
    )
    payload = """
    {
      "TCP": {"443": {"HTTPS": true}, "8443": {"HTTPS": true}, "10000": {"HTTPS": true}},
      "Web": {
        "box.tailnet.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:80"}}},
        "box.tailnet.ts.net:10000": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5000"}}}
      }
    }
    """
    used = select.used_https_ports(status, payload)
    assert 443 in used
    assert 8443 in used
    assert 10000 in used
    port, existing = select.pick_https_port(status, payload, proxy_port=5001)
    assert existing is False
    assert port == 10001
    port, existing = select.pick_https_port(status, payload, proxy_port=5000)
    assert existing is True
    assert port == 10000
    fresh, existed = select.pick_https_port("", "{}", proxy_port=9)
    assert existed is False
    assert fresh == 10000
    assert fresh not in {443, 8443}


def test_magic_dns_strips_trailing_dot():
    payload = '{"Self": {"DNSName": "homeserver.tailnet.ts.net."}}'
    assert select.magic_dns_name(payload) == "homeserver.tailnet.ts.net"
