# Apple Refurb Watch

监听 [苹果中国认证翻新](https://www.apple.com.cn/shop/refurbished) 中你关心的配置，在上新或重新有货时发送通知。

[下载最新版本](https://github.com/jayjayleung/apple-refurb-watch/releases/latest)

当前源码版本：**0.3.18**。从源码运行需要 Python **3.11+**；Releases 里的目录版和单机版都不需要安装 Python。

> 本项目不是 Apple 官方产品，适合个人、自托管使用。请合理设置扫描间隔。

## 它能做什么

- 按 Mac、iPad、Apple Watch 等官网分类扫描当前在售商品。
- 按机型、芯片、尺寸、内存、容量、颜色、价格等条件创建监听规则，也支持精确 SKU。
- 首次扫描只建立库存基线，不会把已有商品全部推送一遍。
- 支持 Bark、Server酱、PushPlus、飞书、钉钉、Telegram、邮件，以及浏览器 / 桌面通知。
- 提供网页、桌面窗口、CLI 和可选 TUI；扫描和通道通知只在一台权威服务上运行。
- 可在本机使用，也可放到 NAS / VPS，再由电脑或手机远程访问。

核心原则是：**一份数据、一个权威服务、多个操作入口**。不要同时开两份扫描。

## 安装

先选一种方式，只看对应小节。默认网页是 `http://127.0.0.1:8765`。

Releases 里的 **zip 目录版**和 **单机版（单文件）都不需要安装 Python**。日常优先用目录版，并保留整个文件夹（旁边的 `_internal` 不能丢掉）。只有从源码运行才需要 Python 3.11+。

目录版 / 单机版都可以当 CLI 用（在终端里对同一个文件加子命令，不要靠双击）。TUI 是可选终端界面，发布包里没有，见后面「TUI」。

| 你的情况 | 用这个 |
| --- | --- |
| Windows 或 Apple Silicon Mac，自己用 | 下面「桌面安装包」 |
| 拷一个文件就跑，不需解压目录 | 下面「单机版（单文件）」 |
| NAS / Linux 服务器，一直跑 | 下面「Linux 安装包」 |
| 服务已经在跑，另一台电脑或手机来看 | 下面「连接远程服务」 |
| 已经有 Docker | 下面「Docker」 |
| 改代码、Intel Mac、Linux 桌面窗口 | 下面「从源码运行」 |

运行 `apple-refurb-watch home` 可查看当前数据目录。

### Windows / macOS：桌面安装包

不需要安装 Python。

1. 打开 [Releases](https://github.com/jayjayleung/apple-refurb-watch/releases/latest)，下载对应 zip 并解压。解压后进入里面的 `apple-refurb-watch` 文件夹：
   - Windows x86_64：`apple-refurb-watch-windows-x86_64.zip`
   - macOS Apple Silicon：`apple-refurb-watch-macos-arm64.zip`
2. 双击 `apple-refurb-watch`。Windows 上文件名是 `apple-refurb-watch.exe`。不要只拷走这一个文件，同目录的 `_internal` 必须留下。
3. 首次启动会打开窗口并出现托盘图标。

窗口关掉后默认只藏到托盘，监听继续跑；从托盘选「退出」才会停。再次双击会唤起已有窗口，不会再开一份扫描。若希望关窗就退出，到设置里关掉「关闭窗口到托盘」。

开机自启：在「设置 → 这台电脑」打开，或从托盘菜单打开。也可以在终端执行 `apple-refurb-watch service install`（安装包默认是托盘模式）。

Windows 需要 Edge WebView2，Windows 10/11 通常已自带。Releases 暂不提供 Intel Mac 包，请用下面的「从源码运行」。

同一个文件也能当 CLI 用。在终端进入该文件夹：

```bash
./apple-refurb-watch --help          # macOS
.\apple-refurb-watch.exe --help      # Windows PowerShell
```

### 单机版（单文件）

不需要安装 Python，也不用解压目录。每个系统一个可执行文件，适合拷到 U 盘或临时目录：

- Windows：`apple-refurb-watch-windows-x86_64.exe`
- macOS Apple Silicon：`apple-refurb-watch-macos-arm64`
- Linux：`apple-refurb-watch-linux-x86_64`

第一次启动会自行解开运行时，比目录版慢，也更容易被杀毒软件误报。能解压 zip 时优先用目录版。

Windows / macOS 双击仍打开桌面窗口；要跑命令请在终端里对这个文件加子命令。Linux / NAS 没有桌面窗口，用来跑服务或 CLI：

```bash
chmod +x ./apple-refurb-watch-linux-x86_64
./apple-refurb-watch-linux-x86_64 serve
```

命令行用法和目录版相同，只是把文件名换成这个单文件。Linux/macOS 若下载后没有执行权限，先 `chmod +x`。

### Linux / NAS / VPS：Linux 安装包

不需要安装 Python。

1. 下载 `apple-refurb-watch-linux-x86_64.zip` 并解压，进入里面的 `apple-refurb-watch` 文件夹。同目录的 `_internal` 必须留下。
2. 启动网页服务：

```bash
chmod +x ./apple-refurb-watch
./apple-refurb-watch serve
```

3. 本机浏览器打开 `http://127.0.0.1:8765`。前台运行时用 `Ctrl+C` 停止。

Linux 发布包面向 `serve` 和 CLI，不含桌面窗口。需要 Linux 图形界面时请从源码安装 `desktop` extra。TUI 也不在发布包里，见后面「TUI」。

**放到 PATH（可选）**

解压目录里若有 `install.sh`：

```bash
./install.sh
```

之后可以直接运行 `apple-refurb-watch serve`。若提示找不到命令，把 `~/.local/bin` 加进 PATH。

**开机自启**

网页设置里也可以开关。命令行：

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

之后桌面和 CLI 都使用远端数据；本机不再扫描，也不会写第二份业务库。源码安装的 TUI 同样走这份连接。

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

容器会监听 `0.0.0.0`，必须已有访问口令，否则服务会拒绝启动。首次使用任选其一：

- 复制 `.env.example` 为 `.env`，填写 `APPLE_REFURB_WATCH_ACCESS_TOKEN`，再执行 `scripts/docker-up.sh`（空数据目录且无口令时脚本会拒绝启动）。
- 或先用刚下载的 Linux 目录版（或单机版）初始化 `./data`，在网页里启用远程访问并保存口令，再启动容器。

用本机程序初始化时，在解压后的 `apple-refurb-watch` 文件夹里：

```bash
mkdir -p data
APPLE_REFURB_WATCH_HOME="$PWD/data" ./apple-refurb-watch serve
```

单机版把上面的文件名换成 `apple-refurb-watch-linux-x86_64`。

打开 `http://127.0.0.1:8765`，启用远程访问并保存口令，然后停掉这个临时服务。再启动容器：

```bash
cp .env.example .env
docker compose up -d --build
```

Compose 默认把端口绑到宿主机 `127.0.0.1`。需要其它设备访问时，把 `.env` 里的 `ARW_BIND` 改成 `0.0.0.0`；应用里的远程访问和口令仍必须开着。

不要让 Docker 和本机 `service` 共用同一个数据目录。容器重启由 Compose 的 `restart: unless-stopped` 管理，不必再装本机开机任务。

### 从源码运行

适合改代码、Intel Mac，或 Linux 上要开桌面窗口。需要 Python 3.11+，步骤见文末「开发」。

## 第一次使用

打开桌面窗口或网页后按这个顺序：

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
- 会话 cookie 是访问口令的 HMAC，等价于口令本身，不能按设备单独吊销；改口令后旧 cookie 失效。
- 用域名或反向代理（Caddy / nginx + HTTPS）访问时，把主机名登记到设置页的「允许的主机名」，或设置环境变量 `APPLE_REFURB_WATCH_ALLOWED_HOSTS`（逗号分隔）。IP 字面量与 `localhost` 始终放行。
- 已绑定非回环地址时不能清除口令：先关闭「允许远程访问」、保存并重启，再在回环监听下清除。
- 公网应使用 HTTPS，优先考虑 Tailscale 等私网方案。
- 不要把口令、Webhook 或邮件密码提交到仓库。
- `config export` 默认排除全部密钥；只有明确加上 `--include-secrets` 才会导出。

也可以用环境变量指定连接，它们优先于本机保存的连接：

```bash
export APPLE_REFURB_WATCH_URL="https://example.com"
export APPLE_REFURB_WATCH_TOKEN="你的口令"
```

设置后，桌面界面不能改连接，需先去掉这两个变量。

## CLI

CLI 是运维和脚本入口：启停服务、扫描、查在售、管规则、看动态、备份。目录版、单机版和源码都带；和网页共用同一套 HTTP API。Windows / macOS **双击**打开的是桌面窗口，要用 CLI 请在终端里对同一个文件加子命令。

```bash
apple-refurb-watch --help
apple-refurb-watch <命令> --help
```

目录版（进入 zip 里的 `apple-refurb-watch` 文件夹）：

```bash
./apple-refurb-watch version            # macOS / Linux
.\apple-refurb-watch.exe version        # Windows
```

单机版把文件名换成 `apple-refurb-watch-linux-x86_64` 或 `apple-refurb-watch-windows-x86_64.exe`。装过 `install.sh` 或源码环境后，可直接打 `apple-refurb-watch`。

默认连本机权威服务；若本机还没在跑，多数命令会按需拉起。已经 `connect` 到远端后，CLI / TUI / 桌面都走那台服务器，本机不再扫描。`scan --local` 和 `list --local` 会绕过服务直接读本机库；已经连远端时不要加 `--local`，CLI 会拒绝。

通知密钥、访问口令和 Webhook **不能**用 CLI 填写或查看，请到网页设置。`settings set` 只动扫描间隔、监听开关、分类和是否允许远程访问（`--lan` 在还没有口令时会自动生成一份，仍要到网页里看）。

### 服务

```bash
apple-refurb-watch version
apple-refurb-watch home                 # 数据目录
apple-refurb-watch serve                # 前台网页服务，Ctrl+C 停止
apple-refurb-watch serve --detach       # 放到后台
apple-refurb-watch status
apple-refurb-watch stop                 # 停当前 daemon，不是删开机任务
```

### 扫描与在售

```bash
apple-refurb-watch scan
apple-refurb-watch list --q "MacBook Pro"
apple-refurb-watch list --listing mac --sort -price
apple-refurb-watch list --dim chip=m5_pro --max-price 18000 --min-ram 24 --min-storage 512
apple-refurb-watch list --json
```

`--listing` 是分类 key，如 `mac` / `ipad`。`--dim` 可重复，格式 `key=value`。只显示当前监听分类里的在售，不是只显示已命中规则的商品。

### 监听规则

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

`watch ls` 最左列是规则 ID，后面的 pause / resume / rm 用这个数字。`--mode` 默认 `condition`；精确 SKU 用 `--mode sku --sku ...`。

### 动态、设置与通知

```bash
apple-refurb-watch events
apple-refurb-watch events --limit 100 --json
apple-refurb-watch events clear         # 只清动态，不影响在售和规则

apple-refurb-watch settings get
apple-refurb-watch settings set --listings mac,ipad --interval 300 --listen
apple-refurb-watch settings set --no-listen
apple-refurb-watch settings set --lan
apple-refurb-watch settings set --no-lan
apple-refurb-watch settings sync-catalog
apple-refurb-watch notify-test          # 按网页里已保存的通道发测试
```

`--json` 输出里的时间为 UTC；终端默认列表用本地时区。

### 连接与开机任务

```bash
apple-refurb-watch connect http://192.168.1.8:8765 --token 你的口令
apple-refurb-watch disconnect

apple-refurb-watch service install --serve   # Linux / NAS 网页服务
apple-refurb-watch service install --tray    # 桌面托盘（安装包默认）
apple-refurb-watch service start
apple-refurb-watch service status
apple-refurb-watch service restart
apple-refurb-watch service stop
apple-refurb-watch service uninstall
```

Windows / macOS 安装包里 `service install` 默认是托盘；其它环境默认是 `serve`。`--serve` 和 `--tray` 不能一起用。`stop` 停当前进程；`service stop` 停开机任务；`service uninstall` 才删除开机任务。备份、恢复、配置导入见下面「备份、恢复与迁移」。

## TUI

TUI 是 SSH 或纯终端里的全屏界面：四个页签（在售、监听、动态、设置），覆盖日常看货、建规则、手动扫描和开关监听。网络请求在后台跑，远程慢时仍可换页、看帮助或退出；失败会留下原表格，设置开关也会回滚。

发布包和单机版默认没有 Textual，运行 `tui` 会提示先装依赖。从源码：已按文末「开发」建好环境的（`dev` extra 已含 Textual），激活虚拟环境后直接：

```bash
apple-refurb-watch tui
```

只要 TUI、不装开发依赖时：

```bash
python -m uv sync --locked --extra tui
apple-refurb-watch tui
```

它使用当前已保存的连接，界面里不能填服务器地址。连远端先执行 `apple-refurb-watch connect ...`，再开 TUI。本机模式会按需连到本机权威服务。

复杂筛选、通知密钥、托盘和电脑通知仍用网页或桌面。TUI 设置页可以开关定时监听、勾选监听分类、发测试通知、从官网同步筛选词条。

### 页面

| 键 | 页面 | 做什么 |
| --- | --- | --- |
| `1` | 在售 | 当前监听分类里的商品；可过滤、换分类、改价格排序 |
| `2` | 监听 | 规则列表：状态、方式、在售命中、条件 |
| `3` | 动态 | 扫描结果和上新记录；同一天的例行扫描会折成一条 |
| `4` | 设置 | 监听总开关、分类、测试通知、同步筛选词条 |

第一次建议：`s` 扫一次建立基线 → `1` 看在售 → 选中一行后 `w` 按配置听或 `k` 精确 SKU → `4` 打开定时监听。

### 快捷键

全局：

- `?` 帮助；`q` 退出；`r` 刷新当前页；`s` 立即扫描；`1`–`4` 换页。
- 扫描会显示等待 / 运行 / 最终状态，完成前按钮不可再点。

在售：

- `/` 过滤关键词；`f` 切换分类；`o` 价格低→高 / 高→低。
- `w` 按选中商品建条件规则；`k` 按选中商品建精确 SKU 规则。

监听：

- `n` 新建（分类、条件/精确 SKU、维度、最低内存/容量、最高价；提交前校验）。
- `e` 暂停或启用当前规则；`d` 删除。
- `Esc` 关闭新建表单。

动态：

- `c` 清除记录，不影响在售和规则。

终端宽度不足 100 列时（例如 80×24）会隐藏在售侧栏，状态改到顶栏，快捷键仍可用。

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
| `APPLE_REFURB_WATCH_ALLOWED_HOSTS` | 额外允许的 Host / Origin 主机名，逗号分隔 |

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

- `tui`：Textual 终端界面。`dev` extra 已包含，跑过 `./scripts/setup.sh` 后可直接 `apple-refurb-watch tui`。
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

GitHub Actions 在 Pull Request、`v*` 标签和手动触发时跑 Linux、Windows、macOS 测试。打 `v*` 标签还会打包并发布 GitHub Release（手动触发也会构建安装包，但不自动发 Release）：

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
