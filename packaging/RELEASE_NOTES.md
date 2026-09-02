# 苹果官翻监听 0.3.6

这是一次桌面界面调整：窗口标题栏已经有应用名，网页顶栏不再重复写一遍。

## 主要变化

- **桌面壳**：系统标题栏保留「官翻监听」和版本；页内品牌名隐藏，只留图标回首页。
- **版本号**：没有新版本时不再在顶栏再显示一次；有更新时仍会提示。
- **登录页**：桌面里同样去掉重复的名字和版本。浏览器不受影响。

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
