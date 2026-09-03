from apple_refurb_watch import __version__
from apple_refurb_watch.update_check import (
    LATEST_RELEASE_URL,
    is_newer,
    latest_release_info,
    parse_release_tag,
    version_key,
)


def test_parse_release_tag_strips_v() -> None:
    assert parse_release_tag("v0.3.3") == "0.3.3"
    assert parse_release_tag("0.3.3") == "0.3.3"
    assert parse_release_tag(" V1.2.0 ") == "1.2.0"


def test_is_newer_compares_semver() -> None:
    assert is_newer("0.3.4", "0.3.3")
    assert not is_newer("0.3.3", "0.3.3")
    assert not is_newer("0.3.2", "0.3.3")
    assert is_newer("v0.4.0", "0.3.9")
    assert version_key("0.3.10") > version_key("0.3.9")


def test_latest_release_info_uses_fetch_and_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    calls = {"n": 0}

    def fetch() -> str:
        calls["n"] += 1
        return "v9.9.9"

    first = latest_release_info(current="0.3.3", now=1000.0, fetch=fetch)
    assert first["ok"] is True
    assert first["current"] == "0.3.3"
    assert first["latest"] == "9.9.9"
    assert first["newer"] is True
    assert first["url"] == LATEST_RELEASE_URL
    assert calls["n"] == 1

    def boom() -> str:
        raise AssertionError("should use cache")

    cached = latest_release_info(current="0.3.3", now=1000.0 + 60, fetch=boom)
    assert cached["latest"] == "9.9.9"
    assert cached["newer"] is True


def test_latest_release_info_same_version_is_not_newer() -> None:
    info = latest_release_info(current=__version__, now=1.0, fetch=lambda: __version__)
    assert info["latest"] == __version__
    assert info["newer"] is False


def test_latest_release_info_refresh_ignores_fresh_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    latest_release_info(current="0.3.5", now=1000.0, fetch=lambda: "0.3.5")
    info = latest_release_info(
        current="0.3.5",
        now=1000.0 + 60,
        refresh=True,
        fetch=lambda: "v0.3.6",
    )
    assert info["latest"] == "0.3.6"
    assert info["newer"] is True


def test_latest_release_info_refetches_when_running_newer_than_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    latest_release_info(current="0.3.3", now=1000.0, fetch=lambda: "0.3.3")
    info = latest_release_info(current="0.3.6", now=1000.0 + 60, fetch=lambda: "v0.3.6")
    assert info["latest"] == "0.3.6"
    assert info["newer"] is False


def test_latest_release_info_fetch_failure_keeps_quiet() -> None:
    info = latest_release_info(current="0.3.3", now=1.0, fetch=lambda: None)
    assert info["latest"] is None
    assert info["newer"] is False
    assert info["url"] == LATEST_RELEASE_URL


def test_latest_release_info_failure_is_negatively_cached(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    calls = {"n": 0}

    def fetch() -> str | None:
        calls["n"] += 1
        return None

    first = latest_release_info(current="0.3.3", now=1000.0, fetch=fetch)
    assert first["latest"] is None
    assert calls["n"] == 1

    def boom() -> str:
        raise AssertionError("should use negative cache")

    cached = latest_release_info(current="0.3.3", now=1000.0 + 60, fetch=boom)
    assert cached["latest"] is None
    assert calls["n"] == 1
    later = latest_release_info(current="0.3.3", now=1000.0 + 31 * 60, fetch=lambda: "v0.4.0")
    assert later["latest"] == "0.4.0"
