# 苹果官翻指定配置监听

盯住 [苹果中国认证翻新](https://www.apple.com.cn/shop/refurbished) 里你选定的配置。上新时推送到 Bark / 微信 / 飞书 / 钉钉 / Telegram / 邮件。

一个后台 daemon 独占扫描和写库；网页、桌面窗口、CLI、TUI 都通过本地 API 操作。

## 安装

需要 Python 3.11+。

```bash
cd apple-refurb-watch
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

可选：

```bash
pip install -e ".[tui]"       # 终端界面
pip install -e ".[desktop]"   # 桌面窗口
pip install -e ".[all]"
```

Linux 桌面窗口还需要 WebKitGTK，例如 Debian/Ubuntu：

```bash
sudo apt install gir1.2-webkit2-4.1 python3-gi
```

Windows 需要 Edge WebView2；macOS 用系统 WebKit。

## 用法

```bash
# 前台启动（网页 + 定时扫描）
apple-refurb-watch serve

# 后台
apple-refurb-watch serve --detach

# 浏览器打开
# http://127.0.0.1:8765

# 桌面窗口
apple-refurb-watch desktop

# 终端界面
apple-refurb-watch tui

# 命令行
apple-refurb-watch scan
apple-refurb-watch list --q "MacBook Pro"
apple-refurb-watch watch add --name "14 MBP" --all-of "14 英寸,MacBook Pro,M5 Pro" --min-ram 24 --max-price 18000
apple-refurb-watch watch ls
apple-refurb-watch notify-test
apple-refurb-watch stop
```

数据目录：

```bash
apple-refurb-watch home
```

默认 `platformdirs` 用户数据目录，也可用环境变量 `APPLE_REFURB_WATCH_HOME` 覆盖。

## 网页里做什么

1. 点「立即扫描」拉当前在售
2. 在卡片上点「按配置听」或「精确 SKU」
3. 到「设置」打开通知通道并「发送测试通知」
4. 需要手机访问时，打开「允许局域网访问」并设口令（默认只绑 127.0.0.1）

首次扫描只建基线，不会把当前库存全部推送一遍。某台机器卖掉再重新上架才会再通知。

## 开机自启

```bash
apple-refurb-watch service install
apple-refurb-watch service status
apple-refurb-watch service uninstall
```

- Linux：systemd --user
- macOS：LaunchAgent
- Windows：登录计划任务

改端口或绑定地址后需要重启 serve。

## 打包

同一源码，三个系统分别出包（不是一个 exe 通吃）：

```bash
pip install pyinstaller
pyinstaller packaging/apple-refurb-watch.spec
```

## 礼貌抓取

默认 5 分钟一轮。详情页只在规则需要内存/硬盘且列表里缺字段时才补抓，并带间隔。请不要把间隔改到过于频繁。

## 测试

```bash
pytest
```
