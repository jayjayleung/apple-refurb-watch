from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")


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


def _present_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("type") or "")
    local = format_localtime(event.get("created_at"))
    return {
        "created_at": event.get("created_at"),
        "type": event_type,
        "label": EVENT_LABELS.get(event_type, event_type),
        "kind": _event_kind(event_type),
        "when_local": local,
        "title": event.get("title"),
        "message": event.get("message"),
        "url": event.get("url"),
        "sku": event.get("sku"),
        "day": local[:10] if len(local) >= 10 else local,
    }


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


def present_event_days(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    days: list[dict[str, Any]] = []
    for event in events:
        item = _present_event(event)
        if not days or days[-1]["day"] != item["day"]:
            days.append({"day": item["day"], "items": [item]})
        else:
            days[-1]["items"].append(item)
    presented: list[dict[str, Any]] = []
    for day in days:
        primary = [item for item in day["items"] if item["kind"] != "routine"]
        routines = [item for item in day["items"] if item["kind"] == "routine"]
        entries = list(primary)
        if routines:
            entries.append(_routine_summary(routines))
        presented.append({"day": day["day"], "entries": entries})
    return presented
