#!/usr/bin/env python3
"""Submit the agent manifest to the teacher Noyau.

The Noyau's ``AgentManifestSubmission`` model expects flattened fields, while
``agent.manifest.json`` is nested. This adapter performs that mapping.

    python scripts/submit_agent.py --kernel http://localhost:8000 \
        --manifest agent.manifest.json --base-url http://localhost:9000
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas/agent.manifest.schema.json").read_text(encoding="utf-8"))


def build_payload(manifest, base_url=None):
    Draft202012Validator(SCHEMA).validate(manifest)
    return {
        "slug": manifest["slug"],
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "filiere": manifest["filiere"],
        "category": manifest["category"],
        "developer_email": manifest["developer"]["email"],
        "team_name": manifest["team_name"],
        "base_url": (base_url or manifest["endpoints"]["base_url"]).rstrip("/"),
        "pricing_model": manifest["pricing_model"],
        "price": float(manifest["price"]),
        "manifest": manifest,
        "produces": list(manifest.get("produces", [])),
        "consumes": list(manifest.get("consumes", [])),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", default="http://localhost:8000")
    parser.add_argument("--manifest", default=str(ROOT / "agent.manifest.json"))
    parser.add_argument("--base-url", default=None,
                        help="override endpoints.base_url, e.g. a Docker service URL")
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        payload = build_payload(manifest, args.base_url)
    except (OSError, ValueError, KeyError) as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2

    import httpx  # imported after validation so --help works without the dependency

    url = args.kernel.rstrip("/") + "/agents/submit"
    try:
        response = httpx.post(url, json=payload, timeout=args.timeout)
    except httpx.HTTPError as exc:
        print(f"submission failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"HTTP {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2, sort_keys=True))
    except ValueError:
        print(response.text[:500])
    return 0 if response.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
