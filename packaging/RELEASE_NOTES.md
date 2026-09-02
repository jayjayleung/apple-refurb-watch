# 苹果官翻监听 0.3.13

面向 SSH / 纯终端环境完善 TUI，并按场景重写 README。

## 主要变化

- **TUI**：连接、刷新、设置和规则操作改为后台执行，远程服务慢时仍可切换页面、查看帮助或退出。
- **扫描**：优先提交后台扫描任务并显示排队、运行和最终状态；只有旧服务不支持任务接口时才回退同步扫描。
- **可靠性**：刷新失败保留原表格；监听开关和分类设置失败会恢复服务端原值。
- **规则表单**：支持分类、条件/精确 SKU、维度、最低内存、最低容量和最高价，并在提交前校验输入。
- **终端体验**：新增 `1`–`4` 切换页面等快捷键；80×24 窄屏隐藏侧栏，扫描状态显示在顶栏。
- **文档**：按桌面、本机/远程服务、Docker 场景重写 README，补齐备份、诊断、开机自启和 TUI 说明。

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
