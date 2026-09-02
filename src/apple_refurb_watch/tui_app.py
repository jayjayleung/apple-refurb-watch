from __future__ import annotations

import math
import threading
import time
from typing import Any, Callable

from apple_refurb_watch.categories import SHOP_FAMILIES, listing_family_name, shop_families_for, shop_family_key
from apple_refurb_watch.client import ApiClient, ApiError
from apple_refurb_watch.connection import check_client_compat, load_connection, resolve_client
from apple_refurb_watch.filters import dim_spec, normalize_dim_filters, restrict_dims
from apple_refurb_watch.listing import format_cny, format_gb
from apple_refurb_watch.status_view import EVENT_LABELS, format_localtime, present_event_days
from apple_refurb_watch.watches import watch_condition_label, watch_from_product, watch_name_from_filters


def _parse_dims(text: str) -> dict[str, list[str]]:
    dims: dict[str, list[str]] = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"维度「{part}」缺少 =")
        key, value = part.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or not value:
            raise ValueError("维度必须写成 key=value")
        dims.setdefault(key, []).append(value)
    normalized = normalize_dim_filters(dims)
    if dims and not normalized:
        raise ValueError("没有可用的维度条件")
    return normalized


def _optional_positive_number(text: str, label: str, cast: Callable[[str], Any]) -> Any | None:
    raw = text.strip()
    if not raw:
        return None
    try:
        value = cast(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是数字") from exc
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label}必须是有效数字")
    if value <= 0:
        raise ValueError(f"{label}必须大于 0")
    return value


def build_watch_payload(values: dict[str, str]) -> dict[str, Any]:
    """Validate the compact TUI form and build the shared watch payload."""

    listing_key = str(values.get("listing_key") or "").strip() or None
    known_listings = {str(item["key"]) for item in SHOP_FAMILIES}
    if listing_key and listing_key not in known_listings:
        raise ValueError(f"未知分类：{listing_key}")

    mode = str(values.get("mode") or "condition").strip()
    if mode not in {"condition", "sku"}:
        raise ValueError("方式只能是 condition 或 sku")

    name = str(values.get("name") or "").strip()
    if mode == "sku":
        sku = str(values.get("sku") or "").strip().upper()
        if not sku:
            raise ValueError("精确 SKU 规则必须填写 SKU")
        return {
            "name": name or f"SKU {sku}",
            "enabled": True,
            "mode": "sku",
            "sku": sku,
            "listing_key": listing_key,
        }

    dims = _parse_dims(str(values.get("dims") or ""))
    unknown_dims = sorted(key for key in dims if not dim_spec(key))
    if unknown_dims:
        raise ValueError(f"未知维度：{'、'.join(unknown_dims)}")
    allowed_dims = restrict_dims(dims, listing_key)
    if allowed_dims != dims:
        rejected = sorted(set(dims) - set(allowed_dims))
        suffix = "、".join(rejected) if rejected else "所填值"
        raise ValueError(f"当前分类不支持维度：{suffix}")

    payload: dict[str, Any] = {
        "name": name,
        "enabled": True,
        "mode": "condition",
        "sku": None,
        "listing_key": listing_key,
        "all_of": [],
        "none_of": [],
        "colors": [],
        "min_ram_gb": _optional_positive_number(values.get("min_ram_gb", ""), "最低内存", int),
        "min_storage_gb": _optional_positive_number(values.get("min_storage_gb", ""), "最低容量", int),
        "min_price": None,
        "max_price": _optional_positive_number(values.get("max_price", ""), "最高价", float),
        "dim_filters": allowed_dims,
    }
    if not payload["name"]:
        payload["name"] = watch_name_from_filters(payload)
    return payload


def create_tui(
    client: ApiClient | None = None,
    *,
    client_factory: Callable[[], ApiClient] | None = None,
    owns_client: bool = False,
):
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import (
        Button,
        DataTable,
        Footer,
        Header,
        Input,
        Label,
        Select,
        Static,
        Switch,
        TabbedContent,
        TabPane,
    )

    class Confirm(ModalScreen[bool]):
        def __init__(self, message: str, confirm_label: str = "确认") -> None:
            super().__init__()
            self._message = message
            self._confirm_label = confirm_label

        def compose(self) -> ComposeResult:
            yield Static(self._message)
            with Horizontal():
                yield Button(self._confirm_label, id="yes", variant="error")
                yield Button("取消", id="no")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            self.dismiss(event.button.id == "yes")

        def action_cancel(self) -> None:
            self.dismiss(False)

        BINDINGS = [Binding("escape", "cancel", "取消", show=False)]

    class HelpScreen(ModalScreen[None]):
        BINDINGS = [Binding("escape", "dismiss_help", "关闭", show=False), Binding("q", "dismiss_help", "关闭", show=False)]

        def compose(self) -> ComposeResult:
            yield Static(
                "快捷键\n"
                "全局  ? 帮助 · q 退出 · r 刷新 · s 扫描 · 1–4 切换页面\n"
                "在售  / 过滤 · f 分类 · o 排序 · w 听配置 · k 精确 SKU\n"
                "监听  n 新建 · e 暂停/启用 · d 删除\n"
                "动态  c 清除记录\n"
                "\n"
                "核心操作与网页对齐：在售、规则、扫描、监听开关、连本机或远端。\n"
                "复杂筛选、通知密钥和电脑通知仍使用网页或桌面。",
                id="help-body",
            )
            yield Button("关闭", id="close")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            self.dismiss(None)

        def action_dismiss_help(self) -> None:
            self.dismiss(None)

    class WatchForm(ModalScreen[dict | None]):
        BINDINGS = [Binding("escape", "cancel", "取消", show=False)]

        def compose(self) -> ComposeResult:
            with VerticalScroll(id="watch-form-body"):
                yield Static("新建监听规则", classes="title")
                yield Label("名称（可选）")
                yield Input(placeholder="14 英寸 M5 Pro", id="watch-name")
                yield Label("分类")
                yield Select(
                    [("不限", ""), *[(str(item["name"]), str(item["key"])) for item in SHOP_FAMILIES]],
                    value="mac",
                    allow_blank=False,
                    id="watch-listing",
                )
                yield Label("方式")
                yield Select(
                    [("按条件", "condition"), ("精确 SKU", "sku")],
                    value="condition",
                    allow_blank=False,
                    id="watch-mode",
                )
                yield Label("SKU（精确 SKU 时必填）")
                yield Input(placeholder="AAAA4CH/A", id="watch-sku")
                yield Label("维度（key=value，多个用逗号分隔）")
                yield Input(placeholder="chip=m5,tsMemorySize=24gb", id="watch-dims")
                yield Label("最低内存 GB（可选）")
                yield Input(placeholder="24", id="watch-min-ram")
                yield Label("最低容量 GB（可选）")
                yield Input(placeholder="512", id="watch-min-storage")
                yield Label("最高价（可选）")
                yield Input(placeholder="18000", id="watch-max-price")
                yield Static("", id="watch-error")
                with Horizontal():
                    yield Button("保存", id="save", variant="primary")
                    yield Button("取消", id="cancel")

        def action_cancel(self) -> None:
            self.dismiss(None)

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id != "save":
                self.dismiss(None)
                return
            listing_value = self.query_one("#watch-listing", Select).value
            mode_value = self.query_one("#watch-mode", Select).value
            values = {
                "name": self.query_one("#watch-name", Input).value,
                "listing_key": listing_value if isinstance(listing_value, str) else "",
                "mode": mode_value if isinstance(mode_value, str) else "condition",
                "sku": self.query_one("#watch-sku", Input).value,
                "dims": self.query_one("#watch-dims", Input).value,
                "min_ram_gb": self.query_one("#watch-min-ram", Input).value,
                "min_storage_gb": self.query_one("#watch-min-storage", Input).value,
                "max_price": self.query_one("#watch-max-price", Input).value,
            }
            try:
                payload = build_watch_payload(values)
            except ValueError as exc:
                self.query_one("#watch-error", Static).update(str(exc))
                return
            self.dismiss(payload)

    class RefurbApp(App[None]):
        TITLE = "官翻监听"
        CSS = """
        Screen { background: #161617; color: #f5f5f7; }
        Screen.narrow #side { display: none; }
        Header { background: #1d1d1f; }
        Footer { background: #1d1d1f; }
        TabbedContent { height: 1fr; }
        TabPane { height: 1fr; }
        DataTable { height: 1fr; }
        #side { width: 28; border-right: solid #424245; padding: 1; }
        #status { color: #a1a1a6; }
        #family-label, #sort-label { color: #a1a1a6; margin-bottom: 1; }
        #listing-switches { height: auto; margin: 1 0; }
        .setting-row { height: auto; }
        .setting-row Label { padding-left: 1; }
        #settings-note { color: #a1a1a6; margin: 1 0; }
        #watch-error { color: #ff6961; min-height: 1; }
        .title { text-style: bold; color: #0a84ff; }
        Input, Select { margin-bottom: 1; }
        Confirm, HelpScreen, WatchForm { align: center middle; }
        Confirm Horizontal, WatchForm Horizontal { width: auto; height: auto; }
        Confirm, HelpScreen {
            background: #1d1d1f;
            padding: 1 2;
            border: round #0a84ff;
            width: 90%;
            max-width: 72;
            height: auto;
        }
        WatchForm {
            background: #1d1d1f;
            padding: 1 2;
            border: round #0a84ff;
            width: 90%;
            max-width: 72;
            height: 90%;
            max-height: 42;
        }
        #watch-form-body { height: 1fr; }
        #help-body { color: #f5f5f7; }
        """
        BINDINGS = [
            Binding("q", "quit", "退出"),
            Binding("question_mark", "help", "帮助"),
            Binding("slash", "filter", "过滤"),
            Binding("f", "cycle_family", "分类"),
            Binding("o", "cycle_sort", "排序"),
            Binding("s", "scan", "扫描"),
            Binding("r", "reload", "刷新"),
            Binding("n", "new_watch", "新建"),
            Binding("w", "listen_config", "听配置"),
            Binding("k", "listen_sku", "精确 SKU"),
            Binding("e", "toggle_watch", "暂停/启用"),
            Binding("d", "delete_watch", "删除规则"),
            Binding("c", "clear_events", "清除动态"),
            Binding("1", "tab_listings", "在售", show=False),
            Binding("2", "tab_watches", "监听", show=False),
            Binding("3", "tab_events", "动态", show=False),
            Binding("4", "tab_settings", "设置", show=False),
        ]

        def __init__(
            self,
            initial_client: ApiClient | None,
            factory: Callable[[], ApiClient] | None,
            close_client: bool,
        ) -> None:
            super().__init__()
            self.client = initial_client
            self._client_factory = factory
            self._owns_client = close_client
            self._listings: list[dict] = []
            self._stock: list[dict] = []
            self._watches: list[dict] = []
            self._settings_listings: list[str] = []
            self._last_settings: dict[str, Any] = {}
            self._last_status: dict[str, Any] = {}
            self._listing_key = ""
            self._sort = "price"
            self._syncing_switch = False
            self._connecting = False
            self._scan_busy = False
            self._settings_ready = False
            self._generations: dict[str, int] = {}
            self._busy_operations: set[str] = set()
            self._status_request_running = False
            self._status_poll_failures = 0
            self._stop_event = threading.Event()
            self._pending_clients: list[Any] = []

        def compose(self) -> ComposeResult:
            yield Header()
            with TabbedContent(initial="listings"):
                with TabPane("在售", id="listings"):
                    with Horizontal():
                        with Vertical(id="side"):
                            yield Static("官翻监听", classes="title")
                            yield Button("刷新在售", id="reload")
                            yield Button("立即扫描", id="scan")
                            yield Label("分类")
                            yield Static("全部", id="family-label")
                            yield Label("排序")
                            yield Static("价格低→高", id="sort-label")
                            yield Label("关键词")
                            yield Input(placeholder="M5 Pro", id="q")
                            yield Label("状态")
                            yield Static("连接中…", id="status")
                        yield DataTable(id="table")
                with TabPane("监听", id="watches"):
                    yield DataTable(id="watch-table")
                with TabPane("动态", id="events"):
                    yield DataTable(id="event-table")
                with TabPane("设置", id="settings"):
                    with Vertical():
                        yield Static("监听开关", classes="title")
                        yield Switch(id="listen-switch")
                        yield Static("监听分类", classes="title")
                        with Vertical(id="listing-switches"):
                            for item in SHOP_FAMILIES:
                                with Horizontal(classes="setting-row"):
                                    yield Switch(id=f"listing-{item['key']}")
                                    yield Label(item["name"])
                        yield Button("测试通知", id="notify")
                        yield Button("同步筛选词条", id="sync-catalog")
                        yield Static("", id="settings-note")
            yield Footer()

        def on_mount(self) -> None:
            table = self.query_one("#table", DataTable)
            table.add_columns("SKU", "分类", "价格", "内存", "硬盘", "标题")
            table.cursor_type = "row"
            watches = self.query_one("#watch-table", DataTable)
            watches.add_columns("ID", "状态", "方式", "在售", "条件", "名称")
            watches.cursor_type = "row"
            events = self.query_one("#event-table", DataTable)
            events.add_columns("日期", "时间", "类型", "内容")
            self.set_focus(table)
            self.screen.set_class(self.size.width < 100, "narrow")
            self._set_settings_controls_enabled(False)
            self.set_interval(4.0, self._poll_status)
            if self.client is None:
                self._connect()
            else:
                self.reload_all()

        def on_resize(self, event) -> None:
            for screen in self.screen_stack:
                screen.set_class(event.size.width < 100, "narrow")

        def on_unmount(self) -> None:
            self._stop_event.set()
            pending = list(self._pending_clients)
            self._pending_clients.clear()
            for pending_client in pending:
                if pending_client is self.client:
                    continue
                try:
                    pending_client.close()
                except Exception:  # noqa: BLE001
                    pass
            if self._owns_client and self.client is not None and hasattr(self.client, "close"):
                try:
                    self.client.close()
                except Exception:  # noqa: BLE001
                    pass

        def _run_task(
            self,
            group: str,
            work: Callable[[], Any],
            done: Callable[[Any, Exception | None], None],
            *,
            exclusive: bool = True,
        ) -> None:
            def runner() -> None:
                result: Any = None
                error: Exception | None = None
                try:
                    result = work()
                except Exception as exc:  # noqa: BLE001
                    error = exc
                if group == "connect" and result is not None and hasattr(result, "close"):
                    self._pending_clients.append(result)
                if self._stop_event.is_set():
                    if group == "connect" and result is not None and hasattr(result, "close"):
                        try:
                            self._pending_clients.remove(result)
                        except ValueError:
                            pass
                        try:
                            result.close()
                        except Exception:  # noqa: BLE001
                            pass
                    return
                try:
                    self.call_from_thread(lambda: done(result, error))
                except RuntimeError:
                    if group == "connect" and result is not None and hasattr(result, "close"):
                        try:
                            self._pending_clients.remove(result)
                        except ValueError:
                            pass
                        try:
                            result.close()
                        except Exception:  # noqa: BLE001
                            pass
                    return

            self.run_worker(
                runner,
                name=group,
                group=group,
                exclusive=exclusive,
                thread=True,
                exit_on_error=False,
            )

        def _client_or_warn(self) -> ApiClient | None:
            if self.client is not None:
                return self.client
            self.notify("服务尚未连接")
            if not self._connecting:
                self._connect()
            return None

        def _run_unique_client_task(
            self,
            group: str,
            work: Callable[[ApiClient], Any],
            done: Callable[[Any, Exception | None], None],
        ) -> bool:
            if group in self._busy_operations:
                self.notify("操作正在进行")
                return False
            current = self._client_or_warn()
            if current is None:
                return False
            self._busy_operations.add(group)

            def finish(result: Any, error: Exception | None) -> None:
                self._busy_operations.discard(group)
                done(result, error)

            self._run_task(group, lambda: work(current), finish, exclusive=False)
            return True

        def _connect(self) -> None:
            if self.client is not None:
                self.reload_all()
                return
            if self._connecting:
                return
            if self._client_factory is None:
                self.query_one("#status", Static).update("没有可用的服务连接")
                self.sub_title = "未连接"
                return
            self._connecting = True
            self.query_one("#status", Static).update("正在连接服务…")
            self.sub_title = "正在连接"

            def finish(result: Any, error: Exception | None) -> None:
                self._connecting = False
                if result is not None and hasattr(result, "close"):
                    try:
                        self._pending_clients.remove(result)
                    except ValueError:
                        pass
                if error is not None:
                    if result is not None and hasattr(result, "close"):
                        try:
                            result.close()
                        except Exception:  # noqa: BLE001
                            pass
                    self.query_one("#status", Static).update(f"连接失败 · {error}")
                    self.sub_title = "连接失败"
                    self.notify(str(error))
                    return
                self.client = result
                self.query_one("#status", Static).update("已连接，正在读取数据…")
                self.sub_title = "已连接"
                self.reload_all()

            self._run_task("connect", self._client_factory, finish)

        def on_button_pressed(self, event: Button.Pressed) -> None:
            button_id = event.button.id or ""
            if button_id == "reload":
                self.reload_listings()
            elif button_id == "scan":
                self.action_scan()
            elif button_id == "notify":
                event.button.disabled = True

                def finish(result: Any, error: Exception | None) -> None:
                    event.button.disabled = False
                    if error is not None:
                        self.notify(str(error))
                        return
                    self.notify("测试通知已发出" if (result or {}).get("ok") else str(result))

                if not self._run_unique_client_task("notify-test", lambda current: current.notify_test(), finish):
                    event.button.disabled = False
            elif button_id == "sync-catalog":
                event.button.disabled = True

                def finish(result: Any, error: Exception | None) -> None:
                    event.button.disabled = False
                    if error is not None:
                        self.notify(str(error))
                        return
                    self.notify("已同步筛选词条" if (result or {}).get("ok") else str(result))

                if not self._run_unique_client_task(
                    "sync-catalog",
                    lambda current: current.sync_catalog() or {},
                    finish,
                ):
                    event.button.disabled = False

        def on_switch_changed(self, event: Switch.Changed) -> None:
            switch_id = event.switch.id or ""
            if self._syncing_switch:
                return
            if not self._settings_ready:
                if switch_id == "listen-switch":
                    self._set_listen_switch(bool(self._last_settings.get("listen_enabled", False)))
                elif switch_id.startswith("listing-"):
                    self._apply_listing_switches(
                        list(self._last_settings.get("listings") or self._settings_listings)
                    )
                self.notify("设置尚未加载完成")
                return
            if switch_id == "listen-switch":
                generation = self._next_generation("settings")
                previous = bool(self._last_settings.get("listen_enabled", not event.value))
                event.switch.disabled = True

                def finish(result: Any, error: Exception | None) -> None:
                    if not self._generation_is_current("settings", generation):
                        event.switch.disabled = False
                        return
                    event.switch.disabled = False
                    if error is not None:
                        self._set_listen_switch(previous)
                        self.notify(str(error))
                        return
                    updated = dict(self._last_settings)
                    updated.update(result or {"listen_enabled": event.value})
                    self._apply_settings(updated)
                    self.notify("已开始监听" if event.value else "已停止监听")

                if not self._run_unique_client_task(
                    "settings-write",
                    lambda current: current.update_settings({"listen_enabled": event.value}),
                    finish,
                ):
                    event.switch.disabled = False
                    self._set_listen_switch(previous)
                return
            if switch_id.startswith("listing-"):
                self._save_listings()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "q":
                self.reload_listings()

        def action_help(self) -> None:
            self.push_screen(HelpScreen())

        def _show_tab(self, tab: str, focus: str | None = None) -> None:
            self.query_one(TabbedContent).active = tab
            if focus:
                self.set_focus(self.query_one(focus))

        def action_tab_listings(self) -> None:
            self._show_tab("listings", "#table")

        def action_tab_watches(self) -> None:
            self._show_tab("watches", "#watch-table")

        def action_tab_events(self) -> None:
            self._show_tab("events", "#event-table")

        def action_tab_settings(self) -> None:
            self._show_tab("settings", "#listen-switch")

        def action_filter(self) -> None:
            self._show_tab("listings", "#q")

        def action_cycle_family(self) -> None:
            self._show_tab("listings", "#table")
            choices = self._family_choices()
            keys = [key for key, _ in choices]
            if not keys:
                return
            try:
                index = keys.index(self._listing_key)
            except ValueError:
                index = -1
            self._listing_key = keys[(index + 1) % len(keys)]
            self._update_family_label()
            self.reload_listings()

        def action_cycle_sort(self) -> None:
            self._show_tab("listings", "#table")
            self._sort = "-price" if self._sort != "-price" else "price"
            self._update_sort_label()
            self.reload_listings()

        def action_reload(self) -> None:
            if self.client is None:
                self._connect()
                return
            active = self.query_one(TabbedContent).active
            if active == "listings":
                self.reload_listings()
            elif active == "watches":
                self.reload_watches()
            elif active == "events":
                self.reload_events()
            else:
                self.reload_settings()

        def action_scan(self) -> None:
            if self._scan_busy:
                self.notify("扫描已在进行")
                return
            current = self._client_or_warn()
            if current is None:
                return
            self._scan_busy = True
            self.query_one("#scan", Button).disabled = True
            self.query_one("#status", Static).update("正在提交扫描…")
            self.sub_title = "正在提交扫描"
            self._run_task("scan", lambda: self._perform_scan(current), self._finish_scan)

        def _post_scan_progress(self, run: dict[str, Any]) -> None:
            if self._stop_event.is_set():
                return
            snapshot = dict(run)
            try:
                self.call_from_thread(lambda: self._apply_scan_progress(snapshot))
            except RuntimeError:
                return

        def _perform_scan(self, current: ApiClient) -> dict[str, Any]:
            if not hasattr(current, "submit_scan") or not hasattr(current, "scan_run"):
                return self._legacy_scan_result(current.scan())
            try:
                submitted = current.submit_scan()
            except ApiError as exc:
                if exc.status not in {404, 405}:
                    raise
                return self._legacy_scan_result(current.scan())
            if not isinstance(submitted, dict):
                raise RuntimeError("服务返回了无效扫描任务")
            if not submitted.get("accepted", True):
                raise RuntimeError(str(submitted.get("message") or "已有扫描在进行"))
            raw_run_id = submitted.get("scan_run_id") or submitted.get("id")
            if raw_run_id in (None, ""):
                return self._legacy_scan_result(submitted)
            run_id = int(raw_run_id)
            self._post_scan_progress({"id": run_id, "status": submitted.get("status") or "queued"})
            deadline = time.monotonic() + 900
            while not self._stop_event.is_set():
                run = current.scan_run(run_id)
                if not isinstance(run, dict):
                    raise RuntimeError("服务返回了无效扫描状态")
                self._post_scan_progress(run)
                if str(run.get("status") or "") in {"succeeded", "partial", "failed"}:
                    return {"legacy": False, "run": run}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(f"等待扫描 #{run_id} 完成超时")
                if self._stop_event.wait(min(1.0, remaining)):
                    return {"cancelled": True, "run": run}
            return {"cancelled": True}

        def _legacy_scan_result(self, run: Any) -> dict[str, Any]:
            if not isinstance(run, dict):
                raise RuntimeError("服务返回了无效扫描结果")
            if run.get("ok") is False:
                raise RuntimeError(str(run.get("message") or "扫描失败"))
            return {"legacy": True, "run": run}

        def _apply_scan_progress(self, run: dict[str, Any]) -> None:
            status = str(run.get("status") or "running")
            run_id = run.get("id") or run.get("scan_run_id")
            labels = {"queued": "等待扫描", "running": "正在扫描"}
            label = labels.get(status, status)
            suffix = f" #{run_id}" if run_id else ""
            self.query_one("#status", Static).update(f"{label}{suffix}…")
            self.sub_title = f"{label}{suffix}"

        def _finish_scan(self, result: Any, error: Exception | None) -> None:
            self._scan_busy = False
            self.query_one("#scan", Button).disabled = False
            if error is not None:
                self.query_one("#status", Static).update(f"扫描失败 · {error}")
                self.sub_title = "扫描失败"
                self.notify(str(error))
                return
            payload = result or {}
            if payload.get("cancelled"):
                return
            run = payload.get("run") or {}
            if payload.get("legacy") and run.get("ok") is False:
                message = str(run.get("message") or "扫描失败")
                self.query_one("#status", Static).update(f"扫描失败 · {message}")
                self.sub_title = "扫描失败"
                self.notify(message)
                return
            status = str(run.get("status") or run.get("scan_status") or "")
            if status == "failed":
                message = str(run.get("error_summary") or run.get("message") or "扫描失败")
                self.query_one("#status", Static).update(f"扫描失败 · {message}")
                self.sub_title = "扫描失败"
                self.notify(message)
            elif status == "partial":
                self.query_one("#status", Static).update("扫描部分完成")
                self.sub_title = "扫描部分完成"
                self.notify("扫描完成，但有部分分类失败")
            else:
                self.query_one("#status", Static).update("扫描完成，正在刷新…")
                self.sub_title = "扫描完成"
                self.notify(str(run.get("message") or "扫描完成"))
            self.reload_all()

        def _selected_listing(self) -> dict | None:
            table = self.query_one("#table", DataTable)
            if not table.is_valid_coordinate(table.cursor_coordinate):
                return None
            row = table.cursor_row
            if row < 0 or row >= len(self._listings):
                return None
            return self._listings[row]

        def _selected_watch(self) -> dict | None:
            table = self.query_one("#watch-table", DataTable)
            if not table.is_valid_coordinate(table.cursor_coordinate):
                return None
            row = table.cursor_row
            if row < 0 or row >= len(self._watches):
                return None
            return self._watches[row]

        def action_listen_config(self) -> None:
            self._create_from_row("condition")

        def action_listen_sku(self) -> None:
            self._create_from_row("sku")

        def _create_from_row(self, mode: str) -> None:
            item = self._selected_listing()
            if not item:
                self.notify("先在在售表里选一行")
                return
            payload = watch_from_product(item, mode)

            def finish(result: Any, error: Exception | None) -> None:
                if error is not None:
                    self.notify(str(error))
                    return
                self.notify(f"已保存 {(result or {}).get('name')}")
                self.reload_watches()

            self._run_unique_client_task("watch-create", lambda current: current.create_watch(payload), finish)

        def action_new_watch(self) -> None:
            def form_finished(payload: dict | None) -> None:
                if not payload:
                    return

                def finish(result: Any, error: Exception | None) -> None:
                    if error is not None:
                        self.notify(str(error))
                        return
                    self.notify(f"已保存 {(result or {}).get('name')}")
                    self.reload_watches()

                self._run_unique_client_task("watch-create", lambda current: current.create_watch(payload), finish)

            self.push_screen(WatchForm(), form_finished)

        def action_toggle_watch(self) -> None:
            watch = self._selected_watch()
            if not watch:
                self.notify("先在监听表里选一行")
                return
            enabled = not bool(watch.get("enabled"))
            watch_id = int(watch["id"])

            def finish(_result: Any, error: Exception | None) -> None:
                if error is not None:
                    self.notify(str(error))
                    return
                self.notify("已启用" if enabled else "已暂停")
                self.reload_watches()

            self._run_unique_client_task(
                "watch-toggle",
                lambda current: current.update_watch(watch_id, {"enabled": enabled}),
                finish,
            )

        def action_delete_watch(self) -> None:
            watch = self._selected_watch()
            if not watch:
                self.notify("先在监听表里选一行")
                return
            watch_id = int(watch["id"])

            def confirmed(ok: bool | None) -> None:
                if not ok:
                    return

                def finish(_result: Any, error: Exception | None) -> None:
                    if error is not None:
                        self.notify(str(error))
                        return
                    self.notify("已删除")
                    self.reload_watches()

                self._run_unique_client_task(
                    "watch-delete",
                    lambda current: current.delete_watch(watch_id),
                    finish,
                )

            self.push_screen(
                Confirm(f"删除规则「{watch.get('name') or watch['id']}」？", "确认删除"),
                confirmed,
            )

        def action_clear_events(self) -> None:
            def confirmed(ok: bool | None) -> None:
                if not ok:
                    return

                def finish(result: Any, error: Exception | None) -> None:
                    if error is not None:
                        self.notify(str(error))
                        return
                    self.notify(f"已清除 {(result or {}).get('deleted', 0)} 条记录")
                    self.reload_events()

                self._run_unique_client_task(
                    "events-clear",
                    lambda current: current.clear_events() or {},
                    finish,
                )

            self.push_screen(Confirm("清除全部动态记录？不影响在售和规则。", "确认清除"), confirmed)

        def _next_generation(self, area: str) -> int:
            generation = self._generations.get(area, 0) + 1
            self._generations[area] = generation
            return generation

        def _generation_is_current(self, area: str, generation: int) -> bool:
            return self._generations.get(area) == generation

        def _current_filters(self) -> tuple[str | None, str | None, str]:
            q = self.query_one("#q", Input).value.strip() or None
            return q, self._listing_key or None, self._sort

        def reload_all(self) -> None:
            current = self._client_or_warn()
            if current is None:
                return
            generations = {
                area: self._next_generation(area)
                for area in ("settings", "listings", "watches", "events")
            }
            q, listing_key, sort = self._current_filters()
            if not self._scan_busy:
                self.query_one("#status", Static).update("正在刷新…")

            def work() -> dict[str, Any]:
                settings = current.settings()
                families = shop_families_for(settings.get("listings") or [])
                valid_listing_keys = [str(item["key"]) for item in families]
                effective_listing_key = listing_key
                if len(valid_listing_keys) == 1:
                    effective_listing_key = valid_listing_keys[0]
                elif len(valid_listing_keys) > 1 and listing_key not in valid_listing_keys:
                    effective_listing_key = None
                elif not valid_listing_keys:
                    effective_listing_key = None
                listings = current.listings(
                    q=q,
                    listing_key=effective_listing_key,
                    sort=sort,
                    all_pages=True,
                )
                status = current.status()
                watches = list(current.watches() or [])
                stock = (
                    listings
                    if not q and not effective_listing_key
                    else current.listings(all_pages=True)
                )
                events = current.events(limit=80)
                return {
                    "settings": settings,
                    "listings": listings,
                    "status": status,
                    "watches": watches,
                    "stock": (stock or {}).get("items") or [],
                    "events": events,
                    "listing_key": effective_listing_key or "",
                }

            def finish(result: Any, error: Exception | None) -> None:
                if error is not None:
                    if self._generation_is_current("listings", generations["listings"]):
                        self.query_one("#status", Static).update(f"刷新失败 · {error}")
                        self.notify(str(error))
                    return
                snapshot = result or {}
                if self._generation_is_current("settings", generations["settings"]):
                    self._apply_settings(snapshot.get("settings") or {})
                if self._generation_is_current("listings", generations["listings"]):
                    self._listing_key = str(snapshot.get("listing_key") or "")
                    self._update_family_label()
                    self._apply_listings(snapshot.get("listings") or {})
                    self._apply_status(snapshot.get("status") or {})
                if self._generation_is_current("watches", generations["watches"]):
                    self._apply_watches(snapshot.get("watches") or [], snapshot.get("stock") or [])
                if self._generation_is_current("events", generations["events"]):
                    self._apply_events(snapshot.get("events") or [])

            self._run_task("refresh-all", work, finish)

        def reload_listings(self) -> None:
            current = self._client_or_warn()
            if current is None:
                return
            if not self._last_settings:
                self.reload_all()
                return
            generation = self._next_generation("listings")
            q, listing_key, sort = self._current_filters()
            if not self._scan_busy:
                self.query_one("#status", Static).update("正在刷新在售…")

            def work() -> dict[str, Any]:
                return {
                    "listings": current.listings(
                        q=q,
                        listing_key=listing_key,
                        sort=sort,
                        all_pages=True,
                    ),
                    "status": current.status(),
                }

            def finish(result: Any, error: Exception | None) -> None:
                if not self._generation_is_current("listings", generation):
                    return
                if error is not None:
                    self.query_one("#status", Static).update(f"刷新失败 · {error}")
                    self.notify(str(error))
                    return
                self._apply_listings((result or {}).get("listings") or {})
                self._apply_status((result or {}).get("status") or {})

            self._run_task("refresh-listings", work, finish)

        def reload_watches(self) -> None:
            current = self._client_or_warn()
            if current is None:
                return
            generation = self._next_generation("watches")

            def work() -> dict[str, Any]:
                return {
                    "watches": list(current.watches() or []),
                    "stock": (current.listings(all_pages=True) or {}).get("items") or [],
                }

            def finish(result: Any, error: Exception | None) -> None:
                if not self._generation_is_current("watches", generation):
                    return
                if error is not None:
                    self.notify(str(error))
                    return
                self._apply_watches((result or {}).get("watches") or [], (result or {}).get("stock") or [])

            self._run_task("refresh-watches", work, finish)

        def reload_events(self) -> None:
            current = self._client_or_warn()
            if current is None:
                return
            generation = self._next_generation("events")

            def finish(result: Any, error: Exception | None) -> None:
                if not self._generation_is_current("events", generation):
                    return
                if error is not None:
                    self.notify(str(error))
                    return
                self._apply_events(result or [])

            self._run_task("refresh-events", lambda: current.events(limit=80), finish)

        def reload_settings(self) -> None:
            current = self._client_or_warn()
            if current is None:
                return
            generation = self._next_generation("settings")

            def finish(result: Any, error: Exception | None) -> None:
                if not self._generation_is_current("settings", generation):
                    return
                if error is not None:
                    self.query_one("#settings-note", Static).update(str(error))
                    return
                self._apply_settings(result or {})

            self._run_task("refresh-settings", current.settings, finish)

        def _poll_status(self) -> None:
            if self.client is None or self._status_request_running:
                return
            current = self.client
            self._status_request_running = True

            def finish(result: Any, error: Exception | None) -> None:
                self._status_request_running = False
                if error is not None:
                    self._status_poll_failures += 1
                    if not self._last_status or self._status_poll_failures >= 2:
                        self.query_one("#status", Static).update(f"连接失败 · {error}")
                        self.sub_title = "连接失败"
                    return
                previous = dict(self._last_status)
                previous_scanning = bool(previous.get("scanning"))
                previous_success = str(previous.get("last_success_at") or "")
                previous_error = str(previous.get("last_error") or "")
                self._status_poll_failures = 0
                self._apply_status(result or {})
                if self._scan_busy:
                    return
                current_scanning = bool((result or {}).get("scanning"))
                current_success = str((result or {}).get("last_success_at") or "")
                current_error = str((result or {}).get("last_error") or "")
                finished_scan = previous_scanning and not current_scanning
                success_changed = bool(previous) and current_success and current_success != previous_success
                error_changed = bool(previous) and current_error != previous_error
                if finished_scan or success_changed or error_changed:
                    self.reload_all()

            self._run_task("status-poll", current.status, finish)

        def _apply_status(self, status: dict[str, Any]) -> None:
            self._last_status = dict(status)
            if self._scan_busy:
                return
            view = status.get("view") or {}
            label = str(view.get("label") or "状态")
            detail = str(view.get("detail") or "").strip()
            if not detail:
                detail = (
                    f"规则 {status.get('watch_count', 0)}/{status.get('watch_total', 0)}"
                    f" · 在售 {status.get('in_stock', 0)}"
                )
            self.sub_title = label
            self.query_one("#status", Static).update(f"{label} · {detail}")

        def _apply_listings(self, payload: dict[str, Any]) -> None:
            items = list(payload.get("items") or [])
            table = self.query_one("#table", DataTable)
            table.clear()
            self._listings = items
            for item in items:
                price = f"¥{format_cny(item.get('price'))}" if item.get("price") is not None else "-"
                table.add_row(
                    item.get("sku") or "",
                    listing_family_name(item.get("listing_key")) or "-",
                    price,
                    format_gb(item.get("ram_gb")) or "-",
                    format_gb(item.get("storage_gb")) or "-",
                    (item.get("title") or "")[:48],
                )

        def _apply_watches(self, watches: list[dict], stock: list[dict]) -> None:
            from apple_refurb_watch.match import matches_watch

            table = self.query_one("#watch-table", DataTable)
            table.clear()
            self._watches = list(watches)
            self._stock = list(stock)
            for watch in self._watches:
                matched = sum(1 for item in self._stock if matches_watch(item, watch)) if self._stock else 0
                cond = watch_condition_label(watch)
                table.add_row(
                    str(watch.get("id") or ""),
                    "启用" if watch.get("enabled") else "暂停",
                    "精确 SKU" if watch.get("mode") == "sku" else "条件",
                    str(matched),
                    (cond or "—")[:40],
                    str(watch.get("name") or ""),
                )

        def _apply_events(self, events: list[dict]) -> None:
            table = self.query_one("#event-table", DataTable)
            table.clear()
            if not events:
                table.add_row("—", "—", "—", "还没有记录。首次扫描只建基线。")
                return
            watch_names = {
                int(item["id"]): str(item.get("name") or "")
                for item in self._watches
                if item.get("id")
            }
            for day in present_event_days(events, collapse_scans=True, watch_names=watch_names):
                for item in day["entries"]:
                    when = str(item.get("when_local") or format_localtime(item.get("created_at")))
                    clock = when[11:] if len(when) >= 16 else when
                    kind = str(item.get("type") or "")
                    table.add_row(
                        str(day["day"]),
                        clock,
                        str(item.get("label") or EVENT_LABELS.get(kind, kind)),
                        str(item.get("title") or item.get("message") or "")[:64],
                    )

        def _family_choices(self) -> list[tuple[str, str]]:
            families = shop_families_for(self._settings_listings)
            if len(families) > 1:
                return [("", "全部"), *[(item["key"], item["name"]) for item in families]]
            if len(families) == 1:
                return [(families[0]["key"], families[0]["name"])]
            return [("", "全部")]

        def _update_family_label(self) -> None:
            label = "全部"
            for key, name in self._family_choices():
                if key == self._listing_key:
                    label = name
                    break
            self.query_one("#family-label", Static).update(label)

        def _update_sort_label(self) -> None:
            text = "价格高→低" if self._sort == "-price" else "价格低→高"
            self.query_one("#sort-label", Static).update(text)

        def _sync_family_from_settings(self) -> None:
            keys = [key for key, _ in self._family_choices()]
            if self._listing_key not in keys:
                self._listing_key = keys[0] if keys else ""
            self._update_family_label()

        def _set_listen_switch(self, value: bool) -> None:
            switch = self.query_one("#listen-switch", Switch)
            with switch.prevent(Switch.Changed):
                switch.value = value

        def _set_listing_switches_disabled(self, disabled: bool) -> None:
            for item in SHOP_FAMILIES:
                self.query_one(f"#listing-{item['key']}", Switch).disabled = disabled

        def _set_settings_controls_enabled(self, enabled: bool) -> None:
            self.query_one("#listen-switch", Switch).disabled = not enabled
            self._set_listing_switches_disabled(not enabled)
            self.query_one("#notify", Button).disabled = not enabled
            self.query_one("#sync-catalog", Button).disabled = not enabled

        def _save_listings(self) -> None:
            if not self._settings_ready:
                self._apply_listing_switches(
                    list(self._last_settings.get("listings") or self._settings_listings)
                )
                self.notify("设置尚未加载完成")
                return
            generation = self._next_generation("settings")
            previous = list(self._last_settings.get("listings") or self._settings_listings)
            keys = [
                str(item["key"])
                for item in SHOP_FAMILIES
                if self.query_one(f"#listing-{item['key']}", Switch).value
            ]
            self._set_listing_switches_disabled(True)

            def finish(result: Any, error: Exception | None) -> None:
                if not self._generation_is_current("settings", generation):
                    self._set_listing_switches_disabled(False)
                    return
                self._set_listing_switches_disabled(False)
                if error is not None:
                    self._apply_listing_switches(previous)
                    self.notify(str(error))
                    return
                updated = dict(self._last_settings)
                updated.update(result or {"listings": keys})
                self._apply_settings(updated)
                self.notify("已更新监听分类")
                self.reload_listings()
                self.reload_watches()

            if not self._run_unique_client_task(
                "settings-write",
                lambda current: current.update_settings({"listings": keys}),
                finish,
            ):
                self._set_listing_switches_disabled(False)
                self._apply_listing_switches(previous)

        def _apply_listing_switches(self, listings: list[str]) -> None:
            current = {shop_family_key(key) for key in listings}
            current.discard("")
            self._settings_listings = list(listings)
            self._syncing_switch = True
            try:
                for item in SHOP_FAMILIES:
                    switch = self.query_one(f"#listing-{item['key']}", Switch)
                    with switch.prevent(Switch.Changed):
                        switch.value = item["key"] in current
            finally:
                self._syncing_switch = False
            self._sync_family_from_settings()

        def _apply_settings(self, settings: dict[str, Any]) -> None:
            self._last_settings = dict(settings)
            self._settings_ready = True
            self._set_listen_switch(bool(settings.get("listen_enabled")))
            self._apply_listing_switches(settings.get("listings") or [])
            self._set_settings_controls_enabled(True)
            self._update_sort_label()
            self.query_one("#settings-note", Static).update(
                f"间隔 {settings.get('interval_seconds')} 秒"
                f" · {settings.get('bind_host')}:{settings.get('bind_port')}"
                " · 密钥请用网页设置"
            )

    return RefurbApp(client, client_factory, owns_client)


def run_tui() -> None:
    def connect_client() -> ApiClient:
        conn = load_connection()
        current = resolve_client(start_local=not bool(conn.url))
        try:
            if conn.url:
                err = check_client_compat(current.health())
                if err:
                    raise RuntimeError(err)
            return current
        except Exception:
            current.close()
            raise

    create_tui(client_factory=connect_client, owns_client=True).run()
