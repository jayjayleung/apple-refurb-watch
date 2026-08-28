from __future__ import annotations

import json

from apple_refurb_watch.client import ApiClient
from apple_refurb_watch.daemon import ensure_daemon


def run_tui() -> None:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

    class RefurbApp(App[None]):
        CSS = """
        Screen { background: #1c1914; color: #f6efe4; }
        DataTable { height: 1fr; }
        #side { width: 28; border-right: solid #4a4036; padding: 1; }
        .title { text-style: bold; color: #e8c36a; }
        """
        BINDINGS = [
            Binding("q", "quit", "退出"),
            Binding("s", "scan", "扫描"),
            Binding("r", "reload", "刷新"),
        ]

        def __init__(self, client: ApiClient) -> None:
            super().__init__()
            self.client = client

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal():
                with Vertical(id="side"):
                    yield Static("官翻监听", classes="title")
                    yield Button("刷新在售", id="reload")
                    yield Button("立即扫描", id="scan")
                    yield Button("测试通知", id="notify")
                    yield Label("关键词")
                    yield Input(placeholder="M5 Pro", id="q")
                    yield Label("状态")
                    yield Static("连接中…", id="status")
                yield DataTable(id="table")
            yield Footer()

        def on_mount(self) -> None:
            table = self.query_one("#table", DataTable)
            table.add_columns("SKU", "价格", "内存", "硬盘", "标题")
            self.reload_table()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "reload":
                self.reload_table()
            elif event.button.id == "scan":
                self.action_scan()
            elif event.button.id == "notify":
                try:
                    result = self.client.notify_test()
                    self.notify(json.dumps(result, ensure_ascii=False))
                except Exception as exc:  # noqa: BLE001
                    self.notify(str(exc))

        def action_reload(self) -> None:
            self.reload_table()

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
                    self.reload_table()

            self.call_from_thread(apply)

        def reload_table(self) -> None:
            table = self.query_one("#table", DataTable)
            table.clear()
            q = self.query_one("#q", Input).value.strip() or None
            try:
                payload = self.client.listings(q=q)
                items = payload.get("items") or []
                status = self.client.status()
                self.query_one("#status", Static).update(
                    f"规则 {status.get('watch_count')} · 上次 {status.get('last_success_at') or '尚未扫描'}"
                )
            except Exception as exc:  # noqa: BLE001
                self.query_one("#status", Static).update(str(exc))
                return
            for item in items:
                table.add_row(
                    item.get("sku") or "",
                    str(item.get("price") or ""),
                    str(item.get("ram_gb") or ""),
                    str(item.get("storage_gb") or ""),
                    (item.get("title") or "")[:48],
                )

    client = ensure_daemon()
    RefurbApp(client).run()
