import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    if not report.failed or report.when not in {"setup", "call"}:
        return
    line = report.location[1] if report.location else 1
    msg = str(report.longrepr)[:1800].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::error file={report.nodeid},line={line or 1}::{msg}")


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
