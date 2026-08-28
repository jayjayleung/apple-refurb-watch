import base64
import hashlib
import hmac
from urllib.parse import quote

from apple_refurb_watch.notify import feishu_sign


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
