# Apple Refurb Watch

监听 [苹果中国认证翻新](https://www.apple.com.cn/shop/refurbished) 中你关心的配置，在上新或重新有货时发送通知。

[下载最新版本](https://github.com/jayjayleung/apple-refurb-watch/releases/latest)

当前源码版本：**0.3.17** · 需要 Python **3.11+**

> 本项目不是 Apple 官方产品，适合个人、自托管使用。请合理设置扫描间隔。

## 它能做什么

- 按 Mac、iPad、Apple Watch 等官网分类扫描当前在售商品。
- 按机型、芯片、尺寸、内存、容量、颜色、价格等条件创建监听规则，也支持精确 SKU。
- 首次扫描只建立库存基线，不会把已有商品全部推送一遍。
- 支持 Bark、Server酱、PushPlus、飞书、钉钉、Telegram、邮件，以及浏览器 / 桌面通知。
- 提供网页、桌面窗口、CLI 和可选 TUI；扫描和通知只在一台权威服务上运行。
- 可在本机使用，也可放到 NAS / VPS，再由电脑或手机远程访问。

核心原则是：**一份数据、一个权威服务、多个操作入口**。不要同时开两份扫描。

## 安装

先选一种方式，只看对应小节。默认网页是 `http://127.0.0.1:8765`。日常请用 **zip 目录版**，不必安装 Python。

| 你的情况 | 用这个 |
| --- | --- |
| Windows 或 Apple Silicon Mac，自己用 | 下面「桌面安装包」 |
| NAS / Linux 服务器，一直跑 | 下面「Linux 安装包」 |
| 服务已经在跑，另一台电脑或手机来看 | 下面「连接远程服务」 |
| 已经有 Docker | 下面「Docker」 |
| 改代码、Intel Mac、Linux 桌面窗口 | 下面「从源码运行」 |

运行 `apple-refurb-watch home` 可查看当前数据目录。

### Windows / macOS：桌面安装包

1. 打开 [Releases](https://github.com/jayjayleung/apple-refurb-watch/releases/latest)，下载对应 zip 并解压：
   - Windows x86_64：`apple-refurb-watch-windows-x86_64.zip`
   - macOS Apple Silicon：`apple-refurb-watch-macos-arm64.zip`
2. 双击 `apple-refurb-watch`。Windows 上文件名是 `apple-refurb-watch.exe`。
3. 首次启动会打开窗口并出现托盘图标。

窗口关掉后默认只藏到托盘，监听继续跑；从托盘选「退出」才会停。再次双击安装包会唤起已有窗口，不会再开一份扫描。若希望关窗就退出，到设置里关掉「关闭窗口到托盘」。

Windows 需要 Edge WebView2，Windows 10/11 通常已自带。Releases 暂不提供 Intel Mac 包，请用下面的「从源码运行」。

每个系统另外还有单文件可执行版，复制方便，但首次启动更慢，也更容易被杀毒软件误报。日常优先用 zip 目录版。

登录后自动启动：在桌面里执行一次 `apple-refurb-watch service install`，或到设置里打开开机自启。冻结安装包默认安装托盘模式。

### Linux / NAS / VPS：Linux 安装包

1. 下载 `apple-refurb-watch-linux-x86_64.zip` 并解压。
2. 启动网页服务：

```bash
chmod +x ./apple-refurb-watch
./apple-refurb-watch serve
```

3. 本机浏览器打开 `http://127.0.0.1:8765`。前台运行时用 `Ctrl+C` 停止。

Linux 发布包面向 `serve` 和 CLI，不含桌面窗口。需要 Linux 图形界面时请从源码安装 `desktop` extra。

**放到 PATH（可选）**

解压目录里若有 `install.sh`：

```bash
./install.sh
```

之后可以直接运行 `apple-refurb-watch serve`。若提示找不到命令，把 `~/.local/bin` 加进 PATH。

**开机自启**

```bash
apple-refurb-watch service install --serve
apple-refurb-watch service start
```

**让手机或其它电脑访问**

默认只监听本机。NAS 若没有浏览器，先用 SSH 端口转发完成首次配置：

```bash
ssh -L 8765:127.0.0.1:8765 user@你的服务器
```

然后在自己电脑打开 `http://127.0.0.1:8765`。到「设置 → 服务」打开「允许远程访问」，保存生成的访问口令，再重启服务。

只想临时放到后台、不装开机任务：

```bash
./apple-refurb-watch serve --detach
```

### 连接远程服务

服务端先打开远程访问并保存口令。客户端再执行：

```bash
apple-refurb-watch connect http://192.168.1.8:8765 --token 你的口令
```

之后桌面、CLI 和 TUI 都使用远端数据；本机不再扫描，也不会写第二份业务库。

```bash
apple-refurb-watch disconnect
```

桌面版也可以在「设置 → 这台电脑」或托盘菜单里切换服务器。关掉远程客户端不会停止 NAS / VPS 上的服务。

公网请用 HTTPS，并在前面放 Caddy、nginx 或其它反向代理。内网可以用 HTTP。公网强制走 HTTP 时才加 `--insecure`，不推荐：

```bash
apple-refurb-watch connect https://example.com --token 你的口令
apple-refurb-watch connect http://example.com --token 你的口令 --insecure
```

口令请单独传入，不要拼进 URL。

### Docker

仓库提供 Dockerfile 和 Compose，不发布预构建镜像。数据在宿主机 `./data`，容器内固定为 `/data`。

监听 `0.0.0.0` 时必须已有访问口令，否则服务会拒绝启动。新数据目录要先初始化一次：

```bash
mkdir -p data
APPLE_REFURB_WATCH_HOME="$PWD/data" apple-refurb-watch serve
```

打开 `http://127.0.0.1:8765`，启用远程访问并保存口令，然后停掉这个临时服务。再启动容器：

```bash
cp .env.example .env
docker compose up -d --build
```

Compose 默认把端口绑到宿主机 `127.0.0.1`。需要其它设备访问时，把 `.env` 里的 `ARW_BIND` 改成 `0.0.0.0`；应用里的远程访问和口令仍必须开着。

不要让 Docker 和本机 `service` 共用同一个数据目录。容器重启由 Compose 的 `restart: unless-stopped` 管理，不必再装本机开机任务。

### 从源码运行

适合改代码、Intel Mac，或 Linux 上要开桌面窗口。步骤见文末「开发」。

## 第一次使用

打开网页后按这个顺序：

1. 点「立即扫描」，获取当前在售并建立基线。
2. 用官网同款筛选查找目标配置。
3. 在商品卡片上选「按配置听」或「精确 SKU」，也可以到「监听」页手动建规则。
4. 到「设置」启用通知通道并发送测试。
5. 保持「定时扫描」开启；要暂停时从顶栏或托盘停止监听。

首次扫描不会通知当前库存。只有之后出现的新商品，或曾经售罄后又上架的商品，才会推送。

默认每 5 分钟扫一次，最小间隔 60 秒。详情页只在规则需要、而列表又缺少内存或容量时补抓，并自动加请求间隔。

## 通知从哪里发出

| 通知类型 | 发送位置 | 是否依赖页面保持打开 |
| --- | --- | --- |
| Bark、Server酱、PushPlus、飞书、钉钉、Telegram、邮件 | 扫描所在的权威服务 | 否 |
| 浏览器通知 | 当前浏览器 | 是 |
| 桌面系统通知 | 当前桌面客户端 | 窗口可关，托盘需运行 |

服务端通知可以同时开多个通道。密钥和 Webhook 只在网页设置里填；CLI 的 `settings set` 不改密钥。

「电脑通知」属于当前客户端：

- 浏览器要在用户操作后授权，页面关掉就不再弹。
- 桌面版用系统通知，关窗到托盘后仍可收。
- 桌面连远端时，通知弹在当前电脑，不会跑到 NAS 上。

## 远程访问与安全

- 默认绑定 `127.0.0.1`，不会自动暴露到局域网。
- 绑定到非回环地址时必须配置访问口令，否则服务拒绝启动。
- Web 登录、CLI 和桌面客户端用同一个口令。
- 公网应使用 HTTPS，优先考虑 Tailscale 等私网方案。
- 不要把口令、Webhook 或邮件密码提交到仓库。
- `config export` 默认排除全部密钥；只有明确加上 `--include-secrets` 才会导出。

也可以用环境变量指定连接，它们优先于本机保存的连接：

```bash
export APPLE_REFURB_WATCH_URL="https://example.com"
export APPLE_REFURB_WATCH_TOKEN="你的口令"
```

设置后，桌面界面不能改连接，需先去掉这两个变量。

## 常用命令

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

`scan --local` 和 `list --local` 会直接用本机库。已经连远端时不要加 `--local`，CLI 会拒绝这种容易写错库的组合。

开机任务：

```bash
apple-refurb-watch service install --serve   # Linux / NAS 网页服务
apple-refurb-watch service install --tray    # 源码桌面托盘
apple-refurb-watch service start
apple-refurb-watch service status
apple-refurb-watch service restart
apple-refurb-watch service stop
apple-refurb-watch service uninstall
```

Windows / macOS 安装包里 `service install` 默认是托盘；其它环境默认是 `serve`。`--serve` 和 `--tray` 不能一起用。`apple-refurb-watch stop` 停当前进程；`service stop` 停开机任务；`service uninstall` 才删除开机任务。

## 备份、恢复与迁移

这些命令只操作权威服务那台机器上的本地库。客户端已经连远端时，要登录服务器执行。

```bash
# 创建 SQLite 在线备份并校验；默认最多保留 8 份自动备份
apple-refurb-watch backup
apple-refurb-watch backup --output /path/to/backups --keep 14

# 检查数据库、监听安全、daemon 和未完成扫描
apple-refurb-watch doctor --human

# 导出规则和非敏感设置
apple-refurb-watch config export config.json

# 导入前必须停止本机 daemon；默认保留本机密钥
apple-refurb-watch stop
apple-refurb-watch config import config.json

# 恢复前也必须停止 daemon；恢复时会留下恢复前副本
apple-refurb-watch restore /path/to/app.db
```

连同口令和通知密钥一起迁移时：

```bash
apple-refurb-watch config export config-with-secrets.json --include-secrets
apple-refurb-watch config import config-with-secrets.json --include-secrets
```

含密钥的导出文件按凭据保管，不要上传或提交到 Git。

## 数据目录与升级

```bash
apple-refurb-watch home
```

| 变量 | 用途 |
| --- | --- |
| `APPLE_REFURB_WATCH_HOME` | 覆盖数据目录 |
| `APPLE_REFURB_WATCH_LOG` | 覆盖日志目录 |
| `APPLE_REFURB_WATCH_URL` | 指定远程服务地址 |
| `APPLE_REFURB_WATCH_TOKEN` | 指定远程访问口令 |

主要数据在数据目录的 `app.db`。筛选词条由内置目录、官网同步文件和用户覆盖合并：

- `filter_catalog.live.json`：扫描或「从官网同步筛选词条」生成。
- `filter_catalog.json`：用户自定义覆盖或增量，按修改时间热加载。

升级：

1. 在权威服务机器上执行 `apple-refurb-watch backup`。
2. 停止桌面、服务或容器。
3. 替换程序文件，保留原数据目录。
4. 重新启动并执行 `apple-refurb-watch doctor --human`。

跨版本迁移会在数据目录自动创建 `app.db.bak-vN`。失败时会尝试恢复备份，并在日志里写出路径。

桌面端和服务端版本分别显示在设置页；有新版本时，「设置」入口会出现提示。远程使用时同时看客户端和服务器版本。

## TUI

TUI 面向 SSH 和纯终端：在售查询、分类与排序、基础规则增删、扫描状态、监听开关和最近动态。网络请求在后台执行，远程慢时仍可切换页面、看帮助或退出。

TUI 使用当前已保存的连接，不能在界面里填服务器地址。连远端前先运行 `apple-refurb-watch connect ...`。

复杂筛选、通知密钥、托盘和电脑通知仍以网页 / 桌面为主。

源码安装：

```bash
python -m uv sync --locked --extra tui
python -m apple_refurb_watch tui
```

常用快捷键：

- `1`–`4`：在售、监听、动态、设置。
- `/`：过滤在售；`f`：切换分类；`o`：切换价格排序。
- `s`：立即扫描；`r`：刷新当前页；`?`：完整帮助。
- `w` / `k`：按选中商品创建条件规则 / 精确 SKU 规则。
- `n`：新建规则；`e`：暂停或启用；`d`：删除。

在 80×24 等窄终端中会隐藏在售侧栏，快捷键仍可用。

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

`setup` 会创建 `.venv`，安装锁定版本的 `uv`，再执行 `uv sync --locked --extra dev`。

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

`desktop --probe` 只检查本机服务能否启动，不打开窗口；日常使用直接运行 `desktop`。

## 打包与发布

本地构建当前系统的目录版：

```bash
python -m uv sync --locked --extra desktop --extra pack
python -m PyInstaller --noconfirm --clean \
  --distpath dist/onedir \
  --workpath build/onedir \
  packaging/apple-refurb-watch.spec
```

单文件版：

```bash
APPLE_REFURB_WATCH_BUILD=onefile \
python -m PyInstaller --noconfirm --clean \
  --distpath dist/onefile \
  --workpath build/onefile \
  packaging/apple-refurb-watch.spec
```

GitHub Actions 在 PR、`v*` 标签和手动触发时跑 Linux、Windows、macOS 测试。`v*` 标签通过后生成：

- Linux x86_64：目录版 zip + 单文件可执行文件。
- Windows x86_64：目录版 zip + 单文件 `.exe`。
- macOS arm64：目录版 zip + 单文件可执行文件。
- `SHA256SUMS.txt`

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

健康检查：`GET /api/health`

## 礼貌抓取

默认扫描间隔 5 分钟，详情请求带延迟。不要把间隔设得过密，也不要同时开多个服务监听同一组规则。
