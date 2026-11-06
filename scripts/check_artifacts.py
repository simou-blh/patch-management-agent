"""Read-only JSON/YAML checks for committed configuration and playbook artifacts.

Run from CI or locally:

    python scripts/check_artifacts.py

Exit code 0 means every check passed. No network access, Ansible execution or
state writes happen here.
"""

import json
from pathlib import Path
import re
import sys
import tomllib

from jsonschema import Draft202012Validator, SchemaError
import yaml

ROOT = Path(__file__).resolve().parent.parent
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_PLAYBOOKS = {"inspect", "preflight", "patch", "verify", "recover"}
MUTATION_MODULES = {
    "apt", "ansible.builtin.apt",
    "package", "ansible.builtin.package",
    "service", "ansible.builtin.service",
    "systemd", "ansible.builtin.systemd",
    "shell", "ansible.builtin.shell",
    "copy", "ansible.builtin.copy",
    "template", "ansible.builtin.template",
    "file", "ansible.builtin.file",
}
TASK_METADATA = {
    "name", "register", "changed_when", "failed_when", "when", "become",
    "environment", "vars", "loop", "notify", "tags", "no_log",
    "ignore_errors", "until", "retries", "delay",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_schemas(root: Path) -> list[str]:
    problems = []
    paths = sorted((root / "schemas").glob("*.json"))
    if not paths:
        problems.append(f"{root / 'schemas'}: no schemas found")
    for path in paths:
        try:
            schema = read_json(path)
            Draft202012Validator.check_schema(schema)
        except (OSError, ValueError, SchemaError) as exc:
            problems.append(f"{path}: invalid JSON schema: {exc}")
            continue
        if schema.get("$schema") != DRAFT_2020_12:
            problems.append(f"{path}: $schema must be {DRAFT_2020_12}")
        if schema.get("type") != "object":
            problems.append(f"{path}: root type must be object")
        if schema.get("additionalProperties") is not False:
            problems.append(f"{path}: root additionalProperties must be false")
    return problems


def check_opencode(root: Path) -> list[str]:
    path = root / "opencode.json"
    try:
        config = read_json(path)
    except (OSError, ValueError) as exc:
        return [f"{path}: invalid JSON: {exc}"]
    problems = []
    permissions = config.get("permissions", [])
    if not permissions or permissions[0] != {"action": "*", "resource": "*", "effect": "deny"}:
        problems.append(f"{path}: first permission must be a catch-all deny")
    allows = [entry for entry in permissions[1:] if entry.get("effect") == "allow"]
    if {entry.get("action") for entry in allows} != {"fleet_*", "approval_*"}:
        problems.append(f"{path}: allowed actions must be exactly fleet_* and approval_*")
    for entry in allows:
        action = str(entry.get("action", "")).lower()
        if "approve" in action or "reject" in action:
            problems.append(f"{path}: approval decisions must not be model tools ({action})")

    servers = config.get("mcp", {}).get("servers", {})
    expected_commands = {
        "fleet": ["python", "-m", "patch_agent.osquery_mcp"],
        "approval": ["python", "-m", "patch_agent.approval_mcp"],
    }
    if set(servers) != set(expected_commands):
        problems.append(f"{path}: MCP servers must be exactly fleet and approval")
    for name, command in expected_commands.items():
        server = servers.get(name, {})
        if server.get("command") != command:
            problems.append(f"{path}: {name} command must be {' '.join(command)}")
        if (server.get("type"), server.get("protocol"), server.get("codemode")) != (
                "local", "legacy", False):
            problems.append(f"{path}: {name} must be local, legacy and codemode false")

    policies = {
        (entry.get("action"), entry.get("resource")): entry.get("effect")
        for entry in config.get("policies", [])
    }
    expected_policies = {
        ("integration.use", "mcp:*"): "deny",
        ("integration.use", "skill:*"): "deny",
        ("integration.use", "mcp:fleet"): "allow",
        ("integration.use", "mcp:approval"): "allow",
    }
    for key, effect in expected_policies.items():
        if policies.get(key) != effect:
            problems.append(f"{path}: policy {key} must be {effect}")

    agent = config.get("agents", {}).get("patch", {})
    if config.get("default_agent") != "patch":
        problems.append(f"{path}: default_agent must be patch")
    if agent.get("steps") != 3:
        problems.append(f"{path}: patch agent steps must be 3")
    return problems


def check_templates(root: Path) -> list[str]:
    path = root / "semaphore/templates.json"
    try:
        data = read_json(path)
    except (OSError, ValueError) as exc:
        return [f"{path}: invalid JSON: {exc}"]
    problems = []
    if not str(data.get("status", "")).lower().startswith("design-only"):
        problems.append(f"{path}: status must say design-only")
    templates = data.get("templates", [])
    names = [template.get("name") for template in templates]
    if names != ["inspect", "preflight", "patch", "verify", "recover"]:
        problems.append(f"{path}: templates must be inspect, preflight, patch, verify, recover")
    for template in templates:
        playbook = template.get("playbook")
        if not isinstance(playbook, str) or not (root / playbook).is_file():
            problems.append(f"{path}: {template.get('name')} playbook is missing ({playbook})")
    return problems


def check_fixtures(root: Path) -> list[str]:
    folder = root / "tests/fixtures/evidence"
    expected = {"valid.json", "partial-error.json", "invalid-missing-installed.json"}
    found = {path.name for path in folder.glob("*.json")}
    problems = []
    if expected - found:
        problems.append(f"{folder}: missing documented fixtures {sorted(expected - found)}")
    for path in sorted(folder.glob("*.json")):
        try:
            read_json(path)
        except (OSError, ValueError) as exc:
            problems.append(f"{path}: invalid JSON: {exc}")
    return problems


def check_compose(root: Path) -> list[str]:
    path = root / "compose.yml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return [f"{path}: invalid YAML: {exc}"]
    problems = []
    services = data.get("services", {}) if isinstance(data, dict) else {}
    semaphore = services.get("semaphore", {})
    image = str(semaphore.get("image", ""))
    if not re.search(r"@sha256:[0-9a-f]{64}$", image):
        problems.append(f"{path}: semaphore image must be digest-pinned (@sha256:...)")
    if "127.0.0.1:3000:3000" not in semaphore.get("ports", []):
        problems.append(f"{path}: semaphore port must be 127.0.0.1:3000:3000")
    environment = semaphore.get("environment", {})
    for key in ("SEMAPHORE_ADMIN_PASSWORD", "SEMAPHORE_ACCESS_KEY_ENCRYPTION"):
        value = str(environment.get(key, ""))
        if not value.startswith("${") or ":?" not in value:
            problems.append(f"{path}: {key} must use Compose required-variable syntax")
    upstream = services.get("semaphore-mcp", {})
    if upstream.get("profiles") != ["upstream"]:
        problems.append(f"{path}: semaphore-mcp must only use the upstream profile")
    return problems


def check_playbooks(root: Path) -> list[str]:
    folder = root / "playbooks"
    found = {path.stem for path in folder.glob("*.yml")}
    problems = []
    if found != EXPECTED_PLAYBOOKS:
        problems.append(f"{folder}: playbooks must be exactly {sorted(EXPECTED_PLAYBOOKS)}")
    for path in sorted(folder.glob("*.yml")):
        try:
            plays = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            problems.append(f"{path}: invalid YAML: {exc}")
            continue
        if not isinstance(plays, list) or not plays:
            problems.append(f"{path}: must be a nonempty list of plays")
            continue
        modules = set()
        for play in plays:
            if not isinstance(play, dict) or play.get("hosts") != "all":
                problems.append(f"{path}: every play must target hosts: all")
                continue
            for task in play.get("tasks", []):
                if isinstance(task, dict):
                    modules.update(key for key in task if key not in TASK_METADATA)
        name = path.stem
        if name in {"preflight", "patch", "recover"} and "ansible.builtin.fail" not in modules:
            problems.append(f"{path}: must keep its ansible.builtin.fail gate")
        if name in {"patch", "recover"}:
            for play in plays:
                if not isinstance(play, dict):
                    continue
                if play.get("serial") != 1 or play.get("any_errors_fatal") is not True:
                    problems.append(f"{path}: must keep serial: 1 and any_errors_fatal: true")
        if name in {"inspect", "verify"}:
            forbidden = modules & MUTATION_MODULES
            if forbidden:
                problems.append(f"{path}: read-only playbook must not use {sorted(forbidden)}")
    return problems


def check_workflow(root: Path) -> list[str]:
    path = root / ".github/workflows/ci.yml"
    if not path.is_file():
        return [f"{path}: CI workflow is missing"]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return [f"{path}: invalid YAML: {exc}"]
    problems = []
    text = path.read_text(encoding="utf-8")
    if "pull_request" not in text:
        problems.append(f"{path}: must run on pull requests")
    permissions = data.get("permissions") if isinstance(data, dict) else None
    if not isinstance(permissions, dict) or permissions.get("contents") != "read":
        problems.append(f"{path}: permissions must be contents: read")
    return problems


def check_pins(root: Path) -> list[str]:
    path = root / ".github/workflows/ci.yml"
    if not path.is_file():
        return []
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    pins = list(pyproject.get("project", {}).get("dependencies", []))
    pins += list(pyproject.get("dependency-groups", {}).get("dev", []))
    workflow = path.read_text(encoding="utf-8")
    return [
        f"{path}: install step is missing pinned dependency {pin!r}"
        for pin in pins
        if pin not in workflow
    ]


def check_all(root=ROOT) -> list[str]:
    root = Path(root)
    problems = []
    problems += check_schemas(root)
    problems += check_opencode(root)
    problems += check_templates(root)
    problems += check_fixtures(root)
    problems += check_compose(root)
    problems += check_playbooks(root)
    problems += check_workflow(root)
    problems += check_pins(root)
    return problems


def main(argv=None, *, root=ROOT) -> int:
    problems = check_all(root)
    if problems:
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        print(f"{len(problems)} artifact problem(s) found.", file=sys.stderr)
        return 1
    print("All JSON/YAML artifacts passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
