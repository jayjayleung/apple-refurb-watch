from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _prepare_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "docker-up.sh", root / "scripts" / "docker-up.sh")
    shutil.copy(REPO / "scripts" / "lib.sh", root / "scripts" / "lib.sh")
    shutil.copy(REPO / ".env.example", root / ".env.example")
    shutil.copy(REPO / "docker-compose.yml", root / "docker-compose.yml")
    return root


def _fake_docker(bin_dir: Path, log_path: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/bash\n"
        f'echo docker "$@" >> "{log_path}"\n'
        'if [[ "$1" == compose && "$2" == version ]]; then exit 0; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)


def _run_docker_up(root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    if shutil.which("bash") is None:
        pytest.skip("需要 bash 运行 docker-up.sh")
    return subprocess.run(
        ["bash", str(root / "scripts" / "docker-up.sh")],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _env_with_fake_docker(tmp_path: Path) -> tuple[dict[str, str], Path]:
    log_path = tmp_path / "docker.log"
    bin_dir = tmp_path / "bin"
    _fake_docker(bin_dir, log_path)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env.pop("APPLE_REFURB_WATCH_ACCESS_TOKEN", None)
    return env, log_path


def test_docker_up_refuses_empty_data_without_token(tmp_path) -> None:
    root = _prepare_project(tmp_path)
    env, log_path = _env_with_fake_docker(tmp_path)
    result = _run_docker_up(root, env)
    assert result.returncode == 1
    assert "访问口令" in (result.stderr or "")
    assert "APPLE_REFURB_WATCH_ACCESS_TOKEN" in (result.stderr or "")
    assert not log_path.exists() or "compose up" not in log_path.read_text(encoding="utf-8")


def test_docker_up_allows_token_and_existing_db(tmp_path) -> None:
    root = _prepare_project(tmp_path)
    env, log_path = _env_with_fake_docker(tmp_path)
    (root / ".env").write_text("APPLE_REFURB_WATCH_ACCESS_TOKEN=secret\n", encoding="utf-8")

    result = _run_docker_up(root, env)
    assert result.returncode == 0, result.stderr
    assert "compose up" in log_path.read_text(encoding="utf-8")

    log_path.write_text("", encoding="utf-8")
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "app.db").write_bytes(b"")
    (root / ".env").write_text("ARW_BIND=127.0.0.1\nARW_PORT=8765\n", encoding="utf-8")
    result = _run_docker_up(root, env)
    assert result.returncode == 0, result.stderr
    assert "compose up" in log_path.read_text(encoding="utf-8")


def test_compose_and_env_example_support_puid_and_token() -> None:
    example = (REPO / ".env.example").read_text(encoding="utf-8")
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    token_lines = [ln for ln in example.splitlines() if "APPLE_REFURB_WATCH_ACCESS_TOKEN=" in ln]
    assert token_lines
    assert not token_lines[0].lstrip().startswith("#")
    assert "只在其它机器访问才需要口令" not in example
    assert "即使只在本机浏览器打开也需要" in example
    assert "PUID=1000" in example
    assert "PGID=1000" in example
    assert 'user: "${PUID:-1000}:${PGID:-1000}"' in compose
