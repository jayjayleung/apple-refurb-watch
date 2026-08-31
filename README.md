# 苹果官翻指定配置监听

监听 [苹果中国认证翻新](https://www.apple.com.cn/shop/refurbished) 里你选定的配置。上新时推送到 Bark、Server酱、PushPlus、飞书、钉钉、Telegram、邮件；电脑上还可以用系统通知或网页通知。

一份数据、一个后台服务（扫描和 SQLite 只在一处）。网页、桌面窗口、CLI、TUI 都通过 JSON API 操作。桌面默认同进程自带服务；也可以改连已经跑在 NAS/VPS 上的那一份。

仓库：[github.com/jayjayleung/apple-refurb-watch](https://github.com/jayjayleung/apple-refurb-watch)

当前版本：**0.2.2**

默认地址 `http://127.0.0.1:8765`。数据目录可用 `APPLE_REFURB_WATCH_HOME` 覆盖，看当前目录：`apple-refurb-watch home`。

## 你是谁

### Windows / macOS，服务跑本机

1. 从 [Releases](https://github.com/jayjayleung/apple-refurb-watch/releases) 下载对应 zip，解压。
   - Windows：`apple-refurb-watch-windows-x86_64.zip`（需要 Edge WebView2，Win10/11 一般都有）
   - macOS Apple Silicon：`apple-refurb-watch-macos-arm64.zip`（Intel Mac 请走下面「开发」）
2. 双击目录里的 `apple-refurb-watch`（Windows 是 `.exe`）。无 Python。
3. 首次会打开窗口并出现托盘图标。关窗进托盘，扫描继续；托盘「退出」才停本机服务。再双击安装包会唤起已有窗口，不会再起一份扫描。
4. 开机自启：设置「这台电脑」→「开机自启（这台电脑的托盘）」，或 `apple-refurb-watch service install`（安装包默认 `--tray`）。登录后拉起托盘，可 `service start` / `stop` / `restart`。本机桌面模式会隐藏「本机服务开机自启」，避免再装一份 `serve`。

不要先 `serve --detach` 再自己开浏览器。不要关窗再手动拉一份后台进程。不想关窗进托盘：设置里关掉「关闭窗口到托盘」。

托盘：打开、开始/停止监听、连接服务器、电脑通知、开机自启、退出。

### 服务器在 NAS / VPS，桌面只当窗口

1. 先按下面「只要网页」把**服务端**跑起来，打开「允许远程访问」，记下口令。服务端开机用设置「开机后自动运行服务」，或 `service install --serve`。
2. 同一包双击后，到设置「这台电脑」填地址和口令（托盘也有「连接服务器…」）。也可以命令行：

```bash
apple-refurb-watch connect http://192.168.1.8:8765 --token 你的口令
```

本机不再扫描、不写第二份库。托盘退出只关窗口，不动服务器。连上之后，设置页「本机服务开机自启」改的是 **NAS 那台机器**；「这台电脑」里的开机自启仍是这台电脑的托盘。

公网地址请用 `https://`，前面用 Caddy/nginx 反代；应用继续 HTTP + 口令。内网 NAS 用 HTTP 即可。公网硬要 HTTP 时勾选「允许公网 HTTP」或加 `--insecure`（不推荐）。口令单独填，不要写进 URL。远端不设口令就不要绑 `0.0.0.0`。

改回本机：设置「改回本机」，或 `apple-refurb-watch disconnect`。

环境变量 `APPLE_REFURB_WATCH_URL` / `APPLE_REFURB_WATCH_TOKEN` 优先于上述连接配置，CLI / TUI / 桌面共用。设了环境变量后，界面无法改连接。

版本对不上时，页面顶栏会提示：服务器 API 新于本客户端 → 升级桌面/CLI；服务器较旧 → 核心功能仍可用，电脑通知等会隐藏。

### 只要网页或手机（服务器 / NAS）

**不要 Docker 时：** 从 [Releases](https://github.com/jayjayleung/apple-refurb-watch/releases) 下载 `apple-refurb-watch-linux-x86_64.zip`，解压后：

```bash
./apple-refurb-watch serve
# 浏览器打开打印的地址，默认 http://127.0.0.1:8765
```

后台跑一次（不装开机任务）：`./apple-refurb-watch serve --detach`。`--host` / `--port` 在本次启动生效并写入设置。在网页设置里改端口或绑定后，需要重启 serve / `service restart`。

可选装到 `~/.local/bin`（在解压目录里）：

```bash
./install.sh
```

开机自启（拉起 `serve`，不是托盘）：

```bash
apple-refurb-watch service install --serve
apple-refurb-watch service start    # 已 install 之后随时启停
apple-refurb-watch service stop
apple-refurb-watch service restart
apple-refurb-watch service status
```

也可在设置页勾选「开机后自动运行服务」。Linux 走 systemd --user，macOS 走 LaunchAgent，Windows 走登录计划任务。同一系统只装一份任务：要么托盘，要么服务。

**已经用 Docker 时**，用仓库里的 compose 本地构建（数据在宿主机 `./data`）：

```bash
cp .env.example .env
docker compose up -d --build
```

不要再在同一数据目录上装本机 `service`。Docker 用 compose 的 `restart: unless-stopped`。CI 不推镜像。

## 网页里做什么

浏览器打开 `http://127.0.0.1:8765`（或你改过的端口）。

1. 点「立即扫描」拉当前在售
2. 用官网同款筛选（机型 / 尺寸 / 内存 / 容量等），或在卡片上「按配置听」「精确 SKU」
3. 到「设置」打开通知通道（Bark / Server酱 / PushPlus / 飞书 / 钉钉 / Telegram / 邮件），点「发送测试通知」。密钥只在这一页填
4. 可同时打开「电脑通知」（网页会要权限；桌面走系统通知）。关掉浏览器页后网页不会再弹，锁屏仍靠 Bark 等，或让桌面留在托盘
5. 顶栏可以「停止监听 / 开始监听」：只停定时扫描，不关服务
6. 需要其它设备访问：打开「允许远程访问」并设口令（默认只服务本机）
7. 扫描所在的那台机器要开机自跑：设置「开机后自动运行服务」。桌面包本机请用「这台电脑」的托盘自启（本机模式会隐藏服务开关）

首次扫描只建基线，不会把当前库存全部推送一遍。某台机器卖掉再重新上架才会再通知。

## 通知怎么分工

| 通道 | 从哪发出 | 人在哪台电脑 |
| --- | --- | --- |
| Bark / Server酱 / PushPlus / 飞书 / 钉钉 / Telegram / 邮件 | 扫描所在的那台机器 | 无关 |
| 电脑系统通知 / 网页通知 | 你眼前这台客户端 | 必须是这台机器；连远端时也不要在 NAS 上弹 toast |

它们可以同时开。电脑通知开关存在本机（网页用浏览器权限 / localStorage，桌面用本机偏好），不进服务端设置。口令和 Webhook 只在网页设置里填，CLI `settings set` 不改密钥。

## TUI

核心操作与网页、CLI 对齐：在售（分类 / 排序 / 条件）、规则增删、扫描、监听开关、状态、连本机或远端。

界面不对等：侧栏 facets、每日动态分页、通知通道密文表单、托盘、电脑通知、连接服务器表单。判断标准是：只开 TUI 能否完成「设规则 + 等到上新」。

TUI 跟已保存的连接走（或环境变量），界面里不能填 URL。要改连远端，先 `apple-refurb-watch connect …`。在售页快捷键：`f` 切换分类，`o` 切换价格排序。

TUI 不进默认安装包（textual 较重）。开发者：

```bash
pip install ".[tui]"
apple-refurb-watch tui
```

## 命令行

安装包和源码是同一个入口。`apple-refurb-watch --help` 看全部。

```bash
apple-refurb-watch version
apple-refurb-watch home

apple-refurb-watch serve
apple-refurb-watch serve --detach
apple-refurb-watch serve --host 0.0.0.0 --port 8765
apple-refurb-watch desktop
apple-refurb-watch desktop --hidden
apple-refurb-watch tui

apple-refurb-watch connect http://192.168.1.8:8765 --token 口令
apple-refurb-watch connect https://example.com --token 口令
apple-refurb-watch connect http://example.com --token 口令 --insecure   # 公网 HTTP，不推荐
apple-refurb-watch disconnect

apple-refurb-watch scan
apple-refurb-watch scan --local                    # 不走 daemon，本进程扫一次
apple-refurb-watch list --q "MacBook Pro"
apple-refurb-watch list --listing mac --sort -price --dim chip=m5 --dim dimensionScreensize=14inch
apple-refurb-watch list --max-price 18000 --min-ram 24 --min-storage 512 --json
apple-refurb-watch list --local                    # 已 connect 远端时不要用

apple-refurb-watch watch add --name "14 MBP" --listing mac --dim chip=m5_pro --dim dimensionScreensize=14inch --min-ram 24 --max-price 18000
apple-refurb-watch watch add --name "这台" --mode sku --sku MLXX3CH/A
apple-refurb-watch watch ls
apple-refurb-watch watch pause 1
apple-refurb-watch watch resume 1
apple-refurb-watch watch rm 1

apple-refurb-watch events
apple-refurb-watch events --limit 100 --json
apple-refurb-watch events clear

apple-refurb-watch settings get
apple-refurb-watch settings set --listings mac,ipad --listen
apple-refurb-watch settings set --interval 300 --lan
apple-refurb-watch settings set --no-listen --no-lan
apple-refurb-watch settings sync-catalog
apple-refurb-watch notify-test
apple-refurb-watch status
apple-refurb-watch stop                            # 停当前 daemon，不是开机任务

apple-refurb-watch service install
apple-refurb-watch service install --serve
apple-refurb-watch service install --tray
apple-refurb-watch service start
apple-refurb-watch service stop
apple-refurb-watch service restart
apple-refurb-watch service status
apple-refurb-watch service uninstall
```

`--local` 只读本机库。已经 `connect` 到远端时不要用，避免对着空库操作。

Docker 数据目录已固定为 `/data`。

## 开机自启

先 `install` 再 `start`。`service stop` 只停开机任务，不卸载；`service uninstall` 才删掉。`apple-refurb-watch stop` 停的是当前 daemon，两者不是一回事。

| | 装什么 | 登录后 |
| --- | --- | --- |
| Windows / macOS 桌面包 | `service install` 或 `--tray` | 托盘（`desktop --hidden`） |
| Linux / NAS / VPS | `service install --serve` | 网页服务 `serve` |
| 源码在 Linux 上跑桌面 | `service install --tray` | 托盘 |
| Docker | 不要装本机 service | compose `restart: unless-stopped` |

不带参数的 `service install`：Win/mac **安装包**默认托盘，其它默认 `serve`。`--serve` 与 `--tray` 不要一起用。未 `install` 时 `start` / `stop` / `restart` 会失败并退出 1。

改端口或绑定地址后需要 `service restart`，或重启 serve / 容器。

## 礼貌抓取

默认 5 分钟一轮。详情页只在规则需要内存/硬盘且列表里缺字段时才补抓，并带间隔。请不要把间隔改到过于频繁。

## 开发

需要 Python 3.11+。

```bash
git clone https://github.com/jayjayleung/apple-refurb-watch.git
cd apple-refurb-watch
./scripts/setup.sh
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Windows：`powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1`。

可选 extra：`.[tui]` 终端界面，`.[desktop]` 桌面窗口和托盘，`.[all]` 两者都要。Linux 桌面还需要 WebKitGTK，例如 Debian/Ubuntu：`sudo apt install gir1.2-webkit2-4.1 python3-gi`。

筛选词条默认在 `src/apple_refurb_watch/data/filter_catalog.json`。扫描或设置页「从官网同步筛选词条」会写入数据目录的 `filter_catalog.live.json`，与安装包内置词条以及用户覆盖文件合并。把同名 `filter_catalog.json` 放到数据目录可做覆盖或增量合并，按 mtime 热加载，不必重启。

跨版本升级数据库前会备份为数据目录里的 `app.db.bak-vN`。若升级失败，会还原备份，日志里带备份路径。

JSON API 是网页 / 桌面 / CLI / TUI 的共同入口，先看 `GET /api/health`（含 `server_version`、`api_revision`、`capabilities`）。

## 打包与发布

GitHub Actions 只留一套 `ci`：

- PR 和 `main`：Linux / Windows / macOS pytest，不打包。
- `v*` 标签：同一套测试通过后打三端 onedir zip、烟测 `serve` 的 `GET /` 200 和 `desktop --probe`，发 GitHub Release。
- 手动运行只留 artifacts，不发 Release。不打 Docker 镜像。

Windows / macOS 托盘依赖系统通知区域。Linux 开发机只能验证 `--probe` 与导入，不能代替真机关窗留守。`desktop --probe` 是打包烟测用的，日常打开窗口请直接双击或 `desktop`。

```bash
git tag v0.2.2
git push origin v0.2.2
```

本地打当前系统一份：

```bash
pip install ".[desktop]" ".[pack]"
python -m PyInstaller --noconfirm --clean packaging/apple-refurb-watch.spec
# 产物在 dist/apple-refurb-watch/
```
