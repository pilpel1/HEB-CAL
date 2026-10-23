"""קריאת releases מ-GitHub. הטוקן נשלח רק בכותרת, אף פעם לא ב-URL ובלי לוג."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

from app.updates.errors import UpdateError
from app.updates.version import (
    highlights_from_body,
    parse_version,
    safe_release_url,
    valid_slug,
    version_text,
)


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    highlights: list[str]
    url: str | None


def github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "heb-cal-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _api_url(repo: str, kind: str) -> str:
    if not valid_slug(repo):
        raise UpdateError("מאגר GitHub לא תקין.", step="fetch")
    owner, name = repo.split("/")
    return (
        f"https://api.github.com/repos/{quote(owner)}/{quote(name)}/{kind}?per_page=30"
    )


def urllib_get(url: str, headers: dict[str, str], timeout: float = 15):
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_000)
            return response.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # לא קוראים את גוף השגיאה — הוא לא נחוץ ויכול להיות ארוך.
        return exc.code, None
    except urllib.error.URLError as exc:
        raise UpdateError("אין חיבור ל-GitHub.", step="fetch") from exc
    except (json.JSONDecodeError, TimeoutError, OSError) as exc:
        raise UpdateError("לא הצלחנו לקרוא את התשובה מ-GitHub.", step="fetch") from exc


def _release_from_tag(tag: str, body: str | None, url: str | None) -> Release | None:
    parts = parse_version(tag)
    if parts is None:
        return None
    return Release(
        version=version_text(parts),
        tag=tag.strip(),
        highlights=highlights_from_body(body),
        url=safe_release_url(url),
    )


def parse_releases(payload) -> list[Release]:
    if not isinstance(payload, list):
        raise UpdateError("תשובה לא צפויה מ-GitHub.", step="fetch")
    found: list[Release] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("draft") or item.get("prerelease"):
            continue
        tag = item.get("tag_name")
        if not isinstance(tag, str):
            continue
        release = _release_from_tag(tag, item.get("body") if isinstance(item.get("body"), str) else "", item.get("html_url"))
        if release is not None:
            found.append(release)
    found.sort(key=lambda item: parse_version(item.version) or (0, 0, 0), reverse=True)
    return found


def parse_tags(payload) -> list[Release]:
    if not isinstance(payload, list):
        raise UpdateError("תשובה לא צפויה מ-GitHub.", step="fetch")
    found: list[Release] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        release = _release_from_tag(name, "", None)
        if release is not None:
            found.append(release)
    found.sort(key=lambda item: parse_version(item.version) or (0, 0, 0), reverse=True)
    return found


def _reject_status(status: int) -> None:
    if status == 401:
        raise UpdateError(
            "GitHub דחה את הטוקן. בדקו את HEB_CAL_GITHUB_TOKEN.",
            step="fetch",
        )
    if status == 403:
        raise UpdateError(
            "GitHub דחה את הבדיקה. אם המאגר פרטי, בדקו את הטוקן. אחרת נסו שוב מאוחר יותר.",
            step="fetch",
        )
    if status == 404:
        raise UpdateError("המאגר לא נמצא ב-GitHub.", step="fetch")
    raise UpdateError("לא הצלחנו לבדוק מול GitHub.", step="fetch")


def fetch_latest(repo: str, token: str | None, getter=urllib_get) -> Release | None:
    headers = github_headers(token)
    status, body = getter(_api_url(repo, "releases"), headers)
    releases: list[Release] = []
    if status == 200:
        releases = parse_releases(body)
    elif status == 404:
        releases = []
    else:
        _reject_status(status)
    if releases:
        return releases[0]
    tag_status, tag_body = getter(_api_url(repo, "tags"), headers)
    if tag_status == 200:
        tags = parse_tags(tag_body)
        return tags[0] if tags else None
    if tag_status == 404:
        return None
    _reject_status(tag_status)
    return None


def release_view(release: Release | None, current: str) -> dict:
    if release is None:
        return {
            "available": False,
            "latest": None,
            "tag": None,
            "highlights": [],
            "url": None,
            "current": current,
            "message": "לא פורסמה עדיין גרסה ב-GitHub.",
        }
    newer = parse_version(release.version) > parse_version(current) if parse_version(current) else False
    if newer:
        message = f"יש גרסה חדשה: {release.version}"
    elif parse_version(current) and parse_version(release.version) < parse_version(current):
        message = "הגרסה המותקנת חדשה ממה שמפורסם."
        newer = False
    else:
        message = "אתם על הגרסה האחרונה."
    return {
        "available": newer,
        "latest": release.version,
        "tag": release.tag,
        "highlights": release.highlights,
        "url": release.url,
        "current": current,
        "message": message,
    }
