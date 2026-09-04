# 苹果官翻监听 0.3.19

桌面安装包登录后，在售商品图改由本机代理加载，不再让 webview 直接去拉苹果 CDN。直连失败时卡片不会再变成没图。

## 主要变化

- **在售图同源代理**：登录后商品缩略图走本机 `/media/thumb`，由服务端向苹果 CDN 取图并缓存，避免 webview 拦图后卡片空白。
- **空图不再冲掉已有地址**：扫描一时拿不到图时，会保留库里已有的图片地址。
- **桌面 UA 更像浏览器**：桌面壳请求带 Chrome/Edg 后缀，方便代理拉到苹果图片。

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
