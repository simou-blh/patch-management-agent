from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agent.main import create_app  # noqa: E402
from patch_agent.preflight import REQUIRED_CHECKS

ROOT = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def evidence():
    stamp = now()
    return {
        "schema_version": 1, "collected_at": stamp, "targets": ["vm-01"],
        "hosts": {"vm-01": {"status": "ok", "collected_at": stamp, "error": None,
                            "packages": {"curl:amd64": {
                                "installed": "7.88.1-10",
                                "source": {"name": "curl", "version": "7.88.1-10"},
                                "candidates": [{
                                    "version": "7.88.1-10+deb12u1",
                                    "source": {"name": "curl", "version": "7.88.1-10+deb12u1"},
                                    "origins": [{"uri": "https://repo.example.invalid/debian",
                                                 "suite": "bookworm", "component": "main"}],
                                }],
                            }}}},
    }


def cache():
    return {
        "schema_version": 1, "fetched_at": now(),
        "source": {"name": "debian-security-tracker",
                   "uri": "https://security-tracker.debian.org/tracker/data/json"},
        "release": "bookworm",
        "packages": {"curl": [{"id": "CVE-2026-0001", "status": "resolved",
                                "fixed_version": "7.88.1-10+deb12u1", "urgency": "high"}]},
    }


def preflight(status="ready"):
    stamp = now()
    checks = [{"id": check, "status": "pass", "detail": "ok", "data": {}}
              for check in REQUIRED_CHECKS]
    host = {
        "status": status, "collected_at": stamp, "checks": checks,
        "backup": {"status": "verified", "detail": "ok", "files": []},
        "recovery_artifacts": {"status": "verified", "detail": "ok", "artifacts": []},
        "blocking": [] if status == "ready" else ["candidates"],
        "error": None,
    }
    return {"schema_version": 1, "collected_at": stamp, "targets": ["vm-01"],
            "hosts": {"vm-01": dict(host)}}


def headers(tenant):
    return {"X-Tenant-Id": tenant, "Authorization": "Bearer tenant-secret"}


def activate(client, tenant):
    response = client.post("/tenant/activate", headers=headers(tenant), json={"config": {}})
    assert response.status_code == 200


def test_evidence_assess_plan_flow(client, monkeypatch):
    sent = []

    async def fake_send(tenant, api_key, event_type, severity, data, **kwargs):
        sent.append((tenant, event_type, severity, data))
        return True

    monkeypatch.setattr("agent.routers.business.send_event", fake_send)
    tenant = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    activate(client, tenant)
    assert client.post("/api/v1/evidence", headers=headers(tenant),
                       json=evidence()).status_code == 200
    assert client.post("/api/v1/advisories", headers=headers(tenant),
                       json=cache()).status_code == 200
    assessment = client.post("/api/v1/assess", headers=headers(tenant)).json()
    assert assessment["status"] == "ok"
    assert assessment["data"]["counts"]["affected"] == 1
    assert any(event[1] == "patch_affected" for event in sent)

    plan = client.post("/api/v1/plans", headers=headers(tenant),
                       json={"run_id": "tenant-run", "canary": "vm-01"}).json()
    assert plan["status"] == "ok"
    assert plan["data"]["patch"] == 1 and plan["data"]["preflight_ready"] is False

    preflight_response = client.post("/api/v1/preflight", headers=headers(tenant),
                                     json=preflight()).json()
    assert preflight_response["status"] == "ok"
    assert preflight_response["data"]["ready"] is True


def test_blocked_preflight_is_uploaded_and_alerted(client, monkeypatch):
    sent = []

    async def fake_send(tenant, api_key, event_type, severity, data, **kwargs):
        sent.append((event_type, severity, data))
        return True

    monkeypatch.setattr("agent.routers.business.send_event", fake_send)
    tenant = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    activate(client, tenant)
    response = client.post("/api/v1/preflight", headers=headers(tenant),
                           json=preflight("not_ready")).json()
    assert response["status"] == "ok"
    assert response["data"]["ready"] is False
    assert any(event[0] == "patch_preflight_blocked" for event in sent)


def test_tenant_isolation_and_purge(client, monkeypatch):
    async def fake_send(*args, **kwargs):
        return True

    monkeypatch.setattr("agent.routers.business.send_event", fake_send)
    first = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    second = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    activate(client, first)
    activate(client, second)
    assert client.post("/api/v1/evidence", headers=headers(first),
                       json=evidence()).status_code == 200
    assert client.post("/api/v1/advisories", headers=headers(first),
                       json=cache()).status_code == 200

    missing = client.post("/api/v1/assess", headers=headers(second))
    assert missing.status_code == 409
    assert missing.json()["status"] == "error"

    assert client.post("/tenant/deactivate", headers=headers(first)).status_code == 200
    assert client.get(f"/tenant/{first}/status", headers=headers(first)).status_code == 404
    assert client.get(f"/tenant/{second}/status", headers=headers(second)).status_code == 200

    root = Path(client.app.state.store.root)
    directories = [path for path in (root / "tenants").iterdir() if path.is_dir()]
    assert len(directories) == 1


def test_execution_endpoint_is_disabled_by_default(client, activated):
    response = client.post("/api/v1/runs", headers=activated, json={"run_id": "x"})
    assert response.status_code == 403
    assert response.json()["status"] == "error"


def test_execution_endpoint_reports_unconfigured_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path / "agent-data"))
    monkeypatch.setenv("AGENT_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("AGENT_OPERATOR_TOKEN", "operator-secret")
    app = create_app()
    with TestClient(app) as client:
        tenant = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
        activate(client, tenant)
        client.post("/api/v1/evidence", headers=headers(tenant), json=evidence())
        client.post("/api/v1/advisories", headers=headers(tenant), json=cache())
        client.post("/api/v1/assess", headers=headers(tenant))
        client.post("/api/v1/plans", headers=headers(tenant),
                    json={"run_id": "run-1", "canary": "vm-01"})
        response = client.post("/api/v1/runs", headers={
            **headers(tenant), "X-Operator-Token": "operator-secret"}, json={"run_id": "run-1"})
        assert response.status_code == 409  # no preflight yet
        client.post("/api/v1/preflight", headers=headers(tenant), json=preflight())
        response = client.post("/api/v1/runs", headers={
            **headers(tenant), "X-Operator-Token": "operator-secret"}, json={"run_id": "run-1"})
        assert response.status_code == 503
        assert "not configured" in response.json()["error"]
