import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("submit_agent_script", ROOT / "scripts/submit_agent.py")
submit_agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(submit_agent)


def manifest():
    return json.loads((ROOT / "agent.manifest.json").read_text(encoding="utf-8"))


def test_manifest_maps_to_the_kernel_submission_schema():
    payload = submit_agent.build_payload(manifest(), base_url="http://agent:9000")
    assert payload["developer_email"] == "m_laghrour@estin.dz"
    assert payload["base_url"] == "http://agent:9000"
    assert payload["manifest"]["filiere"] == "cybersecurite"
    assert payload["produces"] == [] and payload["consumes"] == []


def test_invalid_manifest_is_rejected():
    broken = manifest()
    broken["filiere"] = "unknown"
    with pytest.raises(ValidationError):
        submit_agent.build_payload(broken)
