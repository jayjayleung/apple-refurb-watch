from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
import uvicorn

from apple_refurb_watch import __version__
from apple_refurb_watch.api import create_app
from apple_refurb_watch.web.app import apply_windows_loop_policy, uvicorn_options
from apple_refurb_watch.argv import apply_windows_console, ensure_stdio, is_frozen, with_frozen_default_command
from apple_refurb_watch.categories import listing_family_name, listings_family_names
from apple_refurb_watch.client import ApiClient, ApiError
from apple_refurb_watch.connection import clear_connection, load_connection, resolve_client, save_connection
from apple_refurb_watch.daemon import acquire_lock, ensure_daemon, is_running, stop_daemon
from apple_refurb_watch.db import Database
from apple_refurb_watch.storage.schema import DEFAULT_BIND_PORT
from apple_refurb_watch.listing import format_cny, format_gb
from apple_refurb_watch.paths import data_dir
from apple_refurb_watch.scanner import run_scan
from apple_refurb_watch.status_view import EVENT_LABELS, format_localtime, present_event_days
from apple_refurb_watch.usecases import list_shop
from apple_refurb_watch.watches import watch_condition_label
from apple_refurb_watch.web.auth import validate_listener_security

app = typer.Typer(help="苹果中国官翻指定配置监听", no_args_is_help=True, rich_markup_mode="rich")
watch_app = typer.Typer(help="监听规则", rich_help_panel="监听")
service_app = typer.Typer(help="开机自启")
settings_app = typer.Typer(help="设置", rich_help_panel="设置")
events_app = typer.Typer(help="动态", invoke_without_command=True)
config_app = typer.Typer(help="配置导入导出", rich_help_panel="运维")
app.add_typer(watch_app, name="watch")
app.add_typer(service_app, name="service")
app.add_typer(settings_app, name="settings")
app.add_typer(events_app, name="events")
app.add_typer(config_app, name="config")

ENV_ACCESS_TOKEN = "APPLE_REFURB_WATCH_ACCESS_TOKEN"


def apply_serve_bind(db: Database, host: str | None, port: int | None, *, persist: bool) -> tuple[str, int]:
    settings = db.settings()
    bind_host = host or settings.get("bind_host") or "127.0.0.1"
    bind_port = int(port if port is not None else (settings.get("bind_port") or DEFAULT_BIND_PORT))
    if persist:
        if host:
            db.set_setting("bind_host", bind_host)
        if port is not None:
            db.set_setting("bind_port", bind_port)
    return bind_host, bind_port


def apply_env_access_token(db: Database) -> None:
    token = str(os.environ.get(ENV_ACCESS_TOKEN) or "").strip()
    if not token:
        return
    if str(db.get_setting("access_token") or "").strip():
        return
    db.set_setting("access_token", token)


def _client() -> ApiClient:
    return resolve_client(start_local=True)


def _refuse_local_against_remote() -> None:
    conn = load_connection()
    if conn.url:
        typer.echo("已配置远端服务器，--local 只读本机库。请去掉 --local，或先 apple-refurb-watch disconnect。", err=True)
        raise typer.Exit(2)


def _require_local_maintenance(*, stop_required: bool = False) -> None:
    """Guard commands that operate on the local authority database."""

    conn = load_connection()
    if conn.url:
        typer.echo("当前 CLI 已连接远端服务；备份/恢复/配置维护请在权威服务所在机器执行。", err=True)
        raise typer.Exit(2)
    if stop_required and is_running():
        typer.echo("请先停止本机 daemon，再执行会替换或批量写入数据库的维护命令。", err=True)
        raise typer.Exit(2)


def _dump(data) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


def _parse_dims(values: list[str] | None) -> dict[str, list[str]]:
    dims: dict[str, list[str]] = {}
    for raw in values or []:
        if "=" not in raw:
            typer.echo(f"维度应为 key=value，收到 {raw}", err=True)
            raise typer.Exit(2)
        key, value = raw.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or not value:
            typer.echo(f"维度应为 key=value，收到 {raw}", err=True)
            raise typer.Exit(2)
        dims.setdefault(key, []).append(value)
    return dims


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
    host: Optional[str] = typer.Option(None, help="覆盖绑定地址，仅本次进程"),
    port: Optional[int] = typer.Option(None, help="覆盖端口，仅本次进程"),
    persist: bool = typer.Option(False, "--persist", help="把 --host/--port 写入本机设置"),
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
    apply_env_access_token(db)
    bind_host, bind_port = apply_serve_bind(db, host, port, persist=persist)
    effective_settings = db.settings()
    # Validate the effective address (including one-shot CLI overrides) before
    # handing the socket to uvicorn.  A malformed remote configuration must
    # fail closed and release the singleton lock cleanly.
    effective_settings["bind_host"] = bind_host
    try:
        validate_listener_security(effective_settings)
    except RuntimeError as exc:
        db.close()
        lock.close()
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    try:
        fastapi_app = create_app(
            db,
            with_scheduler=True,
            close_database=True,
            listener_host=bind_host,
            listener_port=bind_port,
        )
    except Exception:
        db.close()
        lock.close()
        raise
    typer.echo(f"网页: http://{'127.0.0.1' if bind_host in {'0.0.0.0', '::'} else bind_host}:{bind_port}")
    try:
        apply_windows_loop_policy()
        uvicorn.run(fastapi_app, host=bind_host, port=bind_port, log_level="info", **uvicorn_options())
    finally:
        lock.close()


@app.command()
def desktop(
    hidden: bool = typer.Option(False, "--hidden", help="启动后隐藏窗口，只留托盘"),
    probe: bool = typer.Option(False, "--probe", help="不打开窗口，只检查本机服务能否启动"),
) -> None:
    """打开桌面窗口（本机模式同进程自带服务）。"""
    from apple_refurb_watch.desktop import probe_runtime, run_desktop

    try:
        if probe:
            result = probe_runtime()
            typer.echo("desktop probe ok")
            for key, value in (result.get("notes") or {}).items():
                typer.echo(f"{key}: {value}")
            return
        run_desktop(hidden=hidden)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@app.command()
def tui() -> None:
    """终端界面。"""
    try:
        from apple_refurb_watch.tui_app import run_tui

        run_tui()
    except ImportError as exc:
        typer.echo("请先安装 TUI 依赖：pip install -e '.[tui]'", err=True)
        raise typer.Exit(1) from exc


@app.command("list", rich_help_panel="在售")
def list_products(
    q: Optional[str] = typer.Option(None, "--q", help="关键词"),
    listing: Optional[str] = typer.Option(None, "--listing", help="分类 key，如 mac / ipad"),
    sort: str = typer.Option("price", "--sort", help="price 低到高，-price 高到低"),
    dim: Optional[list[str]] = typer.Option(None, "--dim", help="维度 key=value，可重复"),
    max_price: Optional[float] = typer.Option(None, "--max-price"),
    min_ram: Optional[int] = typer.Option(None, "--min-ram"),
    min_storage: Optional[int] = typer.Option(None, "--min-storage"),
    local: bool = typer.Option(False, "--local", help="不走 daemon，直接读本地库"),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """在售列表。只显示当前监听分类。"""
    filters = {
        "q": q,
        "listing_key": listing,
        "max_price": max_price,
        "min_ram_gb": min_ram,
        "min_storage_gb": min_storage,
        "dim_filters": _parse_dims(dim),
    }
    if local:
        _refuse_local_against_remote()
        database = Database()
        items = list_shop(database, filters, sort, page_size=None)["all_items"]
    else:
        items = _client().listings(all_pages=True, sort=sort, **filters).get("items") or []
    if as_json:
        _dump(items)
        return
    if not items:
        typer.echo("没有在售数据。先运行 apple-refurb-watch scan")
        return
    for item in items:
        price = f"¥{format_cny(item['price'])}" if item.get("price") is not None else "-"
        ram = format_gb(item.get("ram_gb")) or "-"
        ssd = format_gb(item.get("storage_gb")) or "-"
        family = listing_family_name(item.get("listing_key")) or "-"
        typer.echo(f"{item['sku']:<16} {family:<8} {price:<10} {ram:<8} {ssd:<8} {item['title']}")


@app.command()
def scan(
    local: bool = typer.Option(False, "--local", help="不启动 daemon，本进程扫描一次"),
) -> None:
    if local:
        _refuse_local_against_remote()
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


@app.command()
def home() -> None:
    """打印数据目录。"""
    typer.echo(str(data_dir()))


@app.command()
def backup(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="备份文件或目录"),
    keep: int = typer.Option(8, "--keep", min=1, help="自动备份最多保留份数"),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """创建并校验 SQLite 在线备份。"""
    from apple_refurb_watch.maintenance import backup_database

    _require_local_maintenance()
    try:
        result = backup_database(destination=output, keep=keep)
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if as_json:
        _dump(result)
    else:
        typer.echo(f"备份完成: {result['backup']}")
        typer.echo(f"完整性: {result.get('integrity', 'unknown')}")


@app.command()
def compact(
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """备份后 VACUUM，回收已删除扫描快照占用的空间。"""
    from apple_refurb_watch.maintenance import compact_database

    _require_local_maintenance(stop_required=True)
    try:
        result = compact_database()
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if as_json:
        _dump(result)
    else:
        typer.echo(f"压缩完成: {result['path']}")
        typer.echo(f"备份: {result.get('backup')}")
        typer.echo(f"体积: {result.get('bytes_before')} -> {result.get('bytes_after')}")


@app.command()
def restore(
    backup_path: Path = typer.Argument(..., metavar="BACKUP", help="已校验的 .db 备份"),
    target: Optional[Path] = typer.Option(None, "--target", help="目标数据库，默认本机权威库"),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """停止 daemon 后恢复 SQLite，并保留恢复前副本。"""
    from apple_refurb_watch.maintenance import restore_database

    _require_local_maintenance(stop_required=True)
    try:
        result = restore_database(backup_path, target)
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if as_json:
        _dump(result)
    else:
        typer.echo(f"恢复完成: {result['restored']}")
        if result.get("prior"):
            typer.echo(f"恢复前副本: {result['prior'].get('backup')}")


@app.command("doctor")
def doctor_cmd(
    as_json: bool = typer.Option(True, "--json/--human", help="输出 JSON（默认）"),
) -> None:
    """检查数据库、监听安全、daemon 和未完成扫描。"""
    from apple_refurb_watch.maintenance import doctor as run_doctor

    _require_local_maintenance()
    try:
        result = run_doctor()
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if as_json:
        _dump(result)
    else:
        status_label = "正常" if result.get("ok") else "异常"
        typer.echo(f"诊断: {status_label}")
        typer.echo(f"数据库: {result.get('database', {}).get('integrity', 'unknown')}")
        typer.echo(f"库体积: {result.get('database_bytes', 0)}")
        typer.echo(f"扫描记录: {result.get('scan_runs', 0)}")
        typer.echo(f"快照行: {result.get('observations', 0)}")
        typer.echo(f"待投递: {result.get('pending_deliveries', 0)}")
        typer.echo(f"回收孤儿扫描: {result.get('abandoned_runs_recovered', 0)}")
    if not result.get("ok"):
        raise typer.Exit(1)


@config_app.command("export")
def config_export(
    path: Optional[Path] = typer.Argument(None, metavar="PATH", help="输出文件；省略则打印 JSON"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出文件（与 PATH 二选一）"),
    include_secrets: bool = typer.Option(False, "--include-secrets", help="显式包含访问口令和通知密钥"),
    as_json: bool = typer.Option(False, "--json", help="即使写入文件也打印 JSON"),
) -> None:
    """导出规则和设置，默认排除所有密钥。"""
    from apple_refurb_watch.maintenance import export_config

    _require_local_maintenance()
    if path is not None and output is not None:
        typer.echo("PATH 和 --output 只能指定一个", err=True)
        raise typer.Exit(2)
    destination = path or output
    try:
        result = export_config(destination, include_secrets=include_secrets)
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if destination is None or as_json:
        _dump(result)
    else:
        typer.echo(f"配置已导出: {destination}")


@config_app.command("import")
def config_import(
    path: Path = typer.Argument(..., metavar="PATH", help="配置 JSON 文件"),
    include_secrets: bool = typer.Option(False, "--include-secrets", help="允许替换本地访问口令和通知密钥"),
    replace_watches: bool = typer.Option(False, "--replace-watches", help="先删除本地规则再导入"),
) -> None:
    """原子导入规则和设置；默认保留本地密钥。"""
    from apple_refurb_watch.maintenance import import_config

    _require_local_maintenance(stop_required=True)
    try:
        result = import_config(
            path,
            include_secrets=include_secrets,
            replace_watches=replace_watches,
        )
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    # ``import_config`` returns the updated settings for library callers.  Do
    # not echo retained/replaced credentials into shell history or CI logs.
    if isinstance(result.get("settings"), dict):
        from apple_refurb_watch.settings import public_settings

        result = dict(result)
        result["settings"] = public_settings(result["settings"])
    _dump(result)


@watch_app.command("ls")
def watch_ls(
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """列出监听规则。"""
    watches = _client().watches()
    if as_json:
        _dump(watches)
        return
    if not watches:
        typer.echo("还没有规则。用 watch add 或网页监听页创建。")
        return
    stock = []
    try:
        stock = _client().listings(all_pages=True).get("items") or []
    except ApiError:
        stock = []
    from apple_refurb_watch.match import matches_watch

    for watch in watches:
        flag = "启用" if watch.get("enabled") else "暂停"
        mode = "精确 SKU" if watch.get("mode") == "sku" else "条件"
        matched = sum(1 for item in stock if matches_watch(item, watch)) if stock else 0
        cond = watch_condition_label(watch)
        extra = f"  {cond}" if cond else ""
        typer.echo(f"{watch['id']:<4} {flag:<4} {mode:<8} 在售 {matched:<3} {watch['name']}{extra}")


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
    min_price: Optional[float] = typer.Option(None, "--min-price"),
    max_price: Optional[float] = typer.Option(None, "--max-price"),
    listing: Optional[str] = typer.Option(None, "--listing"),
    dim: Optional[list[str]] = typer.Option(None, "--dim", help="维度 key=value，可重复"),
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
            "min_price": min_price,
            "max_price": max_price,
            "listing_key": listing,
            "dim_filters": _parse_dims(dim),
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
def service_install(
    serve: bool = typer.Option(False, "--serve", help="拉起网页服务，不要托盘"),
    tray: bool = typer.Option(False, "--tray", help="拉起桌面托盘"),
) -> None:
    from apple_refurb_watch.service import install_service

    if serve and tray:
        typer.echo("不要同时使用 --serve 和 --tray", err=True)
        raise typer.Exit(2)
    desktop = True if tray else False if serve else None
    typer.echo(install_service(desktop=desktop))


@service_app.command("uninstall")
def service_uninstall() -> None:
    from apple_refurb_watch.service import uninstall_service

    typer.echo(uninstall_service())


@service_app.command("status")
def service_status() -> None:
    from apple_refurb_watch.service import service_status as status_fn

    typer.echo(status_fn())


def _service_action(fn) -> None:
    try:
        typer.echo(fn())
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@service_app.command("start")
def service_start() -> None:
    """启动已安装的开机任务。"""
    from apple_refurb_watch.service import start_service

    _service_action(start_service)


@service_app.command("stop")
def service_stop() -> None:
    """停止已安装的开机任务（不卸载）。"""
    from apple_refurb_watch.service import stop_service

    _service_action(stop_service)


@service_app.command("restart")
def service_restart() -> None:
    """重启已安装的开机任务。"""
    from apple_refurb_watch.service import restart_service

    _service_action(restart_service)


@events_app.callback(invoke_without_command=True)
def events(
    ctx: typer.Context,
    limit: int = typer.Option(50, "--limit", min=1, max=500),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON（时间为 UTC）"),
) -> None:
    """动态。无子命令时列出记录。"""
    if ctx.invoked_subcommand:
        return
    client = _client()
    rows = client.events(limit=limit)
    if as_json:
        _dump(rows)
        return
    if not rows:
        typer.echo("还没有记录。先运行 apple-refurb-watch scan")
        return
    watch_names: dict[int, str] = {}
    try:
        watch_names = {
            int(item["id"]): str(item.get("name") or "")
            for item in (client.watches() or [])
            if item.get("id")
        }
    except ApiError:
        watch_names = {}
    for day in present_event_days(rows, watch_names=watch_names):
        for event in day["entries"]:
            kind = str(event.get("type") or "")
            when = str(event.get("when_local") or format_localtime(event.get("created_at")))
            body = event.get("title") or event.get("message") or ""
            typer.echo(f"{when}  {str(event.get('label') or EVENT_LABELS.get(kind, kind)):<8}  {body}")


@events_app.command("clear")
def events_clear() -> None:
    """清除动态记录，不影响在售和规则。"""
    result = _client().clear_events() or {}
    typer.echo(f"已清除 {result.get('deleted', 0)} 条记录")


@settings_app.command("get")
def settings_get(
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """查看设置（不含密钥）。"""
    data = _client().settings()
    if as_json:
        _dump(data)
        return
    typer.echo(f"监听  {'开' if data.get('listen_enabled') else '关'}")
    typer.echo(f"间隔  {data.get('interval_seconds')} 秒")
    typer.echo(f"绑定  {data.get('bind_host')}:{data.get('bind_port')}")
    typer.echo(f"远程访问  {'开' if data.get('lan_enabled') else '关'}")
    names = listings_family_names(data.get("listings"))
    typer.echo(f"分类  {', '.join(names) if names else '-'}")


@settings_app.command("set")
def settings_set(
    interval: Optional[int] = typer.Option(None, "--interval", help="扫描间隔（秒）"),
    listen: Optional[bool] = typer.Option(None, "--listen/--no-listen", help="定时监听"),
    listings: Optional[str] = typer.Option(None, "--listings", help="分类 key，逗号分隔"),
    lan: Optional[bool] = typer.Option(None, "--lan/--no-lan", help="允许远程访问"),
) -> None:
    """改安全项。口令和 Webhook 请用网页设置页。"""
    patch: dict = {}
    if interval is not None:
        patch["interval_seconds"] = interval
    if listen is not None:
        patch["listen_enabled"] = listen
    if listings is not None:
        patch["listings"] = [part.strip() for part in listings.split(",") if part.strip()]
    if lan is not None:
        patch["lan_enabled"] = lan
    if not patch:
        typer.echo("没有要改的项。可用 --interval / --listen / --listings / --lan")
        raise typer.Exit(1)
    _dump(_client().update_settings(patch))


@settings_app.command("sync-catalog")
def settings_sync_catalog() -> None:
    """从官网同步筛选词条。"""
    result = _client().sync_catalog() or {}
    if result.get("ok"):
        typer.echo("已从官网同步筛选词条")
        return
    typer.echo(str(result), err=True)
    raise typer.Exit(1)


@app.command()
def connect(
    url: str = typer.Argument(..., help="服务器地址，如 http://192.168.1.8:8765"),
    token: Optional[str] = typer.Option(None, "--token", help="访问口令"),
    insecure: bool = typer.Option(False, "--insecure", help="允许公网 HTTP"),
) -> None:
    """改连远端服务器。本机不再扫描。"""
    try:
        conn = save_connection(url, token, allow_insecure=insecure)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"已连接 {conn.url}")


@app.command()
def disconnect() -> None:
    """改回本机服务。"""
    clear_connection()
    typer.echo("已改回本机")


def main() -> None:
    sys.argv = with_frozen_default_command(
        sys.argv,
        frozen=is_frozen(),
        platform=sys.platform,
    )
    apply_windows_console(sys.argv, frozen=is_frozen(), platform=sys.platform)
    ensure_stdio()
    try:
        app()
    except ApiError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    main()
