# 苹果官翻监听 0.3.14

修复 0.3.13 TUI 中的设置竞态和扫描状态误判。

## 主要变化

- **设置安全**：设置未从服务端加载完成前禁用监听开关和分类开关，避免默认全关状态覆盖已有监听分类。
- **写入竞态**：监听开关与分类保存串行化，并用 generation 防止旧响应回滚新设置。
- **状态轮询**：除扫描中→结束外，`last_success_at` / `last_error` 变化也会刷新在售和动态，减少漏掉外部扫描结果。
- **旧扫描接口**：`POST /api/scan` 返回 `ok=false`（如已有扫描在进行）时不再显示为扫描完成。
- **其它**：退出时关闭尚未接管的连接客户端；规则表单拒绝 `nan` / `inf` 价格。

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
