# 苹果官翻监听 0.3.17

通知和页面里的商品链接改为官网小写短路径，不再带一次性 `fnode`。安装说明按使用场景重新整理。

## 主要变化

- **商品链接**：推送、动态、在售改为 `https://www.apple.com.cn/shop/product/g1mk7ch/a` 这类小写短链，去掉列表页的 `fnode`。
- **安装说明**：README 按桌面安装包、Linux 服务、远程连接、Docker、源码分开写，避免几种安装方式混在一起。

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
