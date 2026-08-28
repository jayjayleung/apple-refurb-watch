FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APPLE_REFURB_WATCH_HOME=/data

LABEL org.opencontainers.image.source="https://github.com/jayjayleung/apple-refurb-watch" \
      org.opencontainers.image.description="监听苹果中国认证翻新上新"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8765
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4).read()"

ENTRYPOINT ["apple-refurb-watch"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765"]
