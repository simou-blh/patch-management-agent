"""Ansible copies only the module file to the target host.

These tests make sure every library module imports without ``patch_agent``
(or anything else from this repository) and that inlined helpers stay in step
with the controller-side originals.
"""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from patch_agent import debversion
from patch_agent.policies import load_default_policy

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "playbooks/library"
MODULES = sorted(LIBRARY.glob("*.py"))


def load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_isolated", LIBRARY / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_module_imports_without_repository_packages(path, tmp_path):
    copy = tmp_path / path.name
    shutil.copy(path, copy)
    result = subprocess.run(
        [sys.executable, "-I", "-c",
         "import importlib.util, sys;"
         "s = importlib.util.spec_from_file_location('m', sys.argv[1]);"
         "s.loader.exec_module(importlib.util.module_from_spec(s))",
         str(copy)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "patch_agent" not in "".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith(("import ", "from "))
    )


VERSIONS = [
    "1.0", "1.0-1", "1.0-1+deb12u1", "1:1.0-1", "2:0.1", "1.0~rc1-1", "1.0+dfsg-2",
    "7.88.1-10", "7.88.1-10+deb12u1", "1:9.2p1-2+deb12u3", "0~20230101-1", "1.0a-1",
]


@pytest.mark.parametrize("name", ["patch_packages", "verify_packages"])
def test_inlined_debversion_matches_patch_agent(name):
    module = load(name)
    for left in VERSIONS:
        assert tuple(module.parse_version(left)) == tuple(debversion.parse_version(left))
        for right in VERSIONS:
            assert module.compare_versions(left, right) == debversion.compare_versions(left, right)
    for bad in ("", "a1.0", "1.0-", "1:", "1.0:1"):
        with pytest.raises(ValueError):
            module.parse_version(bad)


@pytest.mark.parametrize("name", ["patch_packages", "verify_packages"])
def test_module_policy_guard_accepts_repository_policy(name):
    module = load(name)
    module.validate_policy(load_default_policy())


@pytest.mark.parametrize("name", ["patch_packages", "verify_packages"])
def test_module_policy_guard_rejects_unsafe_policy(name):
    module = load(name)
    policy = json.loads((ROOT / "policies/services.json").read_text(encoding="utf-8"))
    dangling = {**policy, "packages": {"openssh-server": {"services": ["sshd-unknown"]}}}
    with pytest.raises(ValueError, match="unconfigured services"):
        module.validate_policy(dangling)
    with pytest.raises(ValueError, match="configured-only"):
        module.validate_policy({**policy, "restart_policy": "any"})
    with pytest.raises(ValueError):
        module.validate_policy(None)


@pytest.mark.parametrize("playbook, module", [
    ("patch.yml", "patch_packages"),
    ("verify.yml", "verify_packages"),
    ("rollout.yml", "patch_packages"),
    ("rollout.yml", "verify_packages"),
])
def test_playbooks_pass_controller_policy_to_modules(playbook, module):
    play = yaml.safe_load((ROOT / "playbooks" / playbook).read_text(encoding="utf-8"))[0]
    tasks = [task for task in play["tasks"] if module in task]
    assert tasks
    for task in tasks:
        assert "policies/services.json" in task[module]["policy"]
        assert "lookup(" in task[module]["policy"]


class _Exit(SystemExit):
    """Like AnsibleModule.exit_json: not caught by ``except Exception``."""


def _run_main(module, params, monkeypatch, dpkg_output):
    """Run a module's main() with a stub AnsibleModule and a fake dpkg-query."""
    import types

    captured = {}

    class StubModule:
        def __init__(self, argument_spec, supports_check_mode):
            assert set(params) <= set(argument_spec)
            self.params = {key: spec.get("default") for key, spec in argument_spec.items()}
            self.params.update(params)
            self.check_mode = True

        def exit_json(self, **kwargs):
            captured.update(kwargs)
            raise _Exit

    basic = types.ModuleType("ansible.module_utils.basic")
    basic.AnsibleModule = StubModule
    for name in ("ansible", "ansible.module_utils"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "ansible.module_utils.basic", basic)

    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=dpkg_output, stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(_Exit):
        module.main()
    return captured, commands


DPKG = "openssh-server\t1:9.2p1-2+deb12u3\tamd64\n"


def test_patch_main_runs_on_target_shape(monkeypatch):
    module = load("patch_packages")
    result, commands = _run_main(module, {
        "target": "vm-01",
        "policy": load_default_policy(),
        "candidates": {"openssh-server": {"1:9.2p1-2+deb12u4": ["amd64"]}},
        "expectations": [{"name": "openssh-server", "architecture": "amd64", "action": "patch",
                          "expected_installed": "1:9.2p1-2+deb12u3",
                          "target_version": "1:9.2p1-2+deb12u4"}],
    }, monkeypatch, DPKG)
    assert result["error"] is None, result
    # dpkg-query expands the literal \t and \n escapes in its show-format.
    assert commands == [["dpkg-query", "-W", "-f", r"${binary:Package}\t${Version}\t${Architecture}\n"]]
    package = result["packages"]["openssh-server"]
    assert package["status"] == "failed"
    assert package["error"]["code"] == "deployment_blocked"


def test_verify_main_runs_on_target_shape(monkeypatch):
    module = load("verify_packages")
    result, commands = _run_main(module, {
        "target": "vm-01",
        "policy": load_default_policy(),
        "expectations": [{"name": "openssh-server", "architecture": "amd64",
                          "expected_version": "1:9.2p1-2+deb12u3"}],
    }, monkeypatch, DPKG)
    assert result["error"] is None, result
    assert commands[0][:3] == ["dpkg-query", "-W", "-f"]
    assert result["packages"]["openssh-server"]["version_check"]["status"] == "pass"


@pytest.mark.parametrize("name", ["patch_packages", "verify_packages"])
def test_main_reports_error_for_bad_policy(name, monkeypatch):
    module = load(name)
    result, commands = _run_main(module, {
        "target": "vm-01", "policy": {"restart_policy": "any"},
    }, monkeypatch, DPKG)
    assert commands == []
    assert result["status"] == "error" and "ValueError" in result["error"]["message"]


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_module_runs_main_when_executed(path):
    # Without this Ansible reports "New-style module did not handle its own exit".
    assert 'if __name__ == "__main__":\n    main()' in path.read_text(encoding="utf-8")


def _argument_spec(module_name):
    """Read a module's AnsibleModule argument_spec keys without Ansible."""
    import ast

    tree = ast.parse((LIBRARY / f"{module_name}.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "argument_spec":
            return {key.value for key in node.value.keys}
    raise AssertionError(f"no argument_spec in {module_name}")


@pytest.mark.parametrize("playbook", sorted(p.name for p in (ROOT / "playbooks").glob("*.yml")))
def test_playbook_module_arguments_are_accepted(playbook):
    # Ansible rejects unsupported parameters; failed_when: false would hide it.
    play = yaml.safe_load((ROOT / "playbooks" / playbook).read_text(encoding="utf-8"))[0]
    for task in play["tasks"]:
        for module in [m.stem for m in MODULES]:
            if module in task:
                accepted = _argument_spec(module)
                given = set(task[module] or {})
                assert given <= accepted, (playbook, module, given - accepted)
