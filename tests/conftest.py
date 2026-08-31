import os
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
_FAILURES: list[str] = []


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if not report.failed or report.when not in {"setup", "call"}:
        return
    _FAILURES.append(f"{report.nodeid}\n{report.longrepr}\n")


def pytest_sessionfinish(session, exitstatus) -> None:
    if not _FAILURES:
        return
    text = "\n".join(_FAILURES)
    Path("pytest-failures.txt").write_text(text, encoding="utf-8")
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    msg = text[:1500].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    sys.__stdout__.write(f"::error::{msg}\n")
    sys.__stdout__.flush()


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
