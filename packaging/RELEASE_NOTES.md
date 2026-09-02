# 苹果官翻监听 0.3.9

这是一次设置页文案精简：去掉复述控件本身的说明，页面更干净；即时生效和需保存的区别仍由开关旁标记说明。

## 主要变化

- **设置页**：去掉页头、分类、开机自启和端口上的重复说明，只保留「MacBook Pro 与 Air 请在 Mac 中选择」和当前绑定地址。
- **状态提示**：电脑通知和开机自启空闲时不再写「已开启/未开启」，出错或操作后才出现。

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
