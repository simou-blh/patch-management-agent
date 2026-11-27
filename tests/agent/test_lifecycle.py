import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def assert_ok(response, status=200):
    assert response.status_code == status
    body = response.json()
    assert body["status"] == "ok" and body["error"] is None
    return body["data"]


def assert_error(response, status):
    assert response.status_code == status
    body = response.json()
    assert body["status"] == "error" and body["data"] is None and body["error"]


def test_health_envelope(client):
    data = assert_ok(client.get("/health"))
    assert data["version"] == "1.0.0"
    assert data["execution_enabled"] is False
    assert isinstance(data["uptime_seconds"], int)


def test_config_schema_is_an_object_schema(client):
    schema = assert_ok(client.get("/config-schema"))
    assert schema["type"] == "object"
    assert "evidence_max_age_seconds" in schema["properties"]


def test_activate_requires_tenant_and_token(client):
    assert_error(client.post("/tenant/activate", json={"config": {}}), 400)
    assert_error(client.post("/tenant/activate", headers={"X-Tenant-Id": "t1"},
                             json={"config": {}}), 401)


def test_activate_rejects_unknown_config_fields(client, headers):
    assert_error(client.post("/tenant/activate", headers=headers,
                             json={"config": {"unexpected": True}}), 400)


def test_lifecycle_status_and_purge(client, headers):
    assert_ok(client.post("/tenant/activate", headers=headers,
                          json={"config": {"evidence_max_age_seconds": 3600}}))
    status = assert_ok(client.get(f"/tenant/{headers['X-Tenant-Id']}/status",
                                  headers=headers))
    assert status["state"] == "running"
    assert status["execution_enabled"] is False

    wrong = {"X-Tenant-Id": "22222222-2222-2222-2222-222222222222",
             "Authorization": "Bearer tenant-secret"}
    assert_error(client.get("/tenant/22222222-2222-2222-2222-222222222222/status",
                           headers=wrong), 404)

    bad_key = {"X-Tenant-Id": headers["X-Tenant-Id"],
               "Authorization": "Bearer wrong"}
    assert_error(client.get(f"/tenant/{headers['X-Tenant-Id']}/status", headers=bad_key), 403)

    data = assert_ok(client.post("/tenant/deactivate", headers=headers))
    assert data["data_purged"] is True
    assert_error(client.get(f"/tenant/{headers['X-Tenant-Id']}/status", headers=headers), 404)


def test_exchange_notify_is_safe_noop(client, activated):
    data = assert_ok(client.post("/exchange/notify", headers=activated,
                                 json={"object_type": "anything"}))
    assert data["processed"] is False


def test_errors_use_the_standard_envelope(client):
    assert_error(client.get("/does-not-exist"), 404)
    assert_error(client.post("/tenant/activate", headers={"X-Tenant-Id": "t1"},
                             json={"config": {"bad": 1}}), 401)


def test_manifest_matches_the_teacher_schema():
    manifest = json.loads((ROOT / "agent.manifest.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/agent.manifest.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    assert manifest["filiere"] == "cybersecurite"
    assert manifest["produces"] == [] and manifest["consumes"] == []
    assert manifest["endpoints"]["health"] == "/health"
