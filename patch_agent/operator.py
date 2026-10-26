"""Operator-only approval CLI; never register this command as an MCP tool."""

import argparse
import json

from patch_agent.approval import local_store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["show", "approve", "reject"])
    parser.add_argument("run_id")
    parser.add_argument("--hash", help="exact SHA-256 reviewed by the human")
    args = parser.parse_args()
    store = local_store()
    if args.action == "show":
        result = store.status(args.run_id)
    else:
        if not args.hash:
            parser.error("--hash is required after reviewing the exact plan")
        result = store.decide(args.run_id, args.hash,
                              "approved" if args.action == "approve" else "rejected")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
