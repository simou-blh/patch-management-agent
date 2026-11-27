import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Imported lazily so the core CI can collect this directory without the
    # agent runtime; the modules themselves skip when FastAPI/httpx are absent.
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from agent.main import create_app

    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path / "agent-data"))
    monkeypatch.setenv("AGENT_EXECUTION_ENABLED", "0")
    monkeypatch.setenv("AGENT_OPERATOR_TOKEN", "operator-secret")
    monkeypatch.setenv("NOYAU_URL", "http://noyau.invalid")
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def tenant():
    return "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def headers(tenant):
    return {"X-Tenant-Id": tenant, "Authorization": "Bearer tenant-secret"}


@pytest.fixture
def activated(client, headers):
    response = client.post("/tenant/activate", headers=headers, json={"config": {}})
    assert response.status_code == 200
    return headers
