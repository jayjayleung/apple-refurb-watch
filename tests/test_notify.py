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
    send_all,
    send_test,
)


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
def test_bark_get_and_push_payloads() -> None:
    get_route = respx.get("https://api.day.app/key/t/b").mock(return_value=httpx.Response(200))
    errors = send_all(
        {"notify": {"bark": {"enabled": True, "url": "https://api.day.app/key"}}},
        "t",
        "b",
        "https://www.apple.com.cn/x",
    )
    assert errors == []
    assert get_route.called
    params = dict(get_route.calls[0].request.url.params)
    assert params["group"] == "官翻监听"
    assert params["url"] == "https://www.apple.com.cn/x"

    push_route = respx.post("https://api.day.app/push").mock(return_value=httpx.Response(200))
    errors = send_all(
        {"notify": {"bark": {"enabled": True, "url": "https://api.day.app/push", "key": "abc"}}},
        "t",
        "b",
        "https://www.apple.com.cn/x",
    )
    assert errors == []
    payload = json.loads(push_route.calls[0].request.content)
    assert payload == {
        "title": "t",
        "body": "b",
        "group": "官翻监听",
        "url": "https://www.apple.com.cn/x",
        "device_key": "abc",
    }


@respx.mock
def test_serverchan_pushplus_telegram_bodies() -> None:
    sct = respx.post("https://sctapi.ftqq.com/sk.send").mock(return_value=httpx.Response(200))
    plus = respx.post("https://www.pushplus.plus/send").mock(return_value=httpx.Response(200))
    tg = respx.post("https://api.telegram.org/bot123:ABC/sendMessage").mock(return_value=httpx.Response(200))
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
    assert "https://www.apple.com.cn/shop/refurbished" in sct_body["desp"]
    plus_body = json.loads(plus.calls[0].request.content)
    assert plus_body["token"] == "pt"
    assert plus_body["title"] == "标题"
    assert plus_body["content"].startswith("正文")
    tg_body = json.loads(tg.calls[0].request.content)
    assert tg_body["chat_id"] == "99"
    assert tg_body["text"].startswith("标题\n正文")


@respx.mock
def test_feishu_and_dingtalk_text_payloads() -> None:
    feishu = respx.post("https://open.feishu.cn/hook").mock(return_value=httpx.Response(200))
    ding = respx.post(url__startswith="https://oapi.dingtalk.com/robot/send").mock(
        return_value=httpx.Response(200)
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
    assert feishu_body["msg_type"] == "text"
    assert "标题" in feishu_body["content"]["text"]
    assert "https://example.test" in feishu_body["content"]["text"]
    ding_body = json.loads(ding.calls[0].request.content)
    assert ding_body["msgtype"] == "text"
    assert "正文" in ding_body["text"]["content"]
    ding_url = str(ding.calls[0].request.url)
    assert "timestamp=" in ding_url
    assert "sign=" in ding_url


@respx.mock
def test_send_test_uses_fixed_copy() -> None:
    route = respx.get(url__regex=r"https://api\.day\.app/.*").mock(return_value=httpx.Response(200))
    errors = send_test({"notify": {"bark": {"enabled": True, "url": "https://api.day.app/key"}}})
    assert errors == []
    url = str(route.calls[0].request.url)
    assert quote(TEST_TITLE) in url
    assert quote(TEST_BODY) in url
    params = dict(route.calls[0].request.url.params)
    assert params["url"] == TEST_URL


@respx.mock
def test_send_test_one_channel_ignores_enabled() -> None:
    bark = respx.get(url__regex=r"https://api\.day\.app/.*").mock(return_value=httpx.Response(200))
    feishu = respx.post("https://open.feishu.cn/hook").mock(return_value=httpx.Response(200))
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
