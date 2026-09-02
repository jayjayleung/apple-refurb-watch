# 苹果官翻监听 0.3.4

这是一次桌面体验版本：能看见当前版本，有新包时提示去下载，并去掉 Windows 上多出来的黑框。

## 主要变化

- **版本号**：顶栏、登录页和桌面窗口标题显示当前版本。
- **更新提示**：对照 GitHub 最新 Release，不自动替换安装包。网页点「查看更新」打开发行说明；桌面壳改为「打开下载页」。关闭后同一版本不再弹出，更新的版本会再提示。
- **Windows**：系统通知、计划任务和托盘隐藏启动不再闪控制台黑框。

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
