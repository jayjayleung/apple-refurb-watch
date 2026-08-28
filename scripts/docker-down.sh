#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 docker（或兼容的 podman）" >&2
  exit 1
fi

compose down
echo "容器已停止。数据仍保留在 ${ROOT}/data"
