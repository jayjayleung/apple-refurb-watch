# 苹果官翻监听 0.3.0

这是一次面向个人长期运行场景的架构升级。网页仍是主要配置入口，CLI 用于运维，桌面壳只负责窗口、托盘和系统通知；扫描、数据和通知由唯一的 `watchd` 服务统一管理。

## 主要变化

- **扫描生命周期可追踪**：引入 `scan_runs`、`observations` 和异步扫描资源。手动扫描返回运行 ID，可查询排队、运行、成功、部分成功和失败状态。
- **通知可靠投递**：事件先写入通知 outbox，再由独立投递器发送；支持租约、指数退避和幂等，进程重启或通道故障不会丢失待发送任务。
- **数据库升级到 schema v3**：旧库启动时自动迁移，升级前会保留备份；扫描失败不会误生成“售罄”事件。
- **运维工具补齐**：新增/完善 `backup`、`restore`、`doctor` 和 `config export/import`，用于迁移、升级和故障恢复。
- **远程服务边界明确**：本机桌面模式由本机 SQLite 持有权威数据；NAS/VPS 模式由服务端持有，远程客户端不复制可写数据库。
- **访问控制加强**：非本机监听需要认证；健康检查保留公开能力信息，业务接口继续要求口令。

## 下载

按系统解压即可，不必安装 Python。

- **Windows**：`apple-refurb-watch-windows-x86_64.zip`（需要 Edge WebView2，Win10/11 一般都有）
- **macOS Apple Silicon**：`apple-refurb-watch-macos-arm64.zip`
- **Linux / NAS**：`apple-refurb-watch-linux-x86_64.zip`

Linux / NAS 解压后执行：

```bash
./apple-refurb-watch serve --host 0.0.0.0 --port 8765
```

后台运行可使用 `serve --detach`。默认网页地址是 `http://127.0.0.1:8765`，实际端口以启动参数和设置为准。

## 升级前后

升级前建议先创建一份独立备份：

```bash
apple-refurb-watch backup --json
```

启动新版本时会自动执行数据库迁移。若迁移或启动失败，先停止服务，再用 `restore` 恢复备份并运行：

```bash
apple-refurb-watch doctor --json
```

通知密钥不会在配置导出中回显；导入配置默认保留本地已保存的密钥。

## Docker / NAS

CI 不发布 Docker 镜像。NAS 上从仓库固定版本构建：

```bash
cp .env.example .env
docker compose up -d --build
```

同一数据目录不要同时安装本机 `service`。容器使用 compose 的 `restart: unless-stopped`。

## 客户端兼容

桌面、CLI 和 TUI 都通过服务端 API 工作。连接远程服务时，客户端不启动本地扫描器，也不写本地第二份数据库；若服务端 API 版本高于客户端，请先升级客户端。
