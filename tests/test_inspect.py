import importlib.util
from pathlib import Path

import pytest
import yaml

from patch_agent.evidence import validate_evidence_contract

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "playbooks/library/inspect_packages.py"

spec = importlib.util.spec_from_file_location("inspect_packages", MODULE_PATH)
inspect_packages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspect_packages)

DPKG_SAMPLE = (
    "bash\t5.2.15-2+b7\tbash\t5.2.15-2+b7\tamd64\tii \n"
    "libc6:amd64\t2.36-9+deb12u4\tglibc\t2.36-9+deb12u4\tamd64\tii \n"
    "demo-package\t1.0-1\tdemo-source\t1.0-1\tall\tii \n"
    "removed\t1.0\t\t\tamd64\trc \n"
)

POLICY_SAMPLE = """\
bash:
  Installed: 5.2.15-2+b7
  Candidate: 5.2.15-2+b8
  Version table:
 *** 5.2.15-2+b7 100
        100 /var/lib/dpkg/status
     5.2.15-2+b7 500
        500 https://deb.debian.org/debian bookworm/main amd64 Packages
     5.2.15-2+b8 500
        500 https://deb.debian.org/debian bookworm-security/main amd64 Packages
        500 https://mirror.example.invalid/debian bookworm-security/main amd64 Packages
"""


def test_installed_packages_are_architecture_qualified_and_source_mapped():
    packages = inspect_packages.parse_dpkg_query(DPKG_SAMPLE)

    assert set(packages) == {"bash:amd64", "libc6:amd64", "demo-package:all"}
    assert packages["bash:amd64"] == {
        "installed": "5.2.15-2+b7",
        "source": {"name": "bash", "version": "5.2.15-2+b7"},
        "candidates": [],
    }
    assert packages["libc6:amd64"]["source"] == {
        "name": "glibc",
        "version": "2.36-9+deb12u4",
    }
    assert packages["demo-package:all"]["source"] == {
        "name": "demo-source",
        "version": "1.0-1",
    }


def test_policy_versions_become_candidates_with_merged_origins():
    packages = inspect_packages.collect(DPKG_SAMPLE, POLICY_SAMPLE)

    candidates = packages["bash:amd64"]["candidates"]
    assert [candidate["version"] for candidate in candidates] == [
        "5.2.15-2+b7",
        "5.2.15-2+b8",
    ]
    assert candidates[0]["origins"] == [
        {
            "uri": "https://deb.debian.org/debian",
            "suite": "bookworm",
            "component": "main",
        }
    ]
    assert candidates[1]["origins"] == [
        {
            "uri": "https://deb.debian.org/debian",
            "suite": "bookworm-security",
            "component": "main",
        },
        {
            "uri": "https://mirror.example.invalid/debian",
            "suite": "bookworm-security",
            "component": "main",
        },
    ]
    # Packages absent from the policy output keep an explicit empty candidate list.
    assert packages["libc6:amd64"]["candidates"] == []
    assert packages["demo-package:all"]["candidates"] == []


def test_candidate_origins_are_filtered_by_installed_architecture():
    policy = """\
demo-package:
  Version table:
     1.0-2 500
        500 https://repo.example.invalid/debian bookworm/main amd64 Packages
     1.0-3 500
        500 https://repo.example.invalid/debian bookworm/main i386 Packages
     1.0-4 500
        500 https://repo.example.invalid/debian bookworm/main all Packages
"""
    installed = "demo-package\t1.0-1\tdemo-source\t1.0-1\tamd64\tii \n"

    candidates = inspect_packages.collect(installed, policy)["demo-package:amd64"]["candidates"]

    assert [candidate["version"] for candidate in candidates] == ["1.0-2", "1.0-4"]


def test_architecture_independent_packages_accept_repository_architectures():
    policy = """\
demo-package:
  Version table:
     1.0-2 500
        500 https://repo.example.invalid/debian bookworm/main amd64 Packages
     1.0-3 500
        500 https://repo.example.invalid/debian bookworm/main arm64 Packages
"""
    installed = "demo-package\t1.0-1\tdemo-source\t1.0-1\tall\tii \n"

    candidates = inspect_packages.collect(installed, policy)["demo-package:all"]["candidates"]

    assert [candidate["version"] for candidate in candidates] == ["1.0-2", "1.0-3"]


def test_local_file_repository_uri_is_normalized():
    policy = """\
demo-package:
  Version table:
     1.0-2 500
        500 file:/srv/apt-mirror bookworm/main amd64 Packages
"""
    installed = "demo-package\t1.0-1\tdemo-source\t1.0-1\tamd64\tii \n"

    candidates = inspect_packages.collect(installed, policy)["demo-package:amd64"]["candidates"]

    assert candidates[0]["origins"] == [
        {"uri": "file:///srv/apt-mirror", "suite": "bookworm", "component": "main"}
    ]


@pytest.mark.parametrize("origin_line", [
    "        500 cdrom://media/cdrom bookworm/main amd64 Packages",
    "        500 https://repo.example.invalid/debian ./ amd64 Packages",
    "        100 /var/lib/dpkg/status",
])
def test_unsupported_or_incomplete_origins_do_not_create_candidates(origin_line):
    policy = f"""\
demo-package:
  Version table:
     1.0-2 500
{origin_line}
"""
    installed = "demo-package\t1.0-1\tdemo-source\t1.0-1\tamd64\tii \n"

    candidates = inspect_packages.collect(installed, policy)["demo-package:amd64"]["candidates"]

    assert candidates == []


def test_ok_host_record_matches_the_v1_evidence_contract():
    record = inspect_packages.host_record(DPKG_SAMPLE, POLICY_SAMPLE)
    envelope = {
        "schema_version": 1,
        "collected_at": record["collected_at"],
        "targets": ["vm-01"],
        "hosts": {"vm-01": record},
    }

    assert validate_evidence_contract(envelope) is None
    assert record["status"] == "ok" and record["error"] is None


def test_error_host_record_matches_the_v1_evidence_contract():
    record = inspect_packages.error_record("inspection_timeout", "Package inspection timed out")
    envelope = {
        "schema_version": 1,
        "collected_at": record["collected_at"],
        "targets": ["vm-01"],
        "hosts": {"vm-01": record},
    }

    assert validate_evidence_contract(envelope) is None
    assert record["status"] == "error" and record["packages"] == {}


def load_playbook(name):
    return yaml.safe_load((ROOT / "playbooks" / name).read_text(encoding="utf-8"))


def test_inspection_playbook_emits_v1_evidence_without_mutating_hosts():
    play = load_playbook("inspect.yml")[0]
    tasks = play["tasks"]
    names = [task["name"] for task in tasks]
    text = yaml.safe_dump(play)

    assert play["hosts"] == "all"
    assert "Collect structured package evidence" in names
    assert "inspect_packages" in tasks[0]
    assert "'schema_version': 1" in text
    assert "'targets': ansible_play_hosts_all" in text
    for mutation in (
        "ansible.builtin.apt",
        "ansible.builtin.package",
        "ansible.builtin.service",
        "ansible.builtin.command",
        "ansible.builtin.shell",
        "ansible.builtin.copy",
        "ansible.builtin.template",
    ):
        assert mutation not in text


@pytest.mark.parametrize("name", ["patch.yml", "recover.yml"])
def test_mutation_playbooks_remain_blocked(name):
    play = load_playbook(name)[0]
    failures = [
        task for task in play["tasks"] if "ansible.builtin.fail" in task
    ]
    assert failures, f"{name} must keep its implementation gate"
