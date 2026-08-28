#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "需要 Python 3.11+，当前找不到 ${PYTHON}" >&2
  exit 1
fi

"$PYTHON" -m venv .venv
# shellcheck disable=SC1091
source "${ROOT}/.venv/bin/activate"
python -m pip install --upgrade pip
pip install -e ".[dev]"

echo
echo "安装完成。"
echo "  启动:  ${ROOT}/scripts/serve.sh"
echo "  后台:  ${ROOT}/scripts/serve.sh --detach"
echo "  停止:  ${ROOT}/scripts/stop.sh"
