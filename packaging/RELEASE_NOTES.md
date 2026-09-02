# 苹果官翻监听 0.3.15

修复 0.3.14 在 Windows CI 上测试失败、导致安装包和 Release 没有打出来的问题。

## 主要变化

- **打包恢复**：Windows 测试不再依赖启动瞬间去抓「设置尚未加载」的短暂窗口，避免慢机器上误杀。
- **TUI 状态栏**：本地扫描进行中时，状态轮询不再覆盖「正在提交扫描」等进度文案。
- **测试稳定**：刷新等待设置真正加载完成；`last_success_at` 变化后等到在售列表刷新再断言。

0.3.14 的功能修复仍然有效：设置未加载前禁用开关、写入 generation、旧扫描 `ok=false` 不当成成功。

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
