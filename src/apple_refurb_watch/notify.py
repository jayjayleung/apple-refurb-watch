from __future__ import annotations

import base64
import hashlib
import hmac
import smtplib
import time
from email.message import EmailMessage
from html import escape
from typing import Any, Callable
from urllib.parse import quote, unquote

import httpx


class NotifyError(RuntimeError):
    pass


SECRET_FIELDS = {
    "url",
    "sendkey",
    "token",
    "webhook",
    "secret",
    "bot_token",
    "password",
    "key",
    "device_key",
}


def _secret_values(settings: dict[str, Any] | None) -> list[str]:
    values: list[str] = []
    notify = (settings or {}).get("notify") or {}
    if not isinstance(notify, dict):
        return values
    for conf in notify.values():
        if not isinstance(conf, dict):
            continue
        for field, raw in conf.items():
            if field not in SECRET_FIELDS:
                continue
            text = str(raw or "").strip()
            if text:
                values.append(text)
    values.sort(key=len, reverse=True)
    return values


def redact_secrets(text: str, settings: dict[str, Any] | None = None) -> str:
    result = str(text or "")
    for secret in _secret_values(settings):
        if secret in result:
            result = result.replace(secret, "***")
        encoded = quote(secret, safe="")
        if encoded and encoded != secret and encoded in result:
            result = result.replace(encoded, "***")
        decoded = unquote(secret)
        if decoded and decoded != secret and decoded in result:
            result = result.replace(decoded, "***")
    return result


def send_all(settings: dict[str, Any], title: str, body: str, url: str | None = None) -> list[str]:
    notify = settings.get("notify") or {}
    errors: list[str] = []
    sent = 0
    for name, conf in notify.items():
        if isinstance(conf, dict) and conf.get("enabled") and name in CHANNELS:
            try:
                send_channel(name, conf, title, body, url)
                sent += 1
            except Exception as exc:
                errors.append(redact_secrets(f"{name}: {exc}", settings))
    if sent == 0 and not errors:
        raise NotifyError("没有已启用的通知通道")
    return errors


TEST_TITLE = "官翻监听测试"
TEST_BODY = "通知通道已接通。"
TEST_URL = "https://www.apple.com.cn/shop/refurbished"
LINK_TEXT = "打开商品"


def _markdown_with_url(body: str, url: str | None) -> str:
    if not url:
        return body
    return f"{body}\n\n[{LINK_TEXT}]({url})"


def _html_with_url(body: str, url: str | None) -> str:
    text = escape(body).replace("\n", "<br>\n")
    if url:
        text += f'<br>\n<a href="{escape(url, quote=True)}">{LINK_TEXT}</a>'
    return text


def _plain_with_url(body: str, url: str | None) -> str:
    return body if not url else f"{body}\n\n{url}"


def _email_message(
    title: str,
    body: str,
    url: str | None,
    *,
    from_addr: str,
    to_addr: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(_plain_with_url(body, url))
    if url:
        msg.add_alternative(_html_with_url(body, url), subtype="html")
    return msg


def send_test(settings: dict[str, Any], channel: str | None = None) -> list[str]:
    name = str(channel or "").strip()
    if not name:
        return send_all(settings, TEST_TITLE, TEST_BODY, TEST_URL)
    if name not in CHANNELS:
        raise NotifyError(f"未知通道 {name}")
    conf = ((settings.get("notify") or {}).get(name) or {})
    try:
        send_channel(name, conf, TEST_TITLE, TEST_BODY, TEST_URL)
    except NotifyError as exc:
        raise NotifyError(redact_secrets(str(exc), settings)) from None
    return []


def send_channel(name: str, conf: dict, title: str, body: str, url: str | None) -> None:
    handler = CHANNELS.get(name)
    if handler is None:
        raise NotifyError(f"未知通道 {name}")
    handler(conf, title, body, url)


def _int_field(payload: dict[str, Any], key: str) -> int | None:
    raw = payload.get(key)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _fail_channel(name: str, payload: dict[str, Any]) -> None:
    for key in ("message", "msg", "errmsg", "description", "error"):
        value = payload.get(key)
        if value:
            raise NotifyError(f"{name}: {str(value).strip()}")
    raise NotifyError(f"{name}: 发送失败")


def _expect(name: str, response: httpx.Response, ok: Callable[[dict[str, Any]], bool]) -> None:
    try:
        payload = response.json()
    except Exception as exc:
        raise NotifyError(f"{name}: 响应无法解析") from exc
    if not isinstance(payload, dict) or not ok(payload):
        if isinstance(payload, dict):
            _fail_channel(name, payload)
        raise NotifyError(f"{name}: 响应无法解析")


def _http(method: str, url: str, **kwargs: Any) -> httpx.Response:
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        if isinstance(exc, httpx.HTTPStatusError):
            raise NotifyError(f"HTTP {exc.response.status_code}") from None
        raise NotifyError(f"网络错误: {type(exc).__name__}") from None
    if response.status_code >= 400:
        raise NotifyError(f"HTTP {response.status_code}")
    return response


def _post_json(url: str, payload: dict) -> httpx.Response:
    return _http("POST", url, json=payload)


def _post_form(url: str, payload: dict) -> httpx.Response:
    return _http("POST", url, data=payload)


def _bark(conf: dict, title: str, body: str, url: str | None) -> None:
    base = (conf.get("url") or "").rstrip("/")
    if not base:
        raise NotifyError("Bark URL 为空")
    payload: dict[str, Any] = {"title": title, "body": body, "group": "官翻监听"}
    if url:
        payload["url"] = url
    response = _post_json(base, payload)
    _expect("Bark", response, lambda data: _int_field(data, "code") == 200)


def _serverchan(conf: dict, title: str, body: str, url: str | None) -> None:
    sendkey = conf.get("sendkey") or ""
    if not sendkey:
        raise NotifyError("Server酱 sendkey 为空")
    response = _post_form(
        f"https://sctapi.ftqq.com/{sendkey}.send",
        {"title": title, "desp": _markdown_with_url(body, url)},
    )
    _expect("Server酱", response, lambda data: _int_field(data, "code") == 0)


def _pushplus(conf: dict, title: str, body: str, url: str | None) -> None:
    token = conf.get("token") or ""
    if not token:
        raise NotifyError("PushPlus token 为空")
    response = _post_json(
        "https://www.pushplus.plus/send",
        {
            "token": token,
            "title": title,
            "content": _html_with_url(body, url),
            "template": "html",
        },
    )
    _expect("PushPlus", response, lambda data: _int_field(data, "code") == 200)


def _feishu(conf: dict, title: str, body: str, url: str | None) -> None:
    webhook = conf.get("webhook") or ""
    if not webhook:
        raise NotifyError("飞书 webhook 为空")
    lines = [[{"tag": "text", "text": f"{line}\n"}] for line in str(body).splitlines()]
    if not lines:
        lines = [[{"tag": "text", "text": ""}]]
    if url:
        lines.append([{"tag": "a", "text": LINK_TEXT, "href": url}])
    payload: dict[str, Any] = {
        "msg_type": "post",
        "content": {"post": {"zh_cn": {"title": title, "content": lines}}},
    }
    secret = conf.get("secret") or ""
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = feishu_sign(secret, timestamp)
    response = _post_json(webhook, payload)
    _expect("飞书", response, lambda data: _int_field(data, "code") == 0)


def _dingtalk(conf: dict, title: str, body: str, url: str | None) -> None:
    webhook = conf.get("webhook") or ""
    if not webhook:
        raise NotifyError("钉钉 webhook 为空")
    text = f"### {title}\n\n{body}"
    if url:
        text = _markdown_with_url(text, url)
    secret = conf.get("secret") or ""
    target = webhook
    if secret:
        timestamp = str(int(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        sign = quote(base64.b64encode(digest).decode("ascii"), safe="")
        sep = "&" if "?" in webhook else "?"
        target = f"{webhook}{sep}timestamp={timestamp}&sign={sign}"
    response = _post_json(target, {"msgtype": "markdown", "markdown": {"title": title, "text": text}})
    _expect("钉钉", response, lambda data: _int_field(data, "errcode") == 0)


def _telegram(conf: dict, title: str, body: str, url: str | None) -> None:
    token = conf.get("bot_token") or ""
    chat_id = conf.get("chat_id") or ""
    if not token or not chat_id:
        raise NotifyError("Telegram bot_token 或 chat_id 为空")
    text = f"{escape(title)}\n{escape(body)}"
    if url:
        text += f'\n<a href="{escape(url, quote=True)}">{LINK_TEXT}</a>'
    api = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False,
    }
    if url:
        payload["parse_mode"] = "HTML"
    response = _post_json(api, payload)
    _expect("Telegram", response, lambda data: data.get("ok") is True)


def _email(conf: dict, title: str, body: str, url: str | None) -> None:
    host = conf.get("smtp_host") or ""
    username = conf.get("username") or ""
    password = conf.get("password") or ""
    to_addr = conf.get("to") or username
    if not host or not username or not password or not to_addr:
        raise NotifyError("邮件 SMTP 配置不完整")
    port = int(conf.get("smtp_port") or 465)
    msg = _email_message(title, body, url, from_addr=username, to_addr=to_addr)
    use_tls = bool(conf.get("use_tls", True))
    try:
        if use_tls and port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
                smtp.login(username, password)
                smtp.send_message(msg)
            return
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)
    except Exception as exc:
        raise NotifyError(f"邮件: {type(exc).__name__}") from None


def feishu_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


CHANNELS = {
    "bark": _bark,
    "serverchan": _serverchan,
    "pushplus": _pushplus,
    "feishu": _feishu,
    "dingtalk": _dingtalk,
    "telegram": _telegram,
    "email": _email,
}
