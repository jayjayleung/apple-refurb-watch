# Apple Refurb Watch

监听 [苹果中国认证翻新](https://www.apple.com.cn/shop/refurbished) 中你关心的配置，在上新或重新有货时发送通知。

[下载最新版本](https://github.com/jayjayleung/apple-refurb-watch/releases/latest)

当前源码版本：**0.3.15** · 需要 Python **3.11+**

> 本项目不是 Apple 官方产品，适合个人、自托管使用。请合理设置扫描间隔。

## 它能做什么

- 按 Mac、iPad、Apple Watch 等官网分类扫描当前在售商品。
- 按机型、芯片、尺寸、内存、容量、颜色、价格等条件创建监听规则。
- 支持条件规则和精确 SKU 两种模式。
- 首次扫描只建立库存基线，不会把已有商品全部推送一遍。
- 支持 Bark、Server酱、PushPlus、飞书、钉钉、Telegram 和邮件通知。
- 支持浏览器通知与桌面系统通知。
- 提供响应式 Web、桌面窗口、CLI 和可选 TUI；所有入口共用同一套 HTTP API。
- 可在本机运行，也可把服务放在 NAS/VPS 上，再由电脑或手机远程访问。
- 内置 SQLite 在线备份、恢复、配置迁移和健康诊断。

核心原则是：**一份数据、一个权威服务、多个操作入口**。扫描、SQLite 和服务端通知只运行一份，避免重复扫描与重复推送。

## 选择运行方式

| 场景 | 推荐方式 | 数据和扫描在哪里 |
| --- | --- | --- |
| Windows / macOS 日常使用 | 桌面版 | 当前电脑 |
| NAS / VPS 持续监听 | `serve` 无界面服务 | NAS / VPS |
| 手机或另一台电脑查看 | 浏览器或远程桌面客户端 | 远端服务 |
| 已有容器环境 | Docker Compose | 容器挂载的 `./data` |

默认网页地址是 `http://127.0.0.1:8765`。运行 `apple-refurb-watch home` 可查看当前数据目录。

## 快速开始

### Windows / macOS：桌面版

从 [Releases](https://github.com/jayjayleung/apple-refurb-watch/releases) 下载并解压对应目录版：

- Windows x86_64：`apple-refurb-watch-windows-x86_64.zip`
- macOS Apple Silicon：`apple-refurb-watch-macos-arm64.zip`

双击 `apple-refurb-watch`，Windows 文件名为 `apple-refurb-watch.exe`。目录版不需要安装 Python。

首次启动会打开窗口并创建托盘图标：

- 关闭窗口默认只隐藏到托盘，监听继续运行。
- 从托盘点“退出”才会停止本机桌面和内置服务。
- 再次双击会唤起已有窗口，不会启动第二份扫描。
- 不希望关窗后继续运行，可在设置中关闭“关闭窗口到托盘”。

Windows 需要 Edge WebView2，Windows 10/11 通常已自带。Releases 暂不提供 Intel Mac 安装包；Intel Mac 请按“开发”章节从源码运行。

每个平台还提供单文件可执行版本。它便于复制，但首次启动更慢，也更容易触发杀毒软件误报；日常使用优先选择 zip 目录版。

### Linux / NAS / VPS：网页服务

下载 `apple-refurb-watch-linux-x86_64.zip`，解压后运行：

```bash
chmod +x ./apple-refurb-watch
./apple-refurb-watch serve
```

服务默认只监听本机 `127.0.0.1:8765`。前台运行时按 `Ctrl+C` 停止；只想临时放到后台可用：

```bash
./apple-refurb-watch serve --detach
```

可选安装到 `~/.local/bin`：

```bash
./install.sh
```

需要登录后自动启动网页服务：

```bash
apple-refurb-watch service install --serve
apple-refurb-watch service start
```

如果 NAS 没有本地浏览器，建议先用 SSH 端口转发完成首次配置：

```bash
ssh -L 8765:127.0.0.1:8765 user@你的服务器
```

然后在本机打开 `http://127.0.0.1:8765`。需要其它设备直接访问时，到“设置 → 服务”打开“允许远程访问”，保存生成的访问口令，再重启服务。

Linux 发布包面向 `serve` 和 CLI，不包含桌面依赖。需要 Linux 桌面窗口时请从源码安装 `desktop` extra。

### 连接已经运行的远程服务

先在服务器设置中打开远程访问并保存口令，再在客户端执行：

```bash
apple-refurb-watch connect http://192.168.1.8:8765 --token 你的口令
```

之后桌面、CLI 和 TUI 都使用远端数据；本机不会再扫描，也不会写第二份业务数据库。

改回本机：

```bash
apple-refurb-watch disconnect
```

桌面版也可以在“设置 → 这台电脑”或托盘菜单中切换服务器。退出远程桌面客户端不会停止 NAS/VPS 上的服务。

公网访问请使用 HTTPS，并在前面放 Caddy、nginx 或其它反向代理。内网可以使用 HTTP；公网强制使用 HTTP 时才加 `--insecure`，不推荐：

```bash
apple-refurb-watch connect https://example.com --token 你的口令
apple-refurb-watch connect http://example.com --token 你的口令 --insecure
```

访问口令请单独传入，不要拼进 URL。

### Docker Compose

仓库提供 Dockerfile 和 Compose 配置，但不发布预构建镜像。数据保存在宿主机 `./data`，容器内路径固定为 `/data`。

当前安全策略会拒绝“监听 `0.0.0.0` 但没有访问口令”的服务。全新的 `./data` 需要先初始化一次：

```bash
mkdir -p data
APPLE_REFURB_WATCH_HOME="$PWD/data" apple-refurb-watch serve
```

在本机打开设置，启用远程访问并保存口令，然后停止这个临时服务。再启动容器：

```bash
cp .env.example .env
docker compose up -d --build
```

Compose 默认只把端口绑定到宿主机 `127.0.0.1`。需要其它设备访问时，把 `.env` 中的 `ARW_BIND` 改为 `0.0.0.0`；应用内的远程访问和口令仍必须保持开启。

不要在同一个数据目录上同时运行 Docker 和本机 `service`。容器重启由 Compose 的 `restart: unless-stopped` 管理。

## 第一次使用

打开网页后，按下面顺序配置：

1. 点击“立即扫描”，获取当前在售商品并建立基线。
2. 使用官网同款筛选条件查找目标配置。
3. 在商品卡片上选择“按配置听”或“精确 SKU”，也可以进入“监听”页面手动建规则。
4. 到“设置”启用通知通道并发送测试通知。
5. 保持“定时扫描”开启；需要暂停时可从顶栏或托盘停止监听。

首次扫描不会通知当前库存。只有后续出现的新商品，或曾经售罄后重新出现的商品，才会触发库存通知。

默认每 5 分钟扫描一次，最小间隔为 60 秒。详情页只会在规则需要、而商品列表又缺少内存或容量信息时补抓，并自动加入请求间隔。

## 通知从哪里发出

| 通知类型 | 发送位置 | 是否依赖页面保持打开 |
| --- | --- | --- |
| Bark、Server酱、PushPlus、飞书、钉钉、Telegram、邮件 | 扫描所在的权威服务 | 否 |
| 浏览器通知 | 当前浏览器 | 是 |
| 桌面系统通知 | 当前桌面客户端 | 窗口可关闭，但托盘需运行 |

服务端通知可以同时启用多个通道。通知密钥和 Webhook 只在网页设置中填写；CLI 的 `settings set` 不修改密钥。

“电脑通知”属于当前客户端：

- 浏览器需要在用户操作后授予通知权限，页面关闭后不再弹出。
- 桌面版使用系统通知，关闭窗口到托盘后仍可接收。
- 桌面连接远端时，通知显示在当前电脑，不会跑到 NAS 上弹窗。

## 远程访问与安全

- 默认绑定 `127.0.0.1`，不会自动暴露到局域网。
- 绑定到非回环地址时必须配置访问口令，否则服务拒绝启动。
- Web 登录支持访问口令；CLI 和桌面客户端使用同一个口令。
- 公网部署应使用 HTTPS，优先考虑 Tailscale 等私网方案。
- 不要把口令、Webhook 或邮件密码提交到仓库。
- `config export` 默认排除全部密钥；只有明确使用 `--include-secrets` 才会导出。

连接配置也可以由环境变量提供，它们优先于本地保存的连接：

```bash
export APPLE_REFURB_WATCH_URL="https://example.com"
export APPLE_REFURB_WATCH_TOKEN="你的口令"
```

设置这些环境变量后，桌面界面不能修改连接，需先移除环境变量。

## 常用命令

查看完整帮助：

```bash
apple-refurb-watch --help
apple-refurb-watch <命令> --help
```

服务与状态：

```bash
apple-refurb-watch version
apple-refurb-watch home
apple-refurb-watch serve
apple-refurb-watch serve --detach
apple-refurb-watch status
apple-refurb-watch stop
```

扫描与在售：

```bash
apple-refurb-watch scan
apple-refurb-watch list --q "MacBook Pro"
apple-refurb-watch list --listing mac --sort -price
apple-refurb-watch list --max-price 18000 --min-ram 24 --min-storage 512
apple-refurb-watch list --json
```

监听规则：

```bash
apple-refurb-watch watch add \
  --name "14 英寸 MacBook Pro" \
  --listing mac \
  --dim chip=m5_pro \
  --dim dimensionScreensize=14inch \
  --min-ram 24 \
  --max-price 18000

apple-refurb-watch watch add --name "指定 SKU" --mode sku --sku MLXX3CH/A
apple-refurb-watch watch ls
apple-refurb-watch watch pause 1
apple-refurb-watch watch resume 1
apple-refurb-watch watch rm 1
```

动态、设置与通知：

```bash
apple-refurb-watch events
apple-refurb-watch events --limit 100 --json
apple-refurb-watch events clear

apple-refurb-watch settings get
apple-refurb-watch settings set --listings mac,ipad --interval 300 --listen
apple-refurb-watch settings sync-catalog
apple-refurb-watch notify-test
```

`scan --local` 和 `list --local` 会直接使用本机库。已经连接远端时不要使用 `--local`；CLI 会拒绝这种容易操作错库的组合。

## 备份、恢复与迁移

这些命令只操作权威服务所在机器的本地数据库。客户端已经连接远端时，需登录服务器执行。

```bash
# 创建 SQLite 在线备份并校验完整性；默认最多保留 8 份自动备份
apple-refurb-watch backup
apple-refurb-watch backup --output /path/to/backups --keep 14

# 检查数据库、监听安全、daemon 和未完成扫描
apple-refurb-watch doctor --human

# 导出规则和非敏感设置
apple-refurb-watch config export config.json

# 导入前必须停止本机 daemon；默认保留本机密钥
apple-refurb-watch stop
apple-refurb-watch config import config.json

# 恢复前也必须停止 daemon；恢复时会保留恢复前副本
apple-refurb-watch restore /path/to/app.db
```

确实需要连同口令和通知密钥迁移时：

```bash
apple-refurb-watch config export config-with-secrets.json --include-secrets
apple-refurb-watch config import config-with-secrets.json --include-secrets
```

含密钥的导出文件应按凭据管理，不要上传或提交到 Git。

## 数据目录与升级

查看实际数据目录：

```bash
apple-refurb-watch home
```

常用环境变量：

| 变量 | 用途 |
| --- | --- |
| `APPLE_REFURB_WATCH_HOME` | 覆盖数据目录 |
| `APPLE_REFURB_WATCH_LOG` | 覆盖日志目录 |
| `APPLE_REFURB_WATCH_URL` | 指定远程服务地址 |
| `APPLE_REFURB_WATCH_TOKEN` | 指定远程访问口令 |

主要数据都保存在数据目录中的 `app.db`。筛选词条可由内置目录、官网同步文件和用户覆盖文件合并：

- `filter_catalog.live.json`：扫描或“从官网同步筛选词条”生成。
- `filter_catalog.json`：用户自定义覆盖或增量内容，按修改时间热加载。

升级建议：

1. 在权威服务机器上执行 `apple-refurb-watch backup`。
2. 停止桌面、服务或容器。
3. 替换程序文件，保留原数据目录。
4. 重新启动并执行 `apple-refurb-watch doctor --human`。

数据库跨版本迁移会在数据目录中自动创建 `app.db.bak-vN`。迁移失败时会尝试恢复备份，并在日志中写出备份路径。

桌面端和服务端版本分别显示在设置页；发现新版本时，“设置”入口会出现提示。远程使用时应同时留意客户端与服务器版本。

## 开机自启

先安装任务，再启动：

```bash
apple-refurb-watch service install --serve
apple-refurb-watch service start
apple-refurb-watch service status
apple-refurb-watch service restart
apple-refurb-watch service stop
apple-refurb-watch service uninstall
```

| 使用方式 | 安装参数 | 登录后启动内容 |
| --- | --- | --- |
| Windows / macOS 桌面安装包 | `service install` 或 `--tray` | 托盘桌面 |
| Linux / NAS / VPS | `service install --serve` | 网页服务 |
| Linux 源码桌面 | `service install --tray` | 托盘桌面 |
| Docker | 不安装本机 service | 由 Compose 重启策略管理 |

Windows/macOS 冻结安装包中的 `service install` 默认安装托盘模式，其它环境默认安装 `serve`。`--serve` 和 `--tray` 不能同时使用。

`apple-refurb-watch stop` 停止当前 daemon；`service stop` 停止开机任务；`service uninstall` 才会删除开机任务。

## TUI

TUI 面向 SSH 和纯终端环境，提供在售查询、分类与排序、基础规则增删、扫描状态、监听开关和最近动态。网络请求都在后台执行，远程服务响应慢时仍可切换页面、查看帮助或退出；操作失败会保留原表格并恢复设置开关。

TUI 使用当前已保存的连接，不能在界面内填写服务器地址。连接远端前先运行 `apple-refurb-watch connect ...`。

手动扫描会提交后台任务并显示等待、运行和最终状态。新建规则支持分类、条件/精确 SKU、维度、最低内存、最低容量和最高价，并在提交前校验输入。复杂筛选、通知密钥、托盘和电脑通知仍以 Web/桌面为主。

源码安装：

```bash
python -m uv sync --locked --extra tui
python -m apple_refurb_watch tui
```

常用快捷键：

- `1`–`4`：切换在售、监听、动态、设置。
- `/`：过滤在售；`f`：切换分类；`o`：切换价格排序。
- `s`：立即扫描；`r`：刷新当前页面；`?`：查看完整帮助。
- `w` / `k`：按选中商品创建条件规则 / 精确 SKU 规则。
- `n`：新建规则；`e`：暂停或启用；`d`：删除。

在 80×24 等窄终端中，TUI 会隐藏在售侧栏，所有核心操作仍可通过快捷键完成。

## 开发

```bash
git clone https://github.com/jayjayleung/apple-refurb-watch.git
cd apple-refurb-watch

./scripts/setup.sh
source .venv/bin/activate
./scripts/serve.sh
```

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\scripts\serve.ps1
```

`setup` 脚本会创建 `.venv`，安装锁定版本的 `uv`，再通过 `uv sync --locked --extra dev` 安装开发依赖。

运行测试：

```bash
pytest
# 或与 CI 一致
uv run python -m pytest --tb=short -q
```

可选依赖：

- `tui`：Textual 终端界面。
- `desktop`：pywebview 桌面窗口、pystray 托盘和系统通知。
- `all`：同时安装 TUI 与桌面依赖。
- `pack`：PyInstaller 打包工具。

Linux 源码桌面还需要 WebKitGTK。例如 Debian/Ubuntu：

```bash
sudo apt install gir1.2-webkit2-4.1 python3-gi
python -m uv sync --locked --extra desktop
apple-refurb-watch desktop
```

`desktop --probe` 只检查本机服务能否启动，不会打开窗口；日常使用直接运行 `desktop`。

## 打包与发布

本地构建当前系统的目录版：

```bash
python -m uv sync --locked --extra desktop --extra pack
python -m PyInstaller --noconfirm --clean \
  --distpath dist/onedir \
  --workpath build/onedir \
  packaging/apple-refurb-watch.spec
```

构建单文件版：

```bash
APPLE_REFURB_WATCH_BUILD=onefile \
python -m PyInstaller --noconfirm --clean \
  --distpath dist/onefile \
  --workpath build/onefile \
  packaging/apple-refurb-watch.spec
```

GitHub Actions 在 PR、`v*` 标签和手动触发时运行 Linux、Windows、macOS 测试。`v*` 标签通过后会生成：

- Linux x86_64：目录版 zip + 单文件可执行文件。
- Windows x86_64：目录版 zip + 单文件 `.exe`。
- macOS arm64：目录版 zip + 单文件可执行文件。
- `SHA256SUMS.txt`：全部产物校验值。

仓库目前不构建或推送 Docker 镜像。

## 架构

```text
浏览器 / 桌面 / CLI / TUI
            │
         HTTP API
            │
       权威后台服务
      ┌─────┼─────┐
    扫描器 SQLite 通知器
```

项目采用 FastAPI + Uvicorn、Jinja2 + HTMX、SQLite WAL 和 APScheduler。个人单用户规模下不引入 React/Vue、PostgreSQL、Redis、Celery、微服务或 Kubernetes。

健康检查端点：`GET /api/health`

## 礼貌抓取

默认扫描间隔为 5 分钟，并对详情请求加入延迟。请不要把间隔设置得过于频繁，也不要启动多个服务监听同一组规则。
