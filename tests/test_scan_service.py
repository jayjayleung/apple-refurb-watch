from __future__ import annotations

import pytest

import apple_refurb_watch.scanner as scanner
from apple_refurb_watch.scanner import ScanService


class _DatabaseDouble:
    def __init__(self) -> None:
        self.settings_written: list[tuple[str, object]] = []

    def set_setting(self, key: str, value: object) -> None:
        self.settings_written.append((key, value))


class _SourceDouble:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def test_scan_service_reuses_source_and_closes_once(monkeypatch) -> None:
    database = _DatabaseDouble()
    source = _SourceDouble()
    calls = []

    monkeypatch.setattr(scanner, "ListingSource", lambda **_kwargs: source)

    def fake_run(db, current_source, hook, sleep_fn):
        calls.append((db, current_source, hook, sleep_fn))
        return {"ok": True}

    monkeypatch.setattr(scanner, "_run_scan_locked", fake_run)
    service = ScanService(database)
    assert service.run_once() == {"ok": True}
    assert service.run_once() == {"ok": True}
    assert len(calls) == 2
    assert calls[0][1] is source and calls[1][1] is source
    assert database.settings_written == [("scanning", False), ("scanning", False)]

    service.close()
    service.close()
    assert source.closed == 1
    with pytest.raises(RuntimeError, match="扫描服务已关闭"):
        service.run_once()
