# 苹果官翻监听 0.3.11

这是一次设置文案整理，并修复 Windows 无控制台安装包从远程改回本机时崩溃、失败后占用的问题。

## 主要变化

- **设置页**：开关和按钮用语与区块标题对齐（定时扫描、电脑通知、发送测试、开机自启）；版本写成「服务」「桌面」。
- **监听分类**：去掉「MacBook Pro 与 Air 请在 Mac 中选择」。
- **桌面**：无控制台安装包改回本机时不再因日志着色崩溃；启动失败会释放锁，连不上时关窗退出不占托盘。

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
