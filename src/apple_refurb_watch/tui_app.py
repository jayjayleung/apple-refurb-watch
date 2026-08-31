from __future__ import annotations

from apple_refurb_watch.categories import SHOP_FAMILIES, listing_family_name, shop_families_for, shop_family_key
from apple_refurb_watch.client import ApiClient
from apple_refurb_watch.daemon import ensure_daemon
from apple_refurb_watch.listing import format_cny, format_gb
from apple_refurb_watch.status_view import EVENT_LABELS, format_localtime, present_event_days
from apple_refurb_watch.watches import watch_condition_label, watch_from_product


def _parse_dims(text: str) -> dict[str, list[str]]:
    dims: dict[str, list[str]] = {}
    for part in text.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or not value:
            continue
        dims.setdefault(key, []).append(value)
    return dims


def create_tui(client: ApiClient):
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static, Switch, TabbedContent, TabPane

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
                "/ 过滤在售关键词\n"
                "f 切换分类\n"
                "o 切换价格排序\n"
                "n 新建规则（表单）\n"
                "w 听配置\n"
                "k 精确 SKU\n"
                "e 暂停 / 启用\n"
                "d 删除规则\n"
                "c 清除动态记录\n"
                "r 刷新\n"
                "s 扫描\n"
                "q 退出",
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
            yield Static("新建监听规则", classes="title")
            yield Label("名称")
            yield Input(placeholder="14 M5 Pro", id="watch-name")
            yield Label("分类 key（mac / ipad / watch / airpods / homepod / accessories，留空不限）")
            yield Input(value="mac", id="watch-listing")
            yield Label("方式：condition 或 sku")
            yield Input(value="condition", id="watch-mode")
            yield Label("SKU（精确货号时填写）")
            yield Input(placeholder="AAAA4CH/A", id="watch-sku")
            yield Label("维度 key=value，逗号分隔")
            yield Input(placeholder="chip=m5,tsMemorySize=24gb", id="watch-dims")
            yield Label("最高价（可选）")
            yield Input(placeholder="18000", id="watch-max-price")
            with Horizontal():
                yield Button("保存", id="save", variant="primary")
                yield Button("取消", id="cancel")

        def action_cancel(self) -> None:
            self.dismiss(None)

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id != "save":
                self.dismiss(None)
                return
            name = self.query_one("#watch-name", Input).value.strip()
            listing_key = self.query_one("#watch-listing", Input).value.strip() or None
            mode = self.query_one("#watch-mode", Input).value.strip() or "condition"
            sku = self.query_one("#watch-sku", Input).value.strip()
            payload: dict = {
                "name": name or (f"SKU {sku}" if sku else "未命名规则"),
                "mode": "sku" if mode == "sku" else "condition",
                "listing_key": listing_key,
            }
            if payload["mode"] == "sku":
                payload["sku"] = sku
            else:
                dims = _parse_dims(self.query_one("#watch-dims", Input).value)
                if dims:
                    payload["dim_filters"] = dims
                raw_price = self.query_one("#watch-max-price", Input).value.strip()
                if raw_price:
                    try:
                        payload["max_price"] = float(raw_price)
                    except ValueError:
                        pass
            self.dismiss(payload)

    class RefurbApp(App[None]):
        TITLE = "官翻监听"
        CSS = """
        Screen { background: #161617; color: #f5f5f7; }
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
        .title { text-style: bold; color: #0a84ff; }
        Input { margin-bottom: 1; }
        Confirm, HelpScreen, WatchForm { align: center middle; }
        Confirm Horizontal, WatchForm Horizontal { width: auto; height: auto; }
        Confirm, HelpScreen, WatchForm {
            background: #1d1d1f;
            padding: 1 2;
            border: round #0a84ff;
            width: 64;
            height: auto;
        }
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
        ]

        def __init__(self, client: ApiClient) -> None:
            super().__init__()
            self.client = client
            self._listings: list[dict] = []
            self._watches: list[dict] = []
            self._settings_listings: list[str] = []
            self._listing_key = ""
            self._sort = "price"
            self._syncing_switch = False

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
            self.reload_all()
            self.set_focus(table)

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "reload":
                self.reload_all()
            elif event.button.id == "scan":
                self.action_scan()
            elif event.button.id == "notify":
                try:
                    result = self.client.notify_test()
                    self.notify("测试通知已发出" if result.get("ok") else str(result))
                except Exception as exc:  # noqa: BLE001
                    self.notify(str(exc))
            elif event.button.id == "sync-catalog":
                try:
                    result = self.client.sync_catalog() or {}
                    self.notify("已同步筛选词条" if result.get("ok") else str(result))
                except Exception as exc:  # noqa: BLE001
                    self.notify(str(exc))

        def on_switch_changed(self, event: Switch.Changed) -> None:
            switch_id = event.switch.id or ""
            if self._syncing_switch:
                return
            if switch_id == "listen-switch":
                try:
                    self.client.update_settings({"listen_enabled": event.value})
                    self.notify("已开始监听" if event.value else "已停止监听")
                except Exception as exc:  # noqa: BLE001
                    self.notify(str(exc))
                return
            if switch_id.startswith("listing-"):
                self._save_listings()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "q":
                self.reload_listings()

        def action_help(self) -> None:
            self.push_screen(HelpScreen())

        def action_filter(self) -> None:
            self.query_one(TabbedContent).active = "listings"
            self.set_focus(self.query_one("#q", Input))

        def action_cycle_family(self) -> None:
            self.query_one(TabbedContent).active = "listings"
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
            self.query_one(TabbedContent).active = "listings"
            self._sort = "-price" if self._sort != "-price" else "price"
            self._update_sort_label()
            self.reload_listings()

        def action_reload(self) -> None:
            if self.query_one(TabbedContent).active == "events":
                self.reload_events()
                return
            self.reload_all()

        def action_scan(self) -> None:
            self.run_worker(self._scan_worker, exclusive=True, thread=True)

        def _scan_worker(self) -> None:
            result = None
            try:
                result = self.client.scan()
                message = result.get("message") or f"在售 {result.get('count')}"
            except Exception as exc:  # noqa: BLE001
                message = str(exc)

            def apply() -> None:
                self.query_one("#status", Static).update(message)
                if result is not None:
                    self.reload_all()

            self.call_from_thread(apply)

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
            try:
                created = self.client.create_watch(watch_from_product(item, mode))
                self.notify(f"已保存 {created.get('name')}")
                self.reload_watches()
            except Exception as exc:  # noqa: BLE001
                self.notify(str(exc))

        def action_new_watch(self) -> None:
            def finish(payload: dict | None) -> None:
                if not payload:
                    return
                try:
                    created = self.client.create_watch(payload)
                    self.notify(f"已保存 {created.get('name')}")
                    self.reload_watches()
                except Exception as exc:  # noqa: BLE001
                    self.notify(str(exc))

            self.push_screen(WatchForm(), finish)

        def action_toggle_watch(self) -> None:
            watch = self._selected_watch()
            if not watch:
                self.notify("先在监听表里选一行")
                return
            try:
                enabled = not bool(watch.get("enabled"))
                self.client.update_watch(int(watch["id"]), {"enabled": enabled})
                self.notify("已启用" if enabled else "已暂停")
                self.reload_watches()
            except Exception as exc:  # noqa: BLE001
                self.notify(str(exc))

        def action_delete_watch(self) -> None:
            watch = self._selected_watch()
            if not watch:
                self.notify("先在监听表里选一行")
                return

            def finish(ok: bool | None) -> None:
                if not ok:
                    return
                try:
                    self.client.delete_watch(int(watch["id"]))
                    self.notify("已删除")
                    self.reload_watches()
                except Exception as exc:  # noqa: BLE001
                    self.notify(str(exc))

            self.push_screen(
                Confirm(f"删除规则「{watch.get('name') or watch['id']}」？", "确认删除"),
                finish,
            )

        def action_clear_events(self) -> None:
            def finish(ok: bool | None) -> None:
                if not ok:
                    return
                try:
                    result = self.client.clear_events() or {}
                    self.notify(f"已清除 {result.get('deleted', 0)} 条记录")
                    self.reload_events()
                except Exception as exc:  # noqa: BLE001
                    self.notify(str(exc))

            self.push_screen(Confirm("清除全部动态记录？不影响在售和规则。", "确认清除"), finish)

        def reload_all(self) -> None:
            self.reload_settings()
            self.reload_listings()
            self.reload_watches()
            self.reload_events()

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

        def _save_listings(self) -> None:
            keys = [
                item["key"]
                for item in SHOP_FAMILIES
                if self.query_one(f"#listing-{item['key']}", Switch).value
            ]
            try:
                updated = self.client.update_settings({"listings": keys})
                self._apply_listing_switches(updated.get("listings") or [])
                self.notify("已更新监听分类")
                self.reload_listings()
                self.reload_watches()
            except Exception as exc:  # noqa: BLE001
                self.notify(str(exc))

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

        def reload_listings(self) -> None:
            table = self.query_one("#table", DataTable)
            table.clear()
            q = self.query_one("#q", Input).value.strip() or None
            try:
                payload = self.client.listings(q=q, listing_key=self._listing_key or None, sort=self._sort)
                self._listings = payload.get("items") or []
                status = self.client.status()
                view = status.get("view") or {}
                label = view.get("label") or "状态"
                self.sub_title = str(label)
                self.query_one("#status", Static).update(
                    f"{label} · 规则 {status.get('watch_count')}/{status.get('watch_total')} · 在售 {status.get('in_stock')}"
                )
            except Exception as exc:  # noqa: BLE001
                self.query_one("#status", Static).update(str(exc))
                return
            for item in self._listings:
                price = f"¥{format_cny(item.get('price'))}" if item.get("price") is not None else "-"
                table.add_row(
                    item.get("sku") or "",
                    listing_family_name(item.get("listing_key")) or "-",
                    price,
                    format_gb(item.get("ram_gb")) or "-",
                    format_gb(item.get("storage_gb")) or "-",
                    (item.get("title") or "")[:48],
                )

        def reload_watches(self) -> None:
            table = self.query_one("#watch-table", DataTable)
            table.clear()
            try:
                self._watches = list(self.client.watches() or [])
            except Exception as exc:  # noqa: BLE001
                self.notify(str(exc))
                return
            from apple_refurb_watch.match import matches_watch

            try:
                stock = (self.client.listings() or {}).get("items") or []
            except Exception:  # noqa: BLE001
                stock = self._listings
            for watch in self._watches:
                matched = sum(1 for item in stock if matches_watch(item, watch)) if stock else 0
                cond = watch_condition_label(watch)
                table.add_row(
                    str(watch.get("id") or ""),
                    "启用" if watch.get("enabled") else "暂停",
                    "精确 SKU" if watch.get("mode") == "sku" else "条件",
                    str(matched),
                    (cond or "—")[:40],
                    str(watch.get("name") or ""),
                )

        def reload_events(self) -> None:
            table = self.query_one("#event-table", DataTable)
            table.clear()
            try:
                events = self.client.events(limit=80)
            except Exception as exc:  # noqa: BLE001
                self.notify(str(exc))
                return
            if not events:
                table.add_row("—", "—", "—", "还没有记录。首次扫描只建基线。")
                return
            watch_names = {
                int(item["id"]): str(item.get("name") or "")
                for item in (self._watches or [])
                if item.get("id")
            }
            for day in present_event_days(events, watch_names=watch_names):
                for event in day["entries"]:
                    when = str(event.get("when_local") or format_localtime(event.get("created_at")))
                    clock = when[11:] if len(when) >= 16 else when
                    kind = str(event.get("type") or "")
                    table.add_row(
                        str(day["day"]),
                        clock,
                        str(event.get("label") or EVENT_LABELS.get(kind, kind)),
                        str(event.get("title") or event.get("message") or "")[:64],
                    )

        def reload_settings(self) -> None:
            try:
                settings = self.client.settings()
            except Exception as exc:  # noqa: BLE001
                self.query_one("#settings-note", Static).update(str(exc))
                return
            switch = self.query_one("#listen-switch", Switch)
            with switch.prevent(Switch.Changed):
                switch.value = bool(settings.get("listen_enabled"))
            self._apply_listing_switches(settings.get("listings") or [])
            self._update_sort_label()
            self.query_one("#settings-note", Static).update(
                f"间隔 {settings.get('interval_seconds')} 秒 · {settings.get('bind_host')}:{settings.get('bind_port')} · 密钥请用网页设置"
            )

    return RefurbApp(client)


def run_tui() -> None:
    create_tui(ensure_daemon()).run()
