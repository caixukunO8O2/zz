import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parents[3]
DOCKER = Path(r"D:\DevTools\DockerDesktop\resources\bin\docker.exe")


def _compose_config() -> dict[str, object]:
    completed = subprocess.run(
        [
            str(DOCKER),
            "compose",
            "-f",
            str(REPO_ROOT / "infra" / "compose.yaml"),
            "config",
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _running_port_bindings(service: str) -> dict[str, list[dict[str, str]]]:
    container = subprocess.run(
        [
            str(DOCKER),
            "compose",
            "-f",
            str(REPO_ROOT / "infra" / "compose.yaml"),
            "ps",
            "-q",
            service,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert container, f"Compose service {service} is not running"
    inspected = subprocess.run(
        [
            str(DOCKER),
            "inspect",
            container,
            "--format",
            "{{json .HostConfig.PortBindings}}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(inspected.stdout)


def test_compose_publishes_dev_ports_only_on_loopback() -> None:
    config = _compose_config()
    services = config["services"]

    assert {
        name: [
            (port["host_ip"], port["published"], port["target"])
            for port in services[name]["ports"]
        ]
        for name in ("api", "mysql", "redis")
    } == {
        "api": [("127.0.0.1", "8000", 8000)],
        "mysql": [("127.0.0.1", "3306", 3306)],
        "redis": [("127.0.0.1", "6379", 6379)],
    }


def test_running_stack_publishes_dev_ports_only_on_loopback() -> None:
    assert {
        service: _running_port_bindings(service)
        for service in ("api", "mysql", "redis")
    } == {
        "api": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8000"}]},
        "mysql": {"3306/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3306"}]},
        "redis": {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6379"}]},
    }


def test_compose_hardens_api_and_restarts_dev_services() -> None:
    config = _compose_config()
    services = config["services"]
    api = services["api"]

    assert api["user"] == "10001:10001"
    assert api["read_only"] is True
    assert api["cap_drop"] == ["ALL"]
    assert api["security_opt"] == ["no-new-privileges:true"]
    assert api["tmpfs"] == ["/tmp:size=64m,mode=1777"]
    assert {
        name: services[name]["restart"] for name in ("api", "mysql", "redis")
    } == {"api": "unless-stopped", "mysql": "unless-stopped", "redis": "unless-stopped"}


def test_compose_uses_named_volumes_for_service_data() -> None:
    config = _compose_config()
    services = config["services"]

    assert {
        service: [
            (mount["type"], mount["source"], mount["target"])
            for mount in services[service]["volumes"]
        ]
        for service in ("mysql", "redis")
    } == {
        "mysql": [("volume", "mysql_data", "/var/lib/mysql")],
        "redis": [("volume", "redis_data", "/data")],
    }
    assert {
        name: config["volumes"][name]["name"]
        for name in ("mysql_data", "redis_data")
    } == {
        "mysql_data": "infra_mysql_data_linux",
        "redis_data": "infra_redis_data",
    }
