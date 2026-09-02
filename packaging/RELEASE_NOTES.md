# 苹果官翻监听 0.3.8

这是一次桌面壳体验修正：原生标题栏不再和网页品牌重复，切换页面时不会短暂闪出图标或版本号，桌面初始化和 Linux 托盘也更稳定。

## 主要变化

- **桌面标题**：窗口标题保留「官翻监听」，网页首帧直接识别桌面壳并隐藏重复的品牌图标和名称。
- **版本信息**：常驻版本号移到设置页，顶栏仅在确有新版本时显示「有更新」；关闭顶栏提示后，设置页仍保留完整更新入口。
- **页面切换**：桌面使用带版本号的专用 User-Agent，跨页面或跨地址跳转时也不会先闪出浏览器版标题和版本号。
- **启动稳定性**：桌面页会等待 pywebview 桥接就绪再初始化，避免设置项偶发按浏览器模式加载。
- **Linux 托盘**：使用 X11 兼容的托盘标题，修复部分 Linux 桌面环境启动时因中文编码而退出的问题。

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
