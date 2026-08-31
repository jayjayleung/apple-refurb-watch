# 苹果官翻监听 0.2.4

这是 **0.2** 的安装包。此前 `v0.2.0`–`v0.2.2` 因 CI 没有成功发出压缩包；`v0.2.3` 若本机还开着旧版托盘，会误报版本过旧。请用这一版。网页、桌面、CLI 共用一份数据和一个后台服务。

打开新安装包时，若本机还在跑更旧的托盘或 `serve`，会先退出旧进程再启动，不必先手动退出。连 NAS 上的旧服务端时，提示改连后请把服务端也换成这一版。

## 下载

按系统解压即可，不必安装 Python。

- **Windows**：`apple-refurb-watch-windows-x86_64.zip`（需要 Edge WebView2，Win10/11 一般都有）
- **macOS Apple Silicon**：`apple-refurb-watch-macos-arm64.zip`（Intel Mac 请用源码运行）
- **Linux / NAS**：`apple-refurb-watch-linux-x86_64.zip`

Windows / macOS 双击目录里的 `apple-refurb-watch`（Windows 是 `.exe`）。Linux 在解压目录执行 `./apple-refurb-watch serve`，后台跑用 `serve --detach`。默认网页 [http://127.0.0.1:8765](http://127.0.0.1:8765)。

## 相对 0.1 主要变化

### 桌面

- 本机模式同进程自带服务。关窗默认进托盘，扫描继续；托盘「退出」才停。
- 再双击不会起第二份扫描，会唤起已有窗口。
- 设置「这台电脑」或托盘「连接服务器…」可改连 NAS / VPS 上已经在跑的那一份。本机不再扫描、不写第二份库。
- 电脑通知：桌面走系统通知；网页勾选「启用电脑通知」后由浏览器弹出（需要你点一下授权，页面加载时不会要权限）。

### 设置

- 分成「监听 / 通知 / 这台电脑 / 服务」。
- 监听开关、分类、关窗到托盘、电脑通知、开机自启即时生效。
- 间隔、端口、远程访问、口令和通道密钥点「保存」。
- 每个通知通道可单独发送测试。密钥不回显，旁边标明「已保存」。

### 开机自启

- Windows / macOS 安装包：设置「开机自启（这台电脑的托盘）」，或 `apple-refurb-watch service install`。
- NAS / VPS：`service install --serve`，或设置「开机后自动运行服务」。
- 装好之后可用 `service start` / `stop` / `restart`。同一台机器只装一份任务：要么托盘，要么网页服务。

### Docker

不再发布镜像。克隆仓库后在本机构建并启动：

```bash
cp .env.example .env
docker compose up -d --build
```

不要再在同一数据目录上装本机 `service`。容器用 compose 的 `restart: unless-stopped`。

## 升级

覆盖解压即可。数据目录会自动迁移；失败时还原 `app.db.bak-vN`。已经 `connect` 到远端的，服务端和客户端都换成这一版更稳妥。
