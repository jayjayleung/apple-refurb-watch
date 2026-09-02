# 苹果官翻监听 0.3.7

这是一次桌面体验修正：更新提示不再被旧缓存挡住，切导航不再闪出版本号，设置页进页也不再被拽到下方。

## 主要变化

- **更新提示**：桌面启动会重新问 GitHub；缓存里的版本比正在运行的还旧时也会重拉。页面用桌面自己的版本号对照最新 Release，旧壳连到新服务器也能提示。
- **导航**：第一次进桌面后记住状态，之后切换「在售 / 监听 / 动态 / 设置」时不再先闪出版本号。
- **设置页**：已启用的通知通道进页默认展开时，不再把「发送测试」滚到视野中间。

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
