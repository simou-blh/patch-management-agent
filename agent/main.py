"""FastAPI application factory for the teacher-platform agent."""

import json
import time
from pathlib import Path

from fastapi import FastAPI
from jsonschema import Draft202012Validator

from agent import config
from agent.contract import install_error_handlers
from agent.routers import business, lifecycle
from agent.state import TenantStore

MANIFEST_SCHEMA = json.loads(
    (config.ROOT / "schemas/agent.manifest.schema.json").read_text(encoding="utf-8"))
MANIFEST_VALIDATOR = Draft202012Validator(MANIFEST_SCHEMA)


def validate_manifest(manifest):
    MANIFEST_VALIDATOR.validate(manifest)
    return manifest


def create_app():
    manifest = validate_manifest(config.load_manifest())
    app = FastAPI(
        title=manifest["name"],
        description=manifest["description"],
        version=manifest["version"],
    )
    app.state.manifest = manifest
    app.state.version = manifest["version"]
    app.state.started = time.time()
    app.state.store = TenantStore(config.data_dir())
    app.state.execution_enabled = config.execution_enabled()
    app.state.operator_token = config.operator_token()
    app.state.runner_factory = None

    app.include_router(lifecycle.router)
    app.include_router(business.router)
    install_error_handlers(app)
    return app
