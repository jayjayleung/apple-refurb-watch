from __future__ import annotations

import subprocess
import sys

from apple_refurb_watch.daemon import windows_hidden_kwargs


def notify_os(title: str, body: str, url: str | None = None) -> None:
    text = str(body or "")[:400]
    if url:
        text = f"{text}\n{url}" if text else str(url)
    try:
        if sys.platform == "darwin":
            script = f'display notification {_osa(text)} with title {_osa(title)}'
            subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
            return
        if sys.platform == "win32":
            _windows_toast(title, text)
            return
        subprocess.run(["notify-send", str(title), text], check=False, capture_output=True)
    except Exception:  # noqa: BLE001
        return


def _osa(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _windows_toast(title: str, body: str) -> None:
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
        "$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
        "$text = $xml.GetElementsByTagName('text'); "
        f"$text.Item(0).AppendChild($xml.CreateTextNode({_ps_str(title)})) > $null; "
        f"$text.Item(1).AppendChild($xml.CreateTextNode({_ps_str(body)})) > $null; "
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('官翻监听').Show($toast)"
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            ps,
        ],
        check=False,
        capture_output=True,
        **windows_hidden_kwargs(),
    )


def _ps_str(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"
