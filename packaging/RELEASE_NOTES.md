# 苹果官翻监听 0.3.16

修复连接服务器或改回本机后，桌面窗口只出现在托盘、没有前台界面的问题。

## 主要变化

- **改连后回到前台**：连接远程服务器或改回本机时，重启后的窗口会重新显示，不再只剩托盘图标。
- **Windows 重启窗口**：不再用 `SW_HIDE` 拉起新进程，避免系统吞掉第一次显示。
- **开机自启不变**：带 `--hidden` 的开机自启仍然只留托盘。

0.3.15 的 Windows CI 打包修复仍然有效。

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
