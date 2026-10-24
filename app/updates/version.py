"""מספר גרסה, תג GitHub, ועיקרי שינויים. התג הוא המקור — לא מחרוזת מהדפדפן."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from app.database import BASE_DIR
from app.updates.errors import UpdateError

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")

DEFAULT_REPO = "pilpel1/HEB-CAL"


def parse_version(value: str | None) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = _SEMVER.fullmatch(value.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def version_text(parts: tuple[int, int, int]) -> str:
    return f"{parts[0]}.{parts[1]}.{parts[2]}"


def normalize_version(value: str) -> str:
    parts = parse_version(value)
    if parts is None:
        raise UpdateError("מספר גרסה לא תקין.", step="version")
    return version_text(parts)


def is_newer(candidate: str, current: str) -> bool:
    left = parse_version(candidate)
    right = parse_version(current)
    if left is None or right is None:
        return False
    return left > right


def validate_tag(tag: str) -> str:
    """תג שמותר להעביר ל-git כארגומנט נפרד. בלי רווחים ובלי תווים של מעטפת."""
    if not isinstance(tag, str) or parse_version(tag) is None:
        raise UpdateError("תג הגרסה לא תקין.", step="checkout")
    if tag.strip() != tag or any(ch.isspace() for ch in tag):
        raise UpdateError("תג הגרסה לא תקין.", step="checkout")
    return tag


def validate_sha(sha: str) -> str:
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise UpdateError("מצב ה-git לא תקין.", step="checkout")
    return sha


def tag_matches_version(tag: str, version: str) -> bool:
    return parse_version(tag) == parse_version(version) and parse_version(tag) is not None


def read_version_file(path: Path | None = None) -> str:
    file = path or (BASE_DIR / "VERSION")
    try:
        text = file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise UpdateError("קובץ VERSION חסר.", step="version") from exc
    return normalize_version(text)


def installed_version() -> str:
    try:
        return read_version_file()
    except UpdateError:
        return "לא ידועה"


def valid_slug(slug: str) -> bool:
    if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
        return False
    owner, name = slug.split("/")
    return owner not in {".", ".."} and name not in {".", ".."}


def parse_github_slug(remote: str) -> str | None:
    """מוציא owner/name מכתובת remote. הטוקן שב-URL לא חוזר החוצה."""
    if not isinstance(remote, str):
        return None
    text = remote.strip()
    if not text or "\n" in text or "\x00" in text:
        return None
    if "://" in text:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
        if host != "github.com":
            return None
        path = parts.path.strip("/")
        if path.endswith(".git"):
            path = path[: -len(".git")]
        segments = [segment for segment in path.split("/") if segment]
        if len(segments) < 2:
            return None
        slug = f"{segments[0]}/{segments[1]}"
        return slug if valid_slug(slug) else None
    match = re.fullmatch(r"git@github\.com:([^/\s]+)/([^/\s]+?)(?:\.git)?", text)
    if not match:
        return None
    slug = f"{match.group(1)}/{match.group(2)}"
    return slug if valid_slug(slug) else None


def highlights_from_body(body: str | None, limit: int = 6) -> list[str]:
    """שורות קצרות מתוך גוף ה-release. בלי HTML — המסך שם אותן כטקסט."""
    if not isinstance(body, str) or not body.strip():
        return []
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        line = line.replace("\x00", "").strip()
        if not line:
            continue
        if len(line) > 180:
            line = line[:177] + "…"
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def safe_release_url(url: str | None) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() != "github.com":
        return None
    return url
