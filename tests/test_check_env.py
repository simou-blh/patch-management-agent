import json
import subprocess

from scripts.check_env import check_semaphore, check_ssh


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = {} if payload is None else payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_semaphore_ping_failure_is_reported_safely(capsys):
    def opener(url, timeout):
        raise OSError("connection refused")

    assert check_semaphore("http://127.0.0.1:3000", opener=opener) is False
    output = capsys.readouterr().out
    assert "FAIL semaphore ping" in output
    assert "Traceback" not in output


def test_semaphore_auth_is_skipped_without_token(capsys):
    calls = []

    def opener(url, timeout):
        calls.append(url)
        return FakeResponse(200, {})

    assert check_semaphore("http://127.0.0.1:3000", token="", opener=opener) is True
    output = capsys.readouterr().out
    assert "SKIP semaphore auth" in output
    assert calls == ["http://127.0.0.1:3000/api/ping"]


def test_semaphore_auth_never_prints_token(capsys):
    seen = {}

    def opener(request, timeout):
        if isinstance(request, str):
            return FakeResponse(200, {})
        seen["auth"] = request.get_header("Authorization")
        return FakeResponse(200, [{"id": 1}, {"id": 2}])

    assert check_semaphore(
        "http://127.0.0.1:3000", token="secret-token-value", opener=opener) is True
    output = capsys.readouterr().out
    assert "2 project(s) visible" in output
    assert "secret-token-value" not in output
    assert seen["auth"] == "Bearer secret-token-value"


def test_ssh_check_reports_each_configured_host(capsys):
    hosts = {
        "vm-01": {"address": "192.168.56.11", "user": "vagrant",
                  "key": "~/.ssh/patch-lab/vm-01"},
        "vm-02": {"address": "192.168.56.12", "user": "vagrant",
                  "key": "~/.ssh/patch-lab/vm-02"},
    }

    def runner(command, capture_output=True, text=True, timeout=20):
        reachable = any("192.168.56.12" in part for part in command)
        return subprocess.CompletedProcess(command, 1 if reachable else 0, "", "")

    assert check_ssh(hosts, runner=runner) is False
    output = capsys.readouterr().out
    assert "OK ssh vm-01" in output
    assert "FAIL ssh vm-02" in output
