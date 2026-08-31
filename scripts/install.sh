#!/usr/bin/env bash
set -euo pipefail

# 把命令行包装到 ~/.local/bin。在解压后的 apple-refurb-watch 目录里运行：
#   ./install.sh
# 或：
#   ./install.sh /path/to/apple-refurb-watch

PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
SHARE_DIR="$PREFIX/share/apple-refurb-watch"

if [[ $# -gt 0 ]]; then
  SRC=$1
else
  SRC=$(cd "$(dirname "$0")" && pwd)
fi

if [[ -x "$SRC/apple-refurb-watch" ]]; then
  ROOT=$SRC
elif [[ -x "$SRC/apple-refurb-watch/apple-refurb-watch" ]]; then
  ROOT=$SRC/apple-refurb-watch
else
  echo "找不到 apple-refurb-watch 可执行文件。请在解压后的目录里运行。" >&2
  exit 1
fi

mkdir -p "$BIN_DIR" "$SHARE_DIR"
rm -rf "$SHARE_DIR"
mkdir -p "$SHARE_DIR"
cp -a "$ROOT"/. "$SHARE_DIR/"
chmod +x "$SHARE_DIR/apple-refurb-watch"
ln -sfn "$SHARE_DIR/apple-refurb-watch" "$BIN_DIR/apple-refurb-watch"
echo "已安装到 $BIN_DIR/apple-refurb-watch"
echo "运行: apple-refurb-watch serve"
echo "若命令找不到，把 $BIN_DIR 加进 PATH。"
