from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from apple_refurb_watch import __version__
from apple_refurb_watch.paths import data_dir

GITHUB_REPO = "jayjayleung/apple-refurb-watch"
GITHUB_URL = f"https://github.com/{GITHUB_REPO}"
LATEST_RELEASE_URL = f"{GITHUB_URL}/releases/latest"
LATEST_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CACHE_NAME = "update-check.json"
CACHE_TTL_SECONDS = 12 * 3600
NEGATIVE_CACHE_TTL_SECONDS = 30 * 60
FetchLatest = Callable[[], str | None]


def version_key(ver: str | None) -> tuple[int, ...]:
    if not ver:
        return (0,)
    nums: list[int] = []
    for part in str(ver).replace("-", ".").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if digits:
            nums.append(int(digits))
    return tuple(nums) or (0,)


def parse_release_tag(tag: str | None) -> str:
    text = str(tag or "").strip()
    if text.lower().startswith("v") and len(text) > 1 and text[1].isdigit():
        return text[1:]
    return text


def is_newer(latest: str | None, current: str | None) -> bool:
    latest_text = parse_release_tag(latest)
    current_text = parse_release_tag(current)
    if not latest_text or not current_text:
        return False
    return version_key(latest_text) > version_key(current_text)


def cache_path() -> Path:
    return data_dir() / CACHE_NAME


def fetch_latest_tag() -> str | None:
    try:
        import httpx

        response = httpx.get(
            LATEST_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"apple-refurb-watch/{__version__}",
            },
            timeout=4.0,
            follow_redirects=True,
        )
        if response.status_code != 200:
            return None
        payload = response.json()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    tag = parse_release_tag(str(payload.get("tag_name") or ""))
    return tag or None


def _read_cache() -> dict[str, Any] | None:
    path = cache_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_cache(latest: str, checked_at: float) -> None:
    path = cache_path()
    payload = {"latest": latest, "checked_at": checked_at}
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def latest_release_info(
    *,
    current: str | None = None,
    now: float | None = None,
    fetch: FetchLatest | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    current_ver = parse_release_tag(current or __version__)
    checked_at = time.time() if now is None else float(now)
    cached = _read_cache()
    latest = ""
    if isinstance(cached, dict):
        latest = parse_release_tag(str(cached.get("latest") or ""))
        try:
            cached_at = float(cached.get("checked_at") or 0)
        except (TypeError, ValueError):
            cached_at = 0.0
        age = checked_at - cached_at
        if latest:
            fresh = age < CACHE_TTL_SECONDS
            if fresh and is_newer(current_ver, latest):
                fresh = False
        else:
            fresh = age >= 0 and age < NEGATIVE_CACHE_TTL_SECONDS
    else:
        fresh = False
    if refresh:
        fresh = False
    if not fresh:
        fetched = (fetch or fetch_latest_tag)()
        if fetched:
            latest = parse_release_tag(fetched)
            _write_cache(latest, checked_at)
        else:
            _write_cache(latest, checked_at)
    return {
        "ok": True,
        "current": current_ver,
        "latest": latest or None,
        "newer": is_newer(latest, current_ver),
        "url": LATEST_RELEASE_URL,
    }
