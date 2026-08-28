from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
        "last_success": last_ok or "—",
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
    if not iso:
        return ""
    try:
        stamp = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - stamp.astimezone(timezone.utc)
    secs = int(delta.total_seconds())
    if secs < 20:
        return "刚刚"
    if secs < 3600:
        return f"{max(1, secs // 60)} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    local = stamp.astimezone()
    return local.strftime("%m-%d %H:%M")
