from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from apple_refurb_watch.listing import products_in_listen_scope
from apple_refurb_watch.parse import product_page_url
from apple_refurb_watch.watches import (
    appeared_spec_line,
    spec_line_from_message,
    watch_condition_chips,
)


def _display_tz():
    try:
        import tzdata  # noqa: F401
    except ImportError:
        pass
    try:
        return ZoneInfo("Asia/Shanghai")
    except Exception:  # noqa: BLE001
        return timezone(timedelta(hours=8))


DISPLAY_TZ = _display_tz()


def parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        stamp = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def format_localtime(iso: str | None) -> str:
    stamp = parse_iso(iso)
    if stamp is None:
        return str(iso or "")
    return stamp.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M")


def load_status(database) -> dict[str, Any]:
    settings = database.settings()
    data = database.scan_status()
    watch_enabled = database.count_watches(enabled=True)
    watch_total = database.count_watches()
    in_stock = len(products_in_listen_scope(database.list_products(in_stock=True), settings.get("listings")))
    data["settings"] = {
        k: settings[k]
        for k in ("interval_seconds", "bind_host", "bind_port", "lan_enabled", "listings", "listen_enabled")
    }
    data["watch_count"] = watch_enabled
    data["watch_total"] = watch_total
    data["in_stock"] = in_stock
    data["view"] = present_status(
        data,
        settings,
        in_stock=in_stock,
        watch_enabled=watch_enabled,
        watch_total=watch_total,
    )
    return data


def present_status(
    status: dict[str, Any],
    settings: dict[str, Any],
    *,
    in_stock: int,
    watch_enabled: int,
    watch_total: int,
) -> dict[str, Any]:
    interval = int(settings.get("interval_seconds") or 300)
    interval_label = format_interval(interval)
    last_ok = format_reltime(status.get("last_success_at"))
    err = str(status.get("last_error") or "").strip()
    err_short = err[:96] + ("…" if len(err) > 96 else "")
    baseline = bool(status.get("baseline_done"))

    listen_enabled = bool(settings.get("listen_enabled", True))

    if status.get("scanning"):
        state, label = "busy", "正在扫描"
        detail = f"正在对照官网在售列表 · 当前库存 {in_stock} 件 · {interval_label}"
    elif not listen_enabled:
        state, label = "stopped", "已停止"
        extra = f"上次成功 {last_ok}" if last_ok else "还没有成功扫描"
        detail = f"定时扫描已暂停，网页仍可用 · {extra}"
    elif err:
        state, label = "bad", "扫描失败"
        detail = err_short + (f" · 上次成功 {last_ok}" if last_ok else " · 还没有成功扫描")
    elif not status.get("last_success_at"):
        state, label = "idle", "尚未扫描"
        detail = f"点「立即扫描」拉取官网在售 · {interval_label}"
    elif not baseline:
        state, label = "idle", "基线未完成"
        detail = f"上次 {last_ok} · 首次成功扫描后才会上新通知"
    else:
        state, label = "ok", "监听中"
        detail = f"上次成功 {last_ok} · {in_stock} 件在售 · {watch_enabled}/{watch_total} 条规则启用 · {interval_label}"

    return {
        "state": state,
        "label": label,
        "detail": detail,
        "last_success": last_ok or "无",
        "interval_label": interval_label,
        "in_stock": in_stock,
        "watch_enabled": watch_enabled,
        "watch_total": watch_total,
        "baseline_done": baseline,
        "baseline_label": "已完成" if baseline else "未完成",
        "last_error": err_short,
        "scanning": bool(status.get("scanning")),
        "listen_enabled": listen_enabled,
    }


def format_interval(seconds: int) -> str:
    seconds = max(1, int(seconds))
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"每 {hours} 小时"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"每 {minutes} 分钟"
    return f"每 {seconds} 秒"


def format_reltime(iso: str | None) -> str:
    stamp = parse_iso(iso)
    if stamp is None:
        return str(iso or "")
    now = datetime.now(timezone.utc)
    delta = now - stamp.astimezone(timezone.utc)
    secs = int(delta.total_seconds())
    if secs < 20:
        return "刚刚"
    if secs < 3600:
        return f"{max(1, secs // 60)} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    return stamp.astimezone(DISPLAY_TZ).strftime("%m-%d %H:%M")


EVENT_LABELS = {
    "scan_ok": "扫描完成",
    "scan": "扫描完成",
    "scan_partial": "部分完成",
    "appeared": "上新",
    "baseline": "已建基线",
    "scan_error": "扫描失败",
}


def _event_kind(event_type: str) -> str:
    if event_type == "appeared":
        return "appear"
    if event_type == "scan_error":
        return "error"
    if event_type == "baseline":
        return "baseline"
    return "routine"


def _watch_id(event: dict[str, Any]) -> int | None:
    raw = event.get("watch_id")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _present_event(
    event: dict[str, Any],
    watch_names: dict[int, str] | None = None,
    watches: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    event_type = str(event.get("type") or "")
    local = format_localtime(event.get("created_at"))
    label = EVENT_LABELS.get(event_type, event_type)
    watch_id = _watch_id(event)
    watch = (watches or {}).get(watch_id) if watch_id is not None else None
    name = None
    if watch_id is not None:
        if watch and watch.get("name"):
            name = str(watch.get("name") or "")
        elif watch_names:
            name = watch_names.get(watch_id)
    if event_type == "appeared" and name:
        label = f"上新 · {name}"
    spec_line = _event_spec_line(event)
    chips = watch_condition_chips(watch) if event_type == "appeared" else []
    return {
        "created_at": event.get("created_at"),
        "type": event_type,
        "label": label,
        "kind": _event_kind(event_type),
        "when_local": local,
        "title": event.get("title"),
        "message": event.get("message"),
        "url": product_page_url(event.get("sku"), event.get("url")),
        "sku": event.get("sku"),
        "watch_id": event.get("watch_id"),
        "price": event.get("price"),
        "ram_gb": event.get("ram_gb"),
        "storage_gb": event.get("storage_gb"),
        "spec_line": spec_line,
        "watch_chips": chips,
        "day": local[:10] if len(local) >= 10 else local,
    }


def _has_capacity(text: str) -> bool:
    return "内存" in text or "硬盘" in text


def _event_spec_line(event: dict[str, Any]) -> str:
    from_fields = appeared_spec_line(
        ram_gb=event.get("ram_gb"),
        storage_gb=event.get("storage_gb"),
        price=event.get("price"),
    )
    from_message = spec_line_from_message(event.get("message"))
    if _has_capacity(from_fields):
        return from_fields
    if _has_capacity(from_message):
        return from_message
    return from_fields or from_message


def _routine_summary(routines: list[dict[str, Any]]) -> dict[str, Any]:
    latest = max(routines, key=lambda item: str(item.get("created_at") or ""))
    summary = dict(latest)
    count = len(routines)
    if count == 1:
        return summary
    clock = latest["when_local"][11:] if len(str(latest["when_local"])) >= 16 else latest["when_local"]
    detail = latest.get("message") or ""
    summary["message"] = f"{count} 次扫描 · 最近 {clock}" + (f" · {detail}" if detail else "")
    return summary


def _collapse_day_scans(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    routines = [item for item in entries if item.get("kind") == "routine"]
    rest = [item for item in entries if item.get("kind") != "routine"]
    if not routines:
        return rest
    summary = _routine_summary(routines) if len(routines) > 1 else routines[0]
    return [summary, *rest]


EVENT_PAGE_SIZE = 20
EVENT_DAY_PAGE_SIZE = 7


def present_event_days(
    events: list[dict[str, Any]],
    *,
    collapse_scans: bool = False,
    watch_names: dict[int, str] | None = None,
    watches: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    presented = [_present_event(event, watch_names, watches) for event in events]
    presented.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    days: list[dict[str, Any]] = []
    for item in presented:
        if not days or days[-1]["day"] != item["day"]:
            days.append({"day": item["day"], "entries": [item]})
        else:
            days[-1]["entries"].append(item)
    out: list[dict[str, Any]] = []
    for day in days:
        entries = _collapse_day_scans(day["entries"]) if collapse_scans else list(day["entries"])
        out.append({"day": day["day"], "entries": entries})
    return out


def _page_index(page: int, pages: int) -> int:
    try:
        page_i = int(page)
    except (TypeError, ValueError):
        page_i = 1
    return min(max(1, page_i), pages)


def paginate_event_days(
    days: list[dict[str, Any]],
    page: int,
    page_size: int | None = None,
    *,
    by_day: bool = False,
) -> dict[str, Any]:
    if page_size is None:
        page_size = EVENT_DAY_PAGE_SIZE if by_day else EVENT_PAGE_SIZE
    page_size = max(1, int(page_size))
    entry_total = sum(len(day.get("entries") or []) for day in days)
    day_total = len(days)
    if by_day:
        unit_total = day_total
        pages = max(1, (unit_total + page_size - 1) // page_size) if unit_total else 1
        page_i = _page_index(page, pages)
        start = (page_i - 1) * page_size
        grouped = days[start : start + page_size]
    else:
        flat: list[tuple[str, dict[str, Any]]] = [
            (str(day.get("day") or ""), entry)
            for day in days
            for entry in day.get("entries") or []
        ]
        unit_total = len(flat)
        pages = max(1, (unit_total + page_size - 1) // page_size) if unit_total else 1
        page_i = _page_index(page, pages)
        start = (page_i - 1) * page_size
        grouped = []
        for day_key, entry in flat[start : start + page_size]:
            if not grouped or grouped[-1]["day"] != day_key:
                grouped.append({"day": day_key, "entries": [entry]})
            else:
                grouped[-1]["entries"].append(entry)
    return {
        "event_days": grouped,
        "event_page": page_i,
        "event_pages": pages,
        "event_total": entry_total,
        "event_day_total": day_total,
        "has_prev": page_i > 1,
        "has_next": page_i < pages,
    }


def filter_event_days(days: list[dict[str, Any]], kind: str | None) -> list[dict[str, Any]]:
    if not kind or kind == "all":
        return days
    wanted = {"appear": "appear", "error": "error"}.get(kind)
    if not wanted:
        return days
    out: list[dict[str, Any]] = []
    for day in days:
        entries = [item for item in day["entries"] if item.get("kind") == wanted]
        if entries:
            out.append({"day": day["day"], "entries": entries})
    return out
