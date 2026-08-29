from __future__ import annotations

import base64
import hashlib
import hmac
import smtplib
import time
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote

import httpx


class NotifyError(RuntimeError):
    pass


def send_all(settings: dict[str, Any], title: str, body: str, url: str | None = None) -> list[str]:
    notify = settings.get("notify") or {}
    errors: list[str] = []
    sent = 0
    for name, conf in notify.items():
        if not isinstance(conf, dict) or not conf.get("enabled"):
            continue
        try:
            _dispatch(name, conf, title, body, url)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    if sent == 0 and not errors:
        raise NotifyError("没有已启用的通知通道")
    return errors


TEST_TITLE = "官翻监听测试"
TEST_BODY = "通知通道已接通。"
TEST_URL = "https://www.apple.com.cn/shop/refurbished"


def send_test(settings: dict[str, Any]) -> list[str]:
    return send_all(settings, TEST_TITLE, TEST_BODY, TEST_URL)


def _dispatch(name: str, conf: dict, title: str, body: str, url: str | None) -> None:
    if name == "bark":
        _bark(conf, title, body, url)
    elif name == "serverchan":
        _serverchan(conf, title, body, url)
    elif name == "pushplus":
        _pushplus(conf, title, body, url)
    elif name == "feishu":
        _feishu(conf, title, body, url)
    elif name == "dingtalk":
        _dingtalk(conf, title, body, url)
    elif name == "telegram":
        _telegram(conf, title, body, url)
    elif name == "email":
        _email(conf, title, body, url)
    else:
        raise NotifyError(f"未知通道 {name}")


def _bark(conf: dict, title: str, body: str, url: str | None) -> None:
    base = (conf.get("url") or "").rstrip("/")
    if not base:
        raise NotifyError("Bark URL 为空")
    payload = {"title": title, "body": body, "group": "官翻监听"}
    if url:
        payload["url"] = url
    if base.endswith("/push"):
        key = conf.get("key") or ""
        payload["device_key"] = key
        _post_json(base, payload)
        return
    # https://api.day.app/{key}
    target = f"{base}/{quote(title)}/{quote(body)}"
    params = {"group": "官翻监听"}
    if url:
        params["url"] = url
    with httpx.Client(timeout=15.0) as client:
        response = client.get(target, params=params)
        response.raise_for_status()


def _serverchan(conf: dict, title: str, body: str, url: str | None) -> None:
    sendkey = conf.get("sendkey") or ""
    if not sendkey:
        raise NotifyError("Server酱 sendkey 为空")
    desp = body if not url else f"{body}\n\n{url}"
    _post_form(f"https://sctapi.ftqq.com/{sendkey}.send", {"title": title, "desp": desp})


def _pushplus(conf: dict, title: str, body: str, url: str | None) -> None:
    token = conf.get("token") or ""
    if not token:
        raise NotifyError("PushPlus token 为空")
    content = body if not url else f"{body}\n{url}"
    _post_json("https://www.pushplus.plus/send", {"token": token, "title": title, "content": content})


def _feishu(conf: dict, title: str, body: str, url: str | None) -> None:
    webhook = conf.get("webhook") or ""
    if not webhook:
        raise NotifyError("飞书 webhook 为空")
    text = f"{title}\n{body}" + (f"\n{url}" if url else "")
    payload: dict[str, Any] = {"msg_type": "text", "content": {"text": text}}
    secret = conf.get("secret") or ""
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = feishu_sign(secret, timestamp)
    _post_json(webhook, payload)


def _dingtalk(conf: dict, title: str, body: str, url: str | None) -> None:
    webhook = conf.get("webhook") or ""
    if not webhook:
        raise NotifyError("钉钉 webhook 为空")
    text = f"{title}\n{body}" + (f"\n{url}" if url else "")
    secret = conf.get("secret") or ""
    target = webhook
    if secret:
        timestamp = str(int(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        sign = quote(base64.b64encode(digest).decode("ascii"), safe="")
        sep = "&" if "?" in webhook else "?"
        target = f"{webhook}{sep}timestamp={timestamp}&sign={sign}"
    _post_json(target, {"msgtype": "text", "text": {"content": text}})


def _telegram(conf: dict, title: str, body: str, url: str | None) -> None:
    token = conf.get("bot_token") or ""
    chat_id = conf.get("chat_id") or ""
    if not token or not chat_id:
        raise NotifyError("Telegram bot_token 或 chat_id 为空")
    text = f"{title}\n{body}" + (f"\n{url}" if url else "")
    api = f"https://api.telegram.org/bot{token}/sendMessage"
    _post_json(api, {"chat_id": chat_id, "text": text, "disable_web_page_preview": False})


def _email(conf: dict, title: str, body: str, url: str | None) -> None:
    host = conf.get("smtp_host") or ""
    username = conf.get("username") or ""
    password = conf.get("password") or ""
    to_addr = conf.get("to") or username
    if not host or not username or not password or not to_addr:
        raise NotifyError("邮件 SMTP 配置不完整")
    port = int(conf.get("smtp_port") or 465)
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = username
    msg["To"] = to_addr
    msg.set_content(body + (f"\n\n{url}" if url else ""))
    use_tls = bool(conf.get("use_tls", True))
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


def feishu_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _post_json(url: str, payload: dict) -> None:
    with httpx.Client(timeout=15.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()


def _post_form(url: str, payload: dict) -> None:
    with httpx.Client(timeout=15.0) as client:
        response = client.post(url, data=payload)
        response.raise_for_status()
