import base64
import hashlib
import hmac
import json
from urllib.parse import quote

import httpx
import respx

from apple_refurb_watch.notify import (
    NotifyError,
    TEST_BODY,
    TEST_TITLE,
    TEST_URL,
    feishu_sign,
    redact_secrets,
    send_all,
    send_test,
)


def _ok(channel: str) -> httpx.Response:
    bodies = {
        "bark": {"code": 200, "message": "success"},
        "serverchan": {"code": 0, "message": "ok"},
        "pushplus": {"code": 200, "msg": "请求成功"},
        "telegram": {"ok": True, "result": {}},
        "feishu": {"code": 0, "msg": "success"},
        "dingtalk": {"errcode": 0, "errmsg": "ok"},
    }
    return httpx.Response(200, json=bodies[channel])


def test_feishu_sign_matches_official() -> None:
    secret = "test-secret"
    timestamp = "1710000000"
    expected = base64.b64encode(
        hmac.new(f"{timestamp}\n{secret}".encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    assert feishu_sign(secret, timestamp) == expected


def test_dingtalk_sign_encodes_slash() -> None:
    digest = hmac.new(b"secret", b"1\nsecret", digestmod=hashlib.sha256).digest()
    raw = base64.b64encode(digest).decode("ascii")
    encoded = quote(raw, safe="")
    if "/" in raw:
        assert "%2F" in encoded
        assert "/" not in encoded


@respx.mock
def test_bark_posts_json_body() -> None:
    route = respx.post("https://api.day.app/key").mock(return_value=_ok("bark"))
    errors = send_all(
        {"notify": {"bark": {"enabled": True, "url": "https://api.day.app/key"}}},
        "t",
        "b / extra",
        "https://www.apple.com.cn/x",
    )
    assert errors == []
    assert route.called
    payload = json.loads(route.calls[0].request.content)
    assert payload == {
        "title": "t",
        "body": "b / extra",
        "group": "官翻监听",
        "url": "https://www.apple.com.cn/x",
    }


@respx.mock
def test_serverchan_pushplus_telegram_bodies() -> None:
    sct = respx.post("https://sctapi.ftqq.com/sk.send").mock(return_value=_ok("serverchan"))
    plus = respx.post("https://www.pushplus.plus/send").mock(return_value=_ok("pushplus"))
    tg = respx.post("https://api.telegram.org/bot123:ABC/sendMessage").mock(return_value=_ok("telegram"))
    errors = send_all(
        {
            "notify": {
                "serverchan": {"enabled": True, "sendkey": "sk"},
                "pushplus": {"enabled": True, "token": "pt"},
                "telegram": {"enabled": True, "bot_token": "123:ABC", "chat_id": "99"},
            }
        },
        "标题",
        "正文",
        "https://www.apple.com.cn/shop/refurbished",
    )
    assert errors == []
    sct_body = dict(httpx.QueryParams(sct.calls[0].request.content.decode()))
    assert sct_body["title"] == "标题"
    assert "正文" in sct_body["desp"]
    assert "[打开商品](https://www.apple.com.cn/shop/refurbished)" in sct_body["desp"]
    plus_body = json.loads(plus.calls[0].request.content)
    assert plus_body["token"] == "pt"
    assert plus_body["title"] == "标题"
    assert plus_body["template"] == "html"
    assert plus_body["content"].startswith("正文")
    assert '<a href="https://www.apple.com.cn/shop/refurbished">打开商品</a>' in plus_body["content"]
    tg_body = json.loads(tg.calls[0].request.content)
    assert tg_body["chat_id"] == "99"
    assert tg_body["parse_mode"] == "HTML"
    assert tg_body["text"].startswith("标题\n正文")
    assert '<a href="https://www.apple.com.cn/shop/refurbished">打开商品</a>' in tg_body["text"]


@respx.mock
def test_feishu_and_dingtalk_text_payloads() -> None:
    feishu = respx.post("https://open.feishu.cn/hook").mock(return_value=_ok("feishu"))
    ding = respx.post(url__startswith="https://oapi.dingtalk.com/robot/send").mock(
        return_value=_ok("dingtalk")
    )
    errors = send_all(
        {
            "notify": {
                "feishu": {"enabled": True, "webhook": "https://open.feishu.cn/hook"},
                "dingtalk": {
                    "enabled": True,
                    "webhook": "https://oapi.dingtalk.com/robot/send?access_token=x",
                    "secret": "sec",
                },
            }
        },
        "标题",
        "正文",
        "https://example.test",
    )
    assert errors == []
    feishu_body = json.loads(feishu.calls[0].request.content)
    assert feishu_body["msg_type"] == "post"
    post = feishu_body["content"]["post"]["zh_cn"]
    assert post["title"] == "标题"
    assert any(span.get("href") == "https://example.test" for line in post["content"] for span in line)
    ding_body = json.loads(ding.calls[0].request.content)
    assert ding_body["msgtype"] == "markdown"
    assert "正文" in ding_body["markdown"]["text"]
    assert "[打开商品](https://example.test)" in ding_body["markdown"]["text"]
    ding_url = str(ding.calls[0].request.url)
    assert "timestamp=" in ding_url
    assert "sign=" in ding_url


@respx.mock
def test_send_test_uses_fixed_copy() -> None:
    route = respx.post("https://api.day.app/key").mock(return_value=_ok("bark"))
    errors = send_test({"notify": {"bark": {"enabled": True, "url": "https://api.day.app/key"}}})
    assert errors == []
    payload = json.loads(route.calls[0].request.content)
    assert payload["title"] == TEST_TITLE
    assert payload["body"] == TEST_BODY
    assert payload["url"] == TEST_URL


@respx.mock
def test_send_test_one_channel_ignores_enabled() -> None:
    bark = respx.post("https://api.day.app/key").mock(return_value=_ok("bark"))
    feishu = respx.post("https://open.feishu.cn/hook").mock(return_value=_ok("feishu"))
    settings = {
        "notify": {
            "bark": {"enabled": False, "url": "https://api.day.app/key"},
            "feishu": {"enabled": True, "webhook": "https://open.feishu.cn/hook"},
        }
    }
    errors = send_test(settings, channel="bark")
    assert errors == []
    assert bark.called
    assert not feishu.called


def test_send_test_unknown_channel() -> None:
    try:
        send_test({"notify": {}}, channel="nope")
    except NotifyError as exc:
        assert "未知通道" in str(exc)
    else:
        raise AssertionError("expected NotifyError")


def test_email_includes_html_hyperlink(monkeypatch) -> None:
    sent: list = []

    class FakeSMTP_SSL:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def login(self, *args) -> None:
            return None

        def send_message(self, msg) -> None:
            sent.append(msg)

    monkeypatch.setattr("apple_refurb_watch.notify.smtplib.SMTP_SSL", FakeSMTP_SSL)
    errors = send_all(
        {
            "notify": {
                "email": {
                    "enabled": True,
                    "smtp_host": "smtp.example.test",
                    "smtp_port": 465,
                    "username": "from@example.test",
                    "password": "secret",
                    "to": "to@example.test",
                    "use_tls": True,
                }
            }
        },
        "标题",
        "正文",
        "https://www.apple.com.cn/shop/product/G1MK7CH/A",
    )
    assert errors == []
    assert sent
    html = sent[0].get_body(preferencelist=("html",)).get_content()
    plain = sent[0].get_body(preferencelist=("plain",)).get_content()
    assert '<a href="https://www.apple.com.cn/shop/product/G1MK7CH/A">打开商品</a>' in html
    assert "https://www.apple.com.cn/shop/product/G1MK7CH/A" in plain


@respx.mock
def test_http_error_does_not_leak_token() -> None:
    settings = {
        "notify": {
            "telegram": {
                "enabled": True,
                "bot_token": "123456:SECRET-TOKEN",
                "chat_id": "1",
            }
        }
    }
    respx.post("https://api.telegram.org/bot123456:SECRET-TOKEN/sendMessage").mock(
        return_value=httpx.Response(401, text="unauthorized")
    )
    try:
        send_test(settings, channel="telegram")
    except NotifyError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected NotifyError")
    assert "SECRET-TOKEN" not in message
    assert "HTTP 401" in message
    errors = send_all(settings, "t", "b")
    assert errors
    assert "SECRET-TOKEN" not in errors[0]
    assert redact_secrets(
        "https://api.telegram.org/bot123456:SECRET-TOKEN/sendMessage",
        settings,
    ) == "https://api.telegram.org/bot***/sendMessage"


@respx.mock
def test_business_code_failure_is_not_success() -> None:
    respx.post("https://sctapi.ftqq.com/SCT_SECRET_KEY.send").mock(
        return_value=httpx.Response(200, json={"code": 40001, "message": "bad key"})
    )
    settings = {"notify": {"serverchan": {"enabled": True, "sendkey": "SCT_SECRET_KEY"}}}
    errors = send_all(settings, "t", "b")
    assert len(errors) == 1
    assert "SCT_SECRET_KEY" not in errors[0]
    assert "Server酱" in errors[0]
    respx.post("https://www.pushplus.plus/send").mock(
        return_value=httpx.Response(200, json={"code": 500, "msg": "token error"})
    )
    try:
        send_test({"notify": {"pushplus": {"token": "pt"}}}, channel="pushplus")
    except NotifyError as exc:
        assert "PushPlus" in str(exc)
        assert "token error" in str(exc)
    else:
        raise AssertionError("expected NotifyError")
