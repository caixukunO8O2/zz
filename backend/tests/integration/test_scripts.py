import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[3]
POWERSHELL = shutil.which("pwsh")


@pytest.fixture
def script_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (repo / "backend" / "tests").mkdir(parents=True)
    (repo / "infra").mkdir()
    (repo / ".env.example").write_text("APP_MODE=mock\n", encoding="utf-8")
    (repo / "infra" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    for name in ("env.ps1", "dev.ps1", "test.ps1"):
        shutil.copy2(REPO_ROOT / "scripts" / name, scripts / name)
    return repo


def _run_script(
    script: Path,
    *,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-File", str(script)],
        cwd=cwd,
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "fake-docker.cmd"
    log = tmp_path / "docker.log"
    executable.write_text(
        """@echo off
echo %*>>"%XIANZHI_TEST_DOCKER_LOG%"
echo %* | findstr /C:"--wait" >nul
if not errorlevel 1 if not "%XIANZHI_TEST_WAIT_EXIT%"=="" exit /b %XIANZHI_TEST_WAIT_EXIT%
exit /b 0
""",
        encoding="utf-8",
    )
    return executable, log


def _fake_python(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "fake-python.ps1"
    log = tmp_path / "python.log"
    executable.write_text(
        """param([Parameter(ValueFromRemainingArguments=$true)][string[]]$PythonArgs)
$Invocation = (Get-Location).Path + '|' + ($PythonArgs -join '|')
Add-Content -LiteralPath $env:XIANZHI_TEST_PYTHON_LOG -Value $Invocation
if ($env:XIANZHI_TEST_PYTHON_EXIT) { exit [int]$env:XIANZHI_TEST_PYTHON_EXIT }
exit 0
""",
        encoding="utf-8",
    )
    return executable, log


def test_dev_script_preserves_existing_env_and_waits_for_api_health(
    script_repo: Path,
    tmp_path: Path,
) -> None:
    docker, log = _fake_docker(tmp_path)
    env_file = script_repo / ".env"
    env_file.write_text("LOCAL_SENTINEL=keep-me\n", encoding="utf-8")

    completed = _run_script(
        script_repo / "scripts" / "dev.ps1",
        cwd=tmp_path,
        environment={
            "XIANZHI_DOCKER_EXE": str(docker),
            "XIANZHI_TEST_DOCKER_LOG": str(log),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert env_file.read_text(encoding="utf-8") == "LOCAL_SENTINEL=keep-me\n"
    calls = log.read_text(encoding="utf-8").splitlines()
    assert calls[-1].endswith("up -d --wait --wait-timeout 120 api")
    assert "API 文档：http://localhost:8000/docs" in completed.stdout


def test_dev_script_propagates_health_wait_failure_without_printing_success(
    script_repo: Path,
    tmp_path: Path,
) -> None:
    docker, log = _fake_docker(tmp_path)

    completed = _run_script(
        script_repo / "scripts" / "dev.ps1",
        cwd=tmp_path,
        environment={
            "XIANZHI_DOCKER_EXE": str(docker),
            "XIANZHI_TEST_DOCKER_LOG": str(log),
            "XIANZHI_TEST_WAIT_EXIT": "17",
        },
    )

    assert completed.returncode != 0
    assert "API 文档" not in completed.stdout


def test_test_script_resolves_paths_from_repo_and_propagates_exit(
    script_repo: Path,
    tmp_path: Path,
) -> None:
    python, log = _fake_python(tmp_path)
    caller = tmp_path / "unrelated-cwd"
    caller.mkdir()
    environment = {
        "XIANZHI_PYTHON_EXE": str(python),
        "XIANZHI_TEST_PYTHON_LOG": str(log),
    }

    succeeded = _run_script(
        script_repo / "scripts" / "test.ps1",
        cwd=caller,
        environment=environment,
    )

    assert succeeded.returncode == 0, succeeded.stderr
    invocation = log.read_text(encoding="utf-8").strip()
    assert invocation == (
        f"{script_repo}|-m|pytest|{script_repo / 'backend' / 'tests'}|-q"
    )

    failed = _run_script(
        script_repo / "scripts" / "test.ps1",
        cwd=caller,
        environment={**environment, "XIANZHI_TEST_PYTHON_EXIT": "7"},
    )
    assert failed.returncode != 0
