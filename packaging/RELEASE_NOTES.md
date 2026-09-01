# 苹果官翻监听 0.3.3

这是一次网页与通知体验版本，在 0.3.2 的双格式安装包基础上，让商品链接、监听命中和通知测试更直接可用。

## 主要变化

- **稳定商品链接**：动态、在售、通知与系统通知改为大写 SKU 路径，不再依赖官网带 `fnode` 的短链。
- **监听命中**：规则可查看命中商品，在售在前、已售出在后；已售出可从规则中移除，在售不可删。
- **动态展示**：上新直接显示价格与规格；已下架商品在原上新行标记「已售出」。
- **通知测试**：设置页「发送测试」使用当前填写内容，空白项沿用已保存密钥，不必先保存。
- **界面**：全站说明改为官方短句；顶栏增加 GitHub 仓库入口；应用图标更新。
- **桌面打包**：Windows / macOS 窗口启动不再弹出控制台；Windows 可执行文件使用应用图标。
- **推送链接**：各通道商品地址改为可点击的「打开商品」。

## 修复

- 动态页对已下架商品也能补全内存与硬盘规格。
- 通知测试在后台线程发送，避免阻塞设置页。
- SKU 解析同时支持 `/A` 与 `/B` 后缀。

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
