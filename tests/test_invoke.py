from apple_refurb_watch.argv import invoke_argv


def test_source_uses_module_flag():
    assert invoke_argv("serve", "--detach-child", frozen=False, executable="/usr/bin/python") == [
        "/usr/bin/python",
        "-m",
        "apple_refurb_watch",
        "serve",
        "--detach-child",
    ]


def test_frozen_calls_exe_directly():
    assert invoke_argv("serve", "--detach-child", frozen=True, executable=r"C:\app.exe") == [
        r"C:\app.exe",
        "serve",
        "--detach-child",
    ]
