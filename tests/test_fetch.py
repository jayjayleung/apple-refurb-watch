import httpx
import pytest

from apple_refurb_watch.fetch import FetchError, fetch_html


def test_fetch_html_breaks_cookie_redirect_loop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "geo=" in request.headers.get("cookie", ""):
            return httpx.Response(200, text="<html>ok</html>")
        return httpx.Response(
            302,
            headers={
                "Location": str(request.url),
                "Set-Cookie": "geo=cn; Path=/",
            },
        )

    html = fetch_html(
        "https://www.apple.com.cn/shop/refurbished/mac/macbook-pro",
        retries=1,
        transport=httpx.MockTransport(handler),
    )
    assert html == "<html>ok</html>"


def test_fetch_html_rejects_offsite_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://evil.example/x"})

    with pytest.raises(FetchError, match="非苹果域名"):
        fetch_html(
            "https://www.apple.com.cn/shop/refurbished/mac/macbook-pro",
            retries=1,
            transport=httpx.MockTransport(handler),
        )
