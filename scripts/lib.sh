# shellcheck shell=bash
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARW_BIN="${ROOT}/.venv/bin/apple-refurb-watch"

require_venv() {
  if [[ ! -x "$ARW_BIN" ]]; then
    echo "尚未安装虚拟环境。请先运行: ${ROOT}/scripts/setup.sh" >&2
    exit 1
  fi
}

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    echo "未找到 docker compose / docker-compose" >&2
    exit 1
  fi
}
