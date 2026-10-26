import asyncio
import subprocess
from unittest.mock import patch

import pytest

from patch_agent.osquery import collect, load_hosts, query_host


def test_unknown_input_is_rejected_before_ssh():
    hosts = load_hosts()
    calls = []
    for selected, query in [(["unknown"], "packages"), (["vm-01"], "SELECT * FROM users"),
                            ([], "packages"), (["vm-01", "vm-01"], "packages")]:
        with pytest.raises(ValueError):
            asyncio.run(collect(selected, query, hosts=hosts, query_runner=lambda *a: calls.append(a)))
    assert calls == []


def test_per_host_failures_do_not_erase_success():
    hosts = load_hosts()

    def fake(host, query):
        if host["address"].endswith("12"):
            return {"rows": [], "error": "SSH query timed out"}
        return {"rows": [{"name": "Debian"}], "error": None}

    result = asyncio.run(collect(list(hosts), "os_version", hosts=hosts, query_runner=fake))
    assert len(result["hosts"]) == 3
    assert result["hosts"]["vm-02"]["error"]
    assert result["hosts"]["vm-03"]["rows"] == [{"name": "Debian"}]


@pytest.mark.parametrize("output", ["not JSON", "{}", '["wrong row type"]'])
def test_malformed_remote_output_is_an_error(output):
    with patch("patch_agent.osquery.subprocess.run", return_value=subprocess.CompletedProcess([], 0, output)):
        assert query_host(load_hosts()["vm-01"], "packages")["error"]


def test_ssh_timeout_is_a_host_error():
    with patch("patch_agent.osquery.subprocess.run", side_effect=subprocess.TimeoutExpired("ssh", 30)):
        assert "timed out" in query_host(load_hosts()["vm-01"], "packages")["error"]
