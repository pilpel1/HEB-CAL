"""PWA בסיסי: מניפסט מקושר, אייקונים, ו-/sw.js עם scope לשורש."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == PNG_MAGIC
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


@pytest.mark.parametrize("page", ["/", "/events_list", "/settings"])
def test_pages_link_manifest_and_register_sw(client, page):
    html = client.get(page).get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert "manifest.webmanifest" in html
    assert 'rel="apple-touch-icon"' in html
    assert "icons/icon-192.png" in html
    assert 'name="theme-color"' in html
    assert "#2563eb" in html
    assert "serviceWorker" in html
    assert "navigator.serviceWorker.register('/sw.js')" in html
    assert "isSecureContext" in html


def test_manifest_has_installable_fields(client):
    response = client.get("/static/manifest.webmanifest")
    assert response.status_code == 200
    ctype = response.headers["Content-Type"]
    assert "manifest+json" in ctype or "json" in ctype
    manifest = json.loads(response.get_data(as_text=True))
    assert manifest["name"]
    assert manifest["short_name"]
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["theme_color"] == "#2563eb"
    assert manifest["background_color"] == "#f8fafc"
    assert manifest["dir"] == "rtl"
    assert manifest["lang"] == "he"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert "192x192" in sizes
    assert "512x512" in sizes
    for icon in manifest["icons"]:
        src = icon["src"]
        path = src if src.startswith("/") else f"/static/{src}"
        icon_resp = client.get(path)
        assert icon_resp.status_code == 200, path
        body = icon_resp.get_data()
        assert body[:8] == PNG_MAGIC
        width, height = _png_size(body)
        expected = int(icon["sizes"].split("x", 1)[0])
        assert (width, height) == (expected, expected)


def test_service_worker_is_served_from_root(client):
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["Content-Type"]
    assert response.headers.get("Service-Worker-Allowed") == "/"
    body = response.get_data(as_text=True)
    assert "addEventListener('fetch'" in body or 'addEventListener("fetch"' in body
    assert "caches" in body
    assert "/api/" in body
    assert "pathname.startsWith('/api/')" in body or 'pathname.startsWith("/api/")' in body
    # לא תחת js/ — test_static_scripts דורש שכל קובץ שם ייטען כ־<script src>
    assert not (REPO / "app" / "static" / "js" / "sw.js").exists()
    static_copy = client.get("/static/sw.js")
    assert static_copy.status_code == 200
