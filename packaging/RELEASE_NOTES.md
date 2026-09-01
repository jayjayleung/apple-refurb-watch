# 苹果官翻监听 0.3.1

这是 0.3.0 的维护版本，修复本地 CLI 连接服务时的认证令牌处理。

## 修复

- **本地 CLI 自动认证**：本地连接会读取本地 SQLite 中的 `access_token`，避免服务监听在 `0.0.0.0` 时状态检查误报 401。
- **令牌隔离**：本地令牌不会发送到远程服务，已保存的远程令牌也不会发送到显式指定的本地服务。
- **回归测试**：覆盖本地、远程、环境变量和显式地址等连接场景。

## 下载

目录版按系统解压即可，不必安装 Python；每个系统同时提供一个可直接运行的单文件版本。

- **Windows**：`apple-refurb-watch-windows-x86_64.zip`（需要 Edge WebView2，Win10/11 一般都有）
- **macOS Apple Silicon**：`apple-refurb-watch-macos-arm64.zip`
- **Linux / NAS**：`apple-refurb-watch-linux-x86_64.zip`

单文件版本的文件名分别为 `apple-refurb-watch-windows-x86_64.exe`、`apple-refurb-watch-macos-arm64` 和 `apple-refurb-watch-linux-x86_64`。它们可以直接复制后运行，不需要解压目录；首次启动会自动解压运行时文件。Linux/macOS 如果下载后没有执行权限，先运行 `chmod +x`。

Linux / NAS 解压后执行：

```bash
./apple-refurb-watch serve --host 0.0.0.0 --port 8765
```

后台运行可使用 `serve --detach`。升级时保留原数据目录即可，数据库 schema 无变化。
