FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /bin/uv

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APPLE_REFURB_WATCH_HOME=/data \
    PATH="/app/.venv/bin:${PATH}"

LABEL org.opencontainers.image.source="https://github.com/jayjayleung/apple-refurb-watch" \
      org.opencontainers.image.description="监听苹果中国认证翻新上新"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 1000 --create-home app \
    && mkdir -p /data \
    && chown app:app /data

COPY pyproject.toml README.md uv.lock /app/
RUN uv sync --locked --no-dev --no-install-project

COPY src /app/src
RUN uv sync --locked --no-dev \
    && chown -R app:app /app

USER app

EXPOSE 8765
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4).read()"

ENTRYPOINT ["apple-refurb-watch"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765"]
