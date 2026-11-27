#!/usr/bin/env python3
"""Smoke-test the 5 mandatory agent endpoints against a running agent.

    python scripts/agent_smoke.py --url http://localhost:9000 \
        --tenant 11111111-1111-1111-1111-111111111111 --key tenant-secret

The script never prints the tenant key and does not need the Noyau.
"""

import argparse
import json
import sys

import httpx


def check(response, expected=200):
    body = response.json()
    if response.status_code != expected:
        raise RuntimeError(f"HTTP {response.status_code}: {body}")
    if body.get("status") not in ("ok", "error"):
        raise RuntimeError(f"invalid envelope: {body}")
    return body


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:9000")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--config", default="{}")
    parser.add_argument("--keep-active", action="store_true")
    args = parser.parse_args(argv)

    base = args.url.rstrip("/")
    headers = {"X-Tenant-Id": args.tenant, "Authorization": f"Bearer {args.key}"}
    try:
        config = json.loads(args.config)
    except ValueError as exc:
        print(f"invalid --config JSON: {exc}", file=sys.stderr)
        return 2

    with httpx.Client(timeout=10) as client:
        health = check(client.get(f"{base}/health"))["data"]
        print(f"health: ok, version={health.get('version')}")
        schema = check(client.get(f"{base}/config-schema"))["data"]
        print(f"config-schema: ok, {len(schema.get('properties', {}))} fields")
        check(client.post(f"{base}/tenant/activate", headers=headers,
                          json={"config": config}))
        print("activate: ok")
        status = check(client.get(f"{base}/tenant/{args.tenant}/status",
                                  headers=headers))["data"]
        print(f"status: {status.get('state')}")
        check(client.post(f"{base}/exchange/notify", headers=headers,
                          json={"object_type": "smoke"}))
        print("exchange/notify: ok")
        if not args.keep_active:
            purged = check(client.post(f"{base}/tenant/deactivate",
                                       headers=headers))["data"]
            print(f"deactivate: ok, data_purged={purged.get('data_purged')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
