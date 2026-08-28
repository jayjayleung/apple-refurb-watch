from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("APPLE_REFURB_WATCH_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("APPLE_REFURB_WATCH_LOG", str(tmp_path / "logs"))


@pytest.fixture
def listing_html() -> str:
    return (FIXTURES / "listing_mac.html").read_text(encoding="utf-8")


@pytest.fixture
def detail_html() -> str:
    return (FIXTURES / "product_detail.html").read_text(encoding="utf-8")
