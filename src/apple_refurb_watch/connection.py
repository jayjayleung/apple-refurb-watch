from __future__ import annotations

import ipaddress
import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from apple_refurb_watch.client import ApiClient
from apple_refurb_watch.paths import data_dir

ENV_URL = "APPLE_REFURB_WATCH_URL"
ENV_TOKEN = "APPLE_REFURB_WATCH_TOKEN"
CLIENT_API_REVISION = 2
CORE_CAPABILITIES = frozenset({"listings", "watches", "events"})
OPTIONAL_CAPABILITY_LABELS = {
    "events.after_id": "电脑通知",
    "notify.deliveries": "通知投递重试",
    "filter-catalog": "筛选词条同步",
}


@dataclass
class Connection:
    mode: str  # local | remote
    url: str | None = None
    token: str | None = None
    allow_insecure: bool = False
    computer_notify: bool = True


def connection_path() -> Path:
    return data_dir() / "connection.json"


def token_path() -> Path:
    return data_dir() / "connection.token"


def _http_ok(host: str) -> bool:
    name = (host or "").strip().lower().rstrip(".")
    if name in {"localhost", "127.0.0.1", "::1"}:
        return True
    if name.endswith(".local") or name.endswith(".lan"):
        return True
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


def validate_server_url(url: str, *, allow_insecure: bool = False) -> str:
    text = str(url or "").strip()
    if not text:
        raise ValueError("请填写服务器地址")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("地址须为 http:// 或 https:// 开头")
    if parsed.username or parsed.password:
        raise ValueError("口令不要写在地址里，请单独填写")
    host = parsed.hostname or ""
    if parsed.scheme == "http" and not allow_insecure and not _http_ok(host):
        raise ValueError("公网地址请使用 https://")
    return text.rstrip("/")


def _read_json() -> dict:
    path = connection_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_token_file() -> str:
    path = token_path()
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_token(token: str) -> None:
    text = str(token or "").strip()
    path = token_path()
    if not text:
        try:
            path.unlink()
        except OSError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.unlink()
    except OSError:
        pass
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_connection() -> Connection:
    env_url = str(os.environ.get(ENV_URL) or "").strip()
    env_token = str(os.environ.get(ENV_TOKEN) or "")
    stored = _read_json()
    allow_insecure = bool(stored.get("allow_insecure"))
    computer_notify = stored.get("computer_notify")
    if computer_notify is None:
        computer_notify = True
    url = env_url or str(stored.get("url") or "").strip()
    token = env_token or _read_token_file() or str(stored.get("token") or "")
    if url:
        try:
            url = validate_server_url(url, allow_insecure=allow_insecure or _http_ok(urlparse(url).hostname or ""))
        except ValueError:
            url = ""
        if url:
            return Connection(
                mode="remote",
                url=url,
                token=token or None,
                allow_insecure=allow_insecure,
                computer_notify=bool(computer_notify),
            )
    return Connection(mode="local", url=None, token=token or None, computer_notify=bool(computer_notify))


def save_connection(url: str, token: str | None = None, *, allow_insecure: bool = False) -> Connection:
    clean = validate_server_url(url, allow_insecure=allow_insecure)
    payload = {
        "mode": "remote",
        "url": clean,
        "allow_insecure": bool(allow_insecure),
        "computer_notify": load_connection().computer_notify,
    }
    connection_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_token(token or "")
    return load_connection()


def save_computer_notify(enabled: bool) -> None:
    stored = _read_json()
    stored["computer_notify"] = bool(enabled)
    connection_path().write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_connection() -> None:
    for path in (connection_path(), token_path()):
        try:
            path.unlink()
        except OSError:
            pass


def inferred_capabilities(health: dict | None) -> set[str]:
    if not isinstance(health, dict):
        return set()
    caps = health.get("capabilities")
    if isinstance(caps, list) and caps:
        return {str(item) for item in caps if item}
    return set(CORE_CAPABILITIES)


def has_capability(health: dict | None, name: str) -> bool:
    return name in inferred_capabilities(health)


def check_client_compat(health: dict | None) -> str | None:
    if not isinstance(health, dict):
        return "服务器没有返回健康信息，请确认地址和口令"
    if health.get("ok") is False:
        return "服务器报告未就绪"
    revision = health.get("api_revision")
    if revision is not None:
        try:
            remote = int(revision)
        except (TypeError, ValueError):
            remote = None
        else:
            if remote > CLIENT_API_REVISION:
                return f"服务器 API 修订 {remote} 新于本客户端 {CLIENT_API_REVISION}，请升级客户端"
    caps_raw = health.get("capabilities")
    if isinstance(caps_raw, list) and caps_raw:
        missing_core = CORE_CAPABILITIES - {str(item) for item in caps_raw if item}
        if missing_core:
            return f"服务器缺少能力 {', '.join(sorted(missing_core))}，请升级服务器"
    return None


def compat_notice(health: dict | None) -> str | None:
    if not isinstance(health, dict) or health.get("ok") is False:
        return None
    caps = inferred_capabilities(health)
    missing_labels = [label for name, label in OPTIONAL_CAPABILITY_LABELS.items() if name not in caps]
    revision = health.get("api_revision")
    try:
        remote = int(revision) if revision is not None else None
    except (TypeError, ValueError):
        remote = None
    old_payload = not isinstance(health.get("capabilities"), list) or not health.get("capabilities")
    if missing_labels:
        if old_payload or remote is None:
            return (
                "服务器版本较旧，"
                + "、".join(missing_labels)
                + "不可用。可继续使用核心功能，或升级服务器。"
            )
        return "此服务器未提供" + "、".join(missing_labels) + "。可继续使用其余功能。"
    if remote is not None and remote < CLIENT_API_REVISION:
        return (
            f"服务器 API 修订 {remote} 旧于本客户端 {CLIENT_API_REVISION}，"
            "部分新功能已隐藏。可升级服务器。"
        )
    return None


def resolve_client(*, start_local: bool = True) -> ApiClient:
    conn = load_connection()
    if conn.url:
        return ApiClient(conn.url, conn.token)
    if start_local:
        from apple_refurb_watch.daemon import ensure_daemon

        return ensure_daemon()
    return ApiClient()
