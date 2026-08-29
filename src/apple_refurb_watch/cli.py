from __future__ import annotations

import json
import sys
from typing import Optional

import typer
import uvicorn

from apple_refurb_watch import __version__
from apple_refurb_watch.api import create_app
from apple_refurb_watch.argv import with_frozen_default_command
from apple_refurb_watch.client import ApiClient, ApiError
from apple_refurb_watch.daemon import acquire_lock, ensure_daemon, is_running, stop_daemon
from apple_refurb_watch.db import Database
from apple_refurb_watch.paths import data_dir
from apple_refurb_watch.scanner import run_scan

app = typer.Typer(help="苹果中国官翻指定配置监听", no_args_is_help=True)
watch_app = typer.Typer(help="管理监听规则")
service_app = typer.Typer(help="安装/卸载开机自启")
app.add_typer(watch_app, name="watch")
app.add_typer(service_app, name="service")


def _client() -> ApiClient:
    return ensure_daemon()


@app.callback()
def _root() -> None:
    return


@app.command()
def version() -> None:
    typer.echo(__version__)


@app.command()
def serve(
    detach: bool = typer.Option(False, "--detach", help="放到后台运行"),
    detach_child: bool = typer.Option(False, "--detach-child", hidden=True),
    host: Optional[str] = typer.Option(None, help="覆盖绑定地址"),
    port: Optional[int] = typer.Option(None, help="覆盖端口"),
) -> None:
    """启动 daemon + 网页。默认前台；--detach 后台。"""
    if detach and not detach_child:
        ensure_daemon(host=host, port=port)
        typer.echo(f"daemon 已启动，打开 {ApiClient().base}")
        return
    try:
        lock = acquire_lock()
    except RuntimeError:
        typer.echo("daemon 已在运行。网页可用 apple-refurb-watch status 查看地址。")
        raise typer.Exit(1)
    db = Database()
    settings = db.settings()
    bind_host = host or settings.get("bind_host") or "127.0.0.1"
    bind_port = port or int(settings.get("bind_port") or 8765)
    if host:
        db.set_setting("bind_host", bind_host)
    if port:
        db.set_setting("bind_port", bind_port)
    fastapi_app = create_app(db, with_scheduler=True)
    typer.echo(f"网页: http://{'127.0.0.1' if bind_host in {'0.0.0.0', '::'} else bind_host}:{bind_port}")
    try:
        uvicorn.run(fastapi_app, host=bind_host, port=bind_port, log_level="info")
    finally:
        lock.close()


@app.command()
def desktop() -> None:
    """打开桌面窗口（自动拉起 daemon）。"""
    from apple_refurb_watch.desktop import run_desktop

    try:
        run_desktop()
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@app.command()
def tui() -> None:
    """终端界面。"""
    try:
        from apple_refurb_watch.tui_app import run_tui
    except ImportError as exc:
        typer.echo("请先安装 TUI 依赖：pip install -e '.[tui]'", err=True)
        raise typer.Exit(1) from exc
    run_tui()


@app.command("list")
def list_products(
    q: Optional[str] = typer.Option(None, "--q", help="关键词"),
    listing: Optional[str] = typer.Option(None, "--listing", help="分类 key"),
    local: bool = typer.Option(False, "--local", help="不走 daemon，直接读本地库"),
) -> None:
    if local:
        items = Database().list_products(in_stock=True)
        if q or listing:
            from apple_refurb_watch.web.listing import filter_products

            items = filter_products(items, q=q, listing_key=listing)
    else:
        items = _client().listings(q=q, listing_key=listing).get("items") or []
    if not items:
        typer.echo("没有在售数据。先运行 apple-refurb-watch scan")
        return
    for item in items:
        price = f"RMB {item['price']:.0f}" if item.get("price") is not None else "-"
        ram = f"{item['ram_gb']}GB" if item.get("ram_gb") else "?"
        ssd = f"{item['storage_gb']}GB" if item.get("storage_gb") else "?"
        typer.echo(f"{item['sku']}\t{price}\t{ram}/{ssd}\t{item['title']}")


@app.command()
def scan(
    local: bool = typer.Option(False, "--local", help="不启动 daemon，本进程扫描一次"),
) -> None:
    if local:
        result = run_scan()
    else:
        result = _client().scan()
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("notify-test")
def notify_test() -> None:
    typer.echo(json.dumps(_client().notify_test(), ensure_ascii=False))


@app.command()
def status() -> None:
    if is_running():
        typer.echo(json.dumps(_client().status(), ensure_ascii=False, indent=2))
    else:
        typer.echo("daemon 未运行")
        raise typer.Exit(1)


@app.command()
def stop() -> None:
    if stop_daemon():
        typer.echo("已发送停止信号")
    else:
        typer.echo("没有找到运行中的 daemon")


@watch_app.command("ls")
def watch_ls() -> None:
    for watch in _client().watches():
        flag = "on " if watch.get("enabled") else "off"
        typer.echo(f"{watch['id']}\t{flag}\t{watch['mode']}\t{watch['name']}")


@watch_app.command("add")
def watch_add(
    name: str = typer.Option(..., "--name"),
    mode: str = typer.Option("condition", "--mode"),
    sku: Optional[str] = typer.Option(None, "--sku"),
    all_of: Optional[str] = typer.Option(None, "--all-of", help="逗号分隔"),
    none_of: Optional[str] = typer.Option(None, "--none-of"),
    colors: Optional[str] = typer.Option(None, "--colors"),
    min_ram_gb: Optional[int] = typer.Option(None, "--min-ram"),
    min_storage_gb: Optional[int] = typer.Option(None, "--min-storage"),
    max_price: Optional[float] = typer.Option(None, "--max-price"),
    listing: Optional[str] = typer.Option(None, "--listing"),
) -> None:
    def split(value: str | None) -> list[str]:
        if not value:
            return []
        return [p.strip() for p in value.split(",") if p.strip()]

    created = _client().create_watch(
        {
            "name": name,
            "mode": mode,
            "sku": sku,
            "all_of": split(all_of),
            "none_of": split(none_of),
            "colors": split(colors),
            "min_ram_gb": min_ram_gb,
            "min_storage_gb": min_storage_gb,
            "max_price": max_price,
            "listing_key": listing,
        }
    )
    typer.echo(json.dumps(created, ensure_ascii=False, indent=2))


@watch_app.command("pause")
def watch_pause(watch_id: int) -> None:
    typer.echo(json.dumps(_client().update_watch(watch_id, {"enabled": False}), ensure_ascii=False))


@watch_app.command("resume")
def watch_resume(watch_id: int) -> None:
    typer.echo(json.dumps(_client().update_watch(watch_id, {"enabled": True}), ensure_ascii=False))


@watch_app.command("rm")
def watch_rm(watch_id: int) -> None:
    _client().delete_watch(watch_id)
    typer.echo("已删除")


@service_app.command("install")
def service_install() -> None:
    from apple_refurb_watch.service import install_service

    typer.echo(install_service())


@service_app.command("uninstall")
def service_uninstall() -> None:
    from apple_refurb_watch.service import uninstall_service

    typer.echo(uninstall_service())


@service_app.command("status")
def service_status() -> None:
    from apple_refurb_watch.service import service_status as status_fn

    typer.echo(status_fn())


@app.command()
def home() -> None:
    typer.echo(str(data_dir()))


def main() -> None:
    sys.argv = with_frozen_default_command(
        sys.argv,
        frozen=getattr(sys, "frozen", False),
        platform=sys.platform,
    )
    try:
        app()
    except ApiError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    main()
