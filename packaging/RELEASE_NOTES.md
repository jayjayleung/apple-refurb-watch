# 苹果官翻监听 0.3.20

设置页里已经保存过的通知密钥和访问口令，不再把明文填回输入框，改用 •••••••• 占位。没配过的密钥不加占位。

## 主要变化

- **已保存密钥掩码**：通知通道密钥和服务访问口令已保存时，输入框显示 ••••••••，不会回显明文。
- **没配过的不加占位**：空白输入框就表示还没填过，不会看起来像已经配好。

## 下载

目录版按系统解压即可，不必安装 Python；每个系统同时提供一个可直接运行的单文件版本。

- **Windows**：`apple-refurb-watch-windows-x86_64.zip`（需要 Edge WebView2，Win10/11 一般都有）
- **macOS Apple Silicon**：`apple-refurb-watch-macos-arm64.zip`
- **Linux / NAS**：`apple-refurb-watch-linux-x86_64.zip`

单文件版本的文件名分别为 `apple-refurb-watch-windows-x86_64.exe`、`apple-refurb-watch-macos-arm64` 和 `apple-refurb-watch-linux-x86_64`。它们可以直接复制后运行，不需要解压目录；首次启动会自动解压运行时文件。Linux/macOS 如果下载后没有执行权限，先运行 `chmod +x`。

Linux / NAS 解压后执行：

```bash
./apple-refurb-watch serve
```

默认只监听本机 `127.0.0.1:8765`。后台运行可用 `serve --detach`。需要其它设备访问时，在设置里打开远程访问并保存口令，再重启服务。升级时保留原数据目录即可，数据库 schema 无变化。
