"""Agent configuration and the tenant-facing configuration schema."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "agent-data"
DEFAULT_NOYAU_URL = "http://localhost:8000"

CONFIG_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "inventory_targets": {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
            "default": [],
            "description": "Configured host names the tenant wants assessed."
        },
        "evidence_max_age_seconds": {
            "type": "integer", "minimum": 1, "default": 86400,
            "description": "Maximum accepted age of uploaded evidence."
        },
        "alert_severity_threshold": {
            "enum": ["info", "low", "medium", "high", "critical"],
            "default": "medium",
            "description": "Minimum severity sent to the Noyau webhook."
        },
        "auto_assess": {
            "type": "boolean", "default": False,
            "description": "Reserved for scheduled assessment; no network scan is started."
        }
    }
}


def data_dir():
    return Path(os.environ.get("AGENT_DATA_DIR", DEFAULT_DATA_DIR)).resolve()


def noyau_url():
    return os.environ.get("NOYAU_URL", DEFAULT_NOYAU_URL).rstrip("/")


def execution_enabled():
    return os.environ.get("AGENT_EXECUTION_ENABLED") == "1"


def operator_token():
    return os.environ.get("AGENT_OPERATOR_TOKEN", "")


def manifest_path():
    return ROOT / "agent.manifest.json"


def load_manifest():
    return json.loads(manifest_path().read_text(encoding="utf-8"))
