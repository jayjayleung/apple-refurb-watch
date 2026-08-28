# 苹果官翻指定配置监听

盯住 [苹果中国认证翻新](https://www.apple.com.cn/shop/refurbished) 里你选定的配置。上新时推送到 Bark / 微信 / 飞书 / 钉钉 / Telegram / 邮件。

一个后台 daemon 独占扫描和写库；网页、桌面窗口、CLI、TUI 都通过本地 API 操作。

仓库：[github.com/jayjayleung/apple-refurb-watch](https://github.com/jayjayleung/apple-refurb-watch)

## 先看这里：Releases 和 Packages 不是一回事

| 入口 | 是什么 | 你该不该用 |
| --- | --- | --- |
| [Releases](https://github.com/jayjayleung/apple-refurb-watch/releases) | Linux / macOS / Windows **可执行文件** | 不想装 Python、直接下载运行，看这里 |
| [Packages](https://github.com/jayjayleung/apple-refurb-watch/pkgs/container/apple-refurb-watch) | **Docker 镜像**（GHCR） | 用容器部署时 `docker pull`，不是 exe |
| Actions → package | 每次推 `main` 打的安装包 artifact | 还没打版本标签时，可从这里下预览包 |

当前稳定版：[v0.1.2](https://github.com/jayjayleung/apple-refurb-watch/releases/tag/v0.1.2)

## 方式一：下载安装包

从 [Releases](https://github.com/jayjayleung/apple-refurb-watch/releases) 按系统取对应文件：

- Linux x86_64：`apple-refurb-watch-linux-x86_64`
- macOS Apple Silicon：`apple-refurb-watch-macos-arm64`
- Windows：`apple-refurb-watch-windows-x86_64.exe`

```bash
chmod +x apple-refurb-watch-linux-x86_64
./apple-refurb-watch-linux-x86_64 serve --detach
# 浏览器打开 http://127.0.0.1:8765
./apple-refurb-watch-linux-x86_64 stop
```

Windows / macOS 安装包带桌面窗口（WebView 套网页）：

- **Windows**：双击 `apple-refurb-watch-windows-x86_64.exe` 打开窗口。需要系统已装 Edge WebView2（Win10/11 一般都有）。关窗口默认不关后台监听。
- **macOS**：终端里直接运行 `./apple-refurb-watch-macos-arm64`（不要带参数）会打开窗口。
- **Linux** 安装包是给服务器用的命令行，没有桌面窗口；用 `serve` 再浏览器打开。

命令行仍然可用：

```powershell
.\apple-refurb-watch-windows-x86_64.exe serve --detach
.\apple-refurb-watch-windows-x86_64.exe stop
```

## 方式二：源码 + 本地脚本

需要 Python 3.11+。

Linux / macOS：

```bash
git clone https://github.com/jayjayleung/apple-refurb-watch.git
cd apple-refurb-watch
./scripts/setup.sh          # 创建 .venv 并安装
./scripts/serve.sh          # 前台启动，Ctrl+C 退出
./scripts/serve.sh --detach # 后台
./scripts/status.sh
./scripts/stop.sh
```

Windows（PowerShell）：

```powershell
git clone https://github.com/jayjayleung/apple-refurb-watch.git
cd apple-refurb-watch
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\serve.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\serve.ps1 --detach
powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1
```

可选依赖：

```bash
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[tui]"            # 终端界面
pip install -e ".[desktop]"        # 桌面窗口
pip install -e ".[all]"
```

Linux 桌面窗口还需要 WebKitGTK，例如 Debian/Ubuntu：

```bash
sudo apt install gir1.2-webkit2-4.1 python3-gi
```

Windows 桌面窗口需要 Edge WebView2；macOS 用系统 WebKit。

手动等价于脚本的命令：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
apple-refurb-watch serve
```

## 方式三：Docker

仓库已带 `Dockerfile` 和 `docker-compose.yml`。数据写在宿主机 `./data`（对应容器内 `/data`），容器重启不丢库。

### 本机构建（推荐先这样）

```bash
git clone https://github.com/jayjayleung/apple-refurb-watch.git
cd apple-refurb-watch
./scripts/docker-up.sh     # 复制 .env、构建并后台启动
# 打开 http://127.0.0.1:8765
./scripts/docker-down.sh   # 停容器，保留 ./data
```

Windows：`.\scripts\docker-up.ps1` / `.\scripts\docker-down.ps1`。

等价命令：

```bash
cp .env.example .env
docker compose up -d --build
docker compose down
```

改端口或绑定地址：编辑 `.env`（可先 `cp .env.example .env`）

```
ARW_BIND=127.0.0.1
ARW_PORT=8765
```

默认只映射到本机回环，避免端口一开就暴露到局域网。手机要访问时改成 `ARW_BIND=0.0.0.0`，**并在网页设置里打开「允许局域网访问」且设置口令**。只改绑定、不开局域网开关时，接口不会校验口令。

本机 8765 已被占用时，把 `ARW_PORT` 改成空闲端口，例如 `8766`。

### 用 GitHub Packages 里的镜像

推送 `main` 或 `v*` 标签后，镜像会出现在仓库的 **Packages** 页：

```text
ghcr.io/jayjayleung/apple-refurb-watch:latest
ghcr.io/jayjayleung/apple-refurb-watch:0.1.2
```

```bash
docker pull ghcr.io/jayjayleung/apple-refurb-watch:latest
# 仍用本仓库 compose：会优先用上面这个 image 名
docker compose up -d
```

若 Packages 里镜像是 private，先登录：

```bash
echo YOUR_GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin
```

公开仓库也可在镜像的 Package settings 里把 visibility 改成 Public，这样别人不用登录就能 pull。

手动 `docker run`：

```bash
docker run --rm \
  -p 127.0.0.1:8765:8765 \
  -v "$PWD/data:/data" \
  -e APPLE_REFURB_WATCH_HOME=/data \
  ghcr.io/jayjayleung/apple-refurb-watch:latest
```

容器内进程前台跑 `serve --host 0.0.0.0 --port 8765`，不要再加 `--detach`。

## 网页里做什么

浏览器打开 `http://127.0.0.1:8765`（或你改过的端口）。

1. 点「立即扫描」拉当前在售
2. 用官网同款筛选（机型 / 尺寸 / 内存 / 容量等），或在卡片上「按配置听」「精确 SKU」
3. 到「设置」打开通知通道，点「发送测试通知」
4. 顶栏状态条可以「停止监听 / 开始监听」：只停定时扫描，不关服务；网页和手动扫描仍可用
5. 需要手机访问时：打开「允许局域网访问」并设口令（默认只服务本机）

首次扫描只建基线，不会把当前库存全部推送一遍。某台机器卖掉再重新上架才会再通知。

## 命令行

脚本装好之后，虚拟环境里的命令和安装包是同一个入口：

```bash
apple-refurb-watch serve
apple-refurb-watch serve --detach --host 127.0.0.1 --port 8765
apple-refurb-watch desktop
apple-refurb-watch tui
apple-refurb-watch scan
apple-refurb-watch list --q "MacBook Pro"
apple-refurb-watch watch add --name "14 MBP" --all-of "14 英寸,MacBook Pro,M5 Pro" --min-ram 24 --max-price 18000
apple-refurb-watch watch ls
apple-refurb-watch notify-test
apple-refurb-watch status
apple-refurb-watch stop
apple-refurb-watch home
```

数据目录默认是系统用户数据目录（`platformdirs`），也可用环境变量覆盖：

```bash
export APPLE_REFURB_WATCH_HOME=/path/to/data
```

Docker 已固定为 `/data`。看当前目录：`apple-refurb-watch home`。

## 开机自启

```bash
apple-refurb-watch service install
apple-refurb-watch service status
apple-refurb-watch service uninstall
```

- Linux：systemd --user
- macOS：LaunchAgent
- Windows：登录计划任务

Docker 部署用 compose 的 `restart: unless-stopped`，不要再装一份本机 service，以免两个进程抢同一份库。

改端口或绑定地址后需要重启 serve / 容器。

## 礼貌抓取

默认 5 分钟一轮。详情页只在规则需要内存/硬盘且列表里缺字段时才补抓，并带间隔。请不要把间隔改到过于频繁。

## 开发

```bash
./scripts/setup.sh
source .venv/bin/activate
pytest
```

筛选词条默认在 `src/apple_refurb_watch/data/filter_catalog.json`。扫描或设置页「从官网同步筛选词条」会写入数据目录的 `filter_catalog.live.json`，与安装包内置词条以及用户覆盖文件合并。把同名 `filter_catalog.json` 放到数据目录可做覆盖或增量合并，按 mtime 热加载，不必重启。

## 打包

推送到 `main` 后，GitHub Actions 会：

- `ci`：跑 pytest（Linux / Windows / macOS）
- `package`：打三端 PyInstaller 包，上传到 Actions Artifacts
- `docker`：构建镜像并推到 `ghcr.io/jayjayleung/apple-refurb-watch`

打 `v*` 标签会同时发 GitHub Release（可执行文件），镜像打上对应 semver 标签：

```bash
git tag v0.1.2
git push origin v0.1.2
```

本地打当前系统一份时，Windows / macOS 若要带桌面窗口：

```bash
pip install ".[desktop]" ".[pack]"
python -m PyInstaller --noconfirm --clean packaging/apple-refurb-watch.spec
```
