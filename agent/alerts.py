"""Outbound webhook client for the Noyau agent-events endpoint."""

import httpx

from agent import config


async def send_event(tenant_id, api_key, event_type, severity, data, *, client=None, url=None):
    """Send one event to the Noyau. Failures are tolerated and never leak data."""
    if not api_key:
        return False
    target = (url or config.noyau_url()).rstrip("/") + "/webhooks/agent-events"
    payload = {"event_type": event_type, "severity": severity, "data": data or {}}
    headers = {"Authorization": f"Bearer {api_key}", "X-Tenant-Id": tenant_id}
    try:
        if client is not None:
            response = await client.post(target, headers=headers, json=payload)
        else:
            async with httpx.AsyncClient(timeout=5) as owned:
                response = await owned.post(target, headers=headers, json=payload)
        return 200 <= response.status_code < 300
    except Exception:  # noqa: BLE001 - the webhook must not break the request
        return False
