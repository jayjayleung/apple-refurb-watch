from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

from xml.sax.saxutils import escape

from apple_refurb_watch.argv import invoke_argv
from apple_refurb_watch.paths import data_dir

SERVICE_NAME = "apple-refurb-watch"


def install_service() -> str:
    if sys.platform.startswith("linux"):
        return _install_systemd()
    if sys.platform == "darwin":
        return _install_launchd()
    if os.name == "nt":
        return _install_windows()
    return "当前系统暂不支持 service install，请用 apple-refurb-watch serve --detach"


def uninstall_service() -> str:
    if sys.platform.startswith("linux"):
        unit = _systemd_unit()
        subprocess.run(["systemctl", "--user", "disable", "--now", SERVICE_NAME], check=False)
        unit.unlink(missing_ok=True)
        return f"已移除 {unit}"
    if sys.platform == "darwin":
        plist = _launchd_plist()
        subprocess.run(["launchctl", "unload", str(plist)], check=False)
        plist.unlink(missing_ok=True)
        return f"已移除 {plist}"
    if os.name == "nt":
        subprocess.run(["schtasks", "/Delete", "/TN", SERVICE_NAME, "/F"], check=False)
        return "已尝试删除计划任务"
    return "无需卸载"


def service_status() -> str:
    if sys.platform.startswith("linux"):
        result = subprocess.run(["systemctl", "--user", "status", SERVICE_NAME], capture_output=True, text=True)
        return result.stdout or result.stderr
    if sys.platform == "darwin":
        result = subprocess.run(["launchctl", "list", SERVICE_NAME], capture_output=True, text=True)
        return result.stdout or result.stderr or "未找到 LaunchAgent"
    if os.name == "nt":
        result = subprocess.run(["schtasks", "/Query", "/TN", SERVICE_NAME], capture_output=True, text=True)
        return result.stdout or result.stderr
    return "未知"


def _systemd_unit() -> Path:
    path = Path.home() / ".config/systemd/user"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{SERVICE_NAME}.service"


def _install_systemd() -> str:
    unit = _systemd_unit()
    unit.write_text(
        dedent(
            f"""
            [Unit]
            Description=Apple CN refurbished watcher
            After=network-online.target

            [Service]
            Type=simple
            ExecStart={" ".join(invoke_argv("serve"))}
            Restart=on-failure
            RestartSec=8
            WorkingDirectory={data_dir()}

            [Install]
            WantedBy=default.target
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", SERVICE_NAME], check=False)
    return f"已写入 {unit} 并尝试 enable --now"


def _launchd_plist() -> Path:
    path = Path.home() / "Library/LaunchAgents"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"cn.apple-refurb-watch.plist"


def _install_launchd() -> str:
    plist = _launchd_plist()
    plist.write_text(
        dedent(
            f"""
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0">
            <dict>
              <key>Label</key><string>{SERVICE_NAME}</string>
              <key>ProgramArguments</key>
              <array>
                {"".join(f"<string>{escape(part)}</string>" for part in invoke_argv("serve"))}
              </array>
              <key>RunAtLoad</key><true/>
              <key>KeepAlive</key><true/>
              <key>WorkingDirectory</key><string>{data_dir()}</string>
            </dict>
            </plist>
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(["launchctl", "load", str(plist)], check=False)
    return f"已写入 {plist}"


def _install_windows() -> str:
    parts = invoke_argv("serve")
    cmd = " ".join(f'"{part}"' if " " in part else part for part in parts)
    subprocess.run(
        ["schtasks", "/Create", "/SC", "ONLOGON", "/TN", SERVICE_NAME, "/TR", cmd, "/F"],
        check=False,
    )
    return "已创建 Windows 登录计划任务 apple-refurb-watch"


def which_webview_hint() -> str:
    if sys.platform.startswith("linux"):
        gtk = shutil.which("pkg-config")
        return "Linux 桌面需要 WebKitGTK，例如：sudo apt install gir1.2-webkit2-4.1 python3-gi"
    if sys.platform == "darwin":
        return "macOS 使用系统 WebKit，一般无需额外安装。"
    return "Windows 10/11 需要 Edge WebView2 Runtime。"
