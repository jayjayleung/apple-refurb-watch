# 苹果官翻监听 0.3.18

远程可用自己的域名访问；扫描、通知和 Docker 首次启动更贴近真实结果。筛选弹层换页后还会留着，扫描完成提示大约 4 秒后消失。

## 主要变化

- **域名访问**：反代或自定义 Host 可以登记到允许的主机名，不再只认 IP / localhost。
- **远程不能清口令**：从外网打开时，不能一键清掉访问口令把服务打回本机。
- **空分类当真清空**：分类页解析成功但一件都没有时，按售罄更新，不再假装还在卖。
- **通知失败看得见**：通道发送失败会记下来，能在状态和医生检查里看到，而不是静默当成功。
- **Docker 首启要口令**：新数据目录第一次启动必须配置访问口令，避免空口令反复崩溃。
- **筛选弹层保持**：手机筛选打开后换页或改关键词，弹层不会被刷掉。
- **扫描完成提示**：顶部「扫描已完成」大约 4 秒后自动消失，地址栏里的完成标记也会清掉。

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
