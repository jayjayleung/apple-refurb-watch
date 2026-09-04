from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

from xml.sax.saxutils import escape

from apple_refurb_watch.argv import invoke_argv, is_frozen
from apple_refurb_watch.daemon import windows_hidden_kwargs
from apple_refurb_watch.paths import data_dir

SERVICE_NAME = "apple-refurb-watch"


def _subprocess_run(cmd: list[str], **kwargs):
    merged = windows_hidden_kwargs()
    merged.update(kwargs)
    return subprocess.run(cmd, **merged)


def desktop_autostart_preferred(*, frozen: bool | None = None, platform: str | None = None) -> bool:
    frozen = is_frozen() if frozen is None else frozen
    platform = sys.platform if platform is None else platform
    return bool(frozen) and platform in {"win32", "darwin"}


def autostart_argv(
    *,
    desktop: bool | None = None,
    frozen: bool | None = None,
    platform: str | None = None,
    executable: str | None = None,
) -> list[str]:
    """开机拉起的命令：Win/mac 桌面包走托盘，其它走 serve。"""
    frozen = is_frozen() if frozen is None else frozen
    platform = sys.platform if platform is None else platform
    if desktop is None:
        desktop = desktop_autostart_preferred(frozen=frozen, platform=platform)
    if desktop:
        return invoke_argv("desktop", "--hidden", frozen=frozen, executable=executable)
    return invoke_argv("serve", frozen=frozen, executable=executable)


def autostart_status(*, desktop: bool | None = None) -> dict:
    if desktop is None:
        desktop = desktop_autostart_preferred()
    return {
        "installed": is_service_installed(),
        "kind": "tray" if desktop else "serve",
        "command": autostart_argv(desktop=desktop),
    }


def set_autostart(enabled: bool, *, desktop: bool | None = None) -> dict:
    if enabled:
        message = install_service(desktop=desktop)
    else:
        message = uninstall_service()
    info = autostart_status(desktop=desktop)
    info["ok"] = True
    info["message"] = message
    return info


def install_service(*, desktop: bool | None = None) -> str:
    argv = autostart_argv(desktop=desktop)
    if sys.platform.startswith("linux"):
        return _install_systemd(argv)
    if sys.platform == "darwin":
        return _install_launchd(argv)
    if os.name == "nt":
        return _install_windows(argv)
    return "当前系统暂不支持 service install，请用 apple-refurb-watch serve --detach"


def uninstall_service() -> str:
    if sys.platform.startswith("linux"):
        unit = _systemd_unit()
        _subprocess_run(["systemctl", "--user", "disable", "--now", SERVICE_NAME], check=False)
        unit.unlink(missing_ok=True)
        return f"已移除 {unit}"
    if sys.platform == "darwin":
        plist = _launchd_plist()
        _subprocess_run(["launchctl", "unload", str(plist)], check=False)
        plist.unlink(missing_ok=True)
        return f"已移除 {plist}"
    if os.name == "nt":
        _subprocess_run(["schtasks", "/Delete", "/TN", SERVICE_NAME, "/F"], check=False)
        return "已尝试删除计划任务"
    return "无需卸载"


def service_status() -> str:
    if sys.platform.startswith("linux"):
        result = _subprocess_run(["systemctl", "--user", "status", SERVICE_NAME], capture_output=True, text=True)
        return result.stdout or result.stderr
    if sys.platform == "darwin":
        result = _subprocess_run(["launchctl", "list", SERVICE_NAME], capture_output=True, text=True)
        return result.stdout or result.stderr or "未找到 LaunchAgent"
    if os.name == "nt":
        result = _subprocess_run(["schtasks", "/Query", "/TN", SERVICE_NAME], capture_output=True, text=True)
        return result.stdout or result.stderr
    return "未知"


def is_service_installed() -> bool:
    if sys.platform.startswith("linux"):
        return _systemd_unit().exists()
    if sys.platform == "darwin":
        return _launchd_plist().exists()
    if os.name == "nt":
        result = _subprocess_run(["schtasks", "/Query", "/TN", SERVICE_NAME], capture_output=True)
        return result.returncode == 0
    return False


def control_commands(
    action: str,
    *,
    platform: str | None = None,
    plist: str | None = None,
) -> list[list[str]]:
    """start / stop / restart 对应的系统命令。restart 可能是两条。"""
    if action not in {"start", "stop", "restart"}:
        raise ValueError(action)
    platform = sys.platform if platform is None else platform
    if platform.startswith("linux"):
        return [["systemctl", "--user", action, SERVICE_NAME]]
    if platform == "darwin":
        path = plist if plist is not None else str(_launchd_plist())
        if action == "start":
            return [["launchctl", "load", path]]
        if action == "stop":
            return [["launchctl", "unload", path]]
        return [["launchctl", "unload", path], ["launchctl", "load", path]]
    if platform == "win32":
        if action == "start":
            return [["schtasks", "/Run", "/TN", SERVICE_NAME]]
        if action == "stop":
            return [["schtasks", "/End", "/TN", SERVICE_NAME]]
        return [["schtasks", "/End", "/TN", SERVICE_NAME], ["schtasks", "/Run", "/TN", SERVICE_NAME]]
    raise RuntimeError("当前系统暂不支持 service start/stop，请用 apple-refurb-watch serve")


def start_service() -> str:
    return _control("start")


def stop_service() -> str:
    return _control("stop")


def restart_service() -> str:
    return _control("restart")


def _control(action: str) -> str:
    if not is_service_installed():
        raise RuntimeError("尚未安装开机任务。请先 apple-refurb-watch service install")
    return _run_control_commands(action, control_commands(action))


def _ignore_control_error(action: str, text: str) -> bool:
    low = text.lower()
    if action == "start":
        return any(token in low for token in ("already loaded", "already running", "already started"))
    if action == "stop":
        return any(token in low for token in ("not loaded", "not running", "not started", "has not yet started"))
    return False


def _run_control_commands(action: str, commands: list[list[str]]) -> str:
    for index, cmd in enumerate(commands):
        result = _subprocess_run(cmd, capture_output=True, text=True)
        text = f"{result.stderr or ''}{result.stdout or ''}".strip()
        if result.returncode == 0:
            continue
        step = "stop" if action == "restart" and index == 0 else action
        if _ignore_control_error(step, text):
            continue
        raise RuntimeError(text or f"{' '.join(cmd)} 失败")
    labels = {"start": "已启动", "stop": "已停止", "restart": "已重启"}
    return labels.get(action, "已执行")


def _systemd_unit() -> Path:
    path = Path.home() / ".config/systemd/user"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{SERVICE_NAME}.service"


def _systemd_assign(key: str, value: str) -> str:
    text = str(value)
    if any(ch.isspace() for ch in text) or any(ch in text for ch in '"\\'):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{escaped}"'
    return f"{key}={text}"


def _install_systemd(argv: list[str]) -> str:
    unit = _systemd_unit()
    home = str(data_dir())
    exec_start = " ".join(shlex.quote(part) for part in argv)
    unit.write_text(
        dedent(
            f"""
            [Unit]
            Description=Apple CN refurbished watcher
            After=network-online.target

            [Service]
            Type=simple
            Environment={_systemd_assign("APPLE_REFURB_WATCH_HOME", home)}
            ExecStart={exec_start}
            Restart=on-failure
            RestartSec=8
            WorkingDirectory={shlex.quote(home)}

            [Install]
            WantedBy=default.target
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    _subprocess_run(["systemctl", "--user", "daemon-reload"], check=False)
    _subprocess_run(["systemctl", "--user", "enable", "--now", SERVICE_NAME], check=False)
    return f"已写入 {unit} 并尝试 enable --now"


def _launchd_plist() -> Path:
    path = Path.home() / "Library/LaunchAgents"
    path.mkdir(parents=True, exist_ok=True)
    return path / "cn.apple-refurb-watch.plist"


def _install_launchd(argv: list[str]) -> str:
    plist = _launchd_plist()
    home = escape(str(data_dir()))
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
                {"".join(f"<string>{escape(part)}</string>" for part in argv)}
              </array>
              <key>EnvironmentVariables</key>
              <dict>
                <key>APPLE_REFURB_WATCH_HOME</key>
                <string>{home}</string>
              </dict>
              <key>RunAtLoad</key><true/>
              <key>KeepAlive</key><true/>
              <key>WorkingDirectory</key><string>{home}</string>
            </dict>
            </plist>
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    _subprocess_run(["launchctl", "load", str(plist)], check=False)
    return f"已写入 {plist}"


def _install_windows(argv: list[str]) -> str:
    cmd = " ".join(f'"{part}"' if " " in part else part for part in argv)
    _subprocess_run(
        ["schtasks", "/Create", "/SC", "ONLOGON", "/TN", SERVICE_NAME, "/TR", cmd, "/F"],
        check=False,
    )
    return "已创建 Windows 登录计划任务 apple-refurb-watch"


def which_webview_hint() -> str:
    if sys.platform.startswith("linux"):
        return "Linux 桌面需要 WebKitGTK，例如：sudo apt install gir1.2-webkit2-4.1 python3-gi"
    if sys.platform == "darwin":
        return "macOS 使用系统 WebKit，一般无需额外安装。"
    return "Windows 10/11 需要 Edge WebView2 Runtime。"
