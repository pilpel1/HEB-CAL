"""hebcal:read ו-hebcal:write. write כולל read."""
from __future__ import annotations

SCOPES = ("hebcal:read", "hebcal:write")
_KNOWN = frozenset(SCOPES)


def parse_scopes(value) -> list[str] | None:
    if value in (None, ""):
        return ["hebcal:read"]
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value]
    else:
        parts = str(value).split()
    wanted = []
    seen = set()
    for item in parts:
        if not item:
            continue
        if item not in _KNOWN:
            return None
        if item in seen:
            continue
        seen.add(item)
        wanted.append(item)
    if not wanted:
        return ["hebcal:read"]
    if "hebcal:write" in seen and "hebcal:read" not in seen:
        wanted.insert(0, "hebcal:read")
    return wanted


def permission_for(scopes: list[str] | str) -> str:
    if isinstance(scopes, str):
        items = scopes.split()
    else:
        items = list(scopes)
    return "write" if "hebcal:write" in items else "read"


def scope_string(scopes: list[str]) -> str:
    return " ".join(scopes)
