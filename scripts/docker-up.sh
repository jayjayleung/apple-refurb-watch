#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 docker（或兼容的 podman）" >&2
  exit 1
fi

mkdir -p "${ROOT}/data"
if [[ ! -f "${ROOT}/.env" && -f "${ROOT}/.env.example" ]]; then
  cp "${ROOT}/.env.example" "${ROOT}/.env"
  echo "已复制 .env.example -> .env"
fi

if [[ -f "${ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "${ROOT}/.env"
  set +a
fi

compose up -d --build

echo
echo "容器已启动。"
echo "  网页:  http://${ARW_BIND:-127.0.0.1}:${ARW_PORT:-8765}"
echo "  日志:  docker logs -f apple-refurb-watch"
echo "  停止:  ${ROOT}/scripts/docker-down.sh"
echo "  数据:  ${ROOT}/data"
