#!/usr/bin/env bash
# Operator-only evidence collection driver (S1.3 persistence step).
# Runs the fixed read-only inspection playbook, extracts the emitted
# contract-v1 fleet_evidence envelope from its task output, and imports it
# via python -m patch_agent.collector, which validates, freshness-gates and
# atomically publishes data/evidence.json. Never mutates a VM, never accepts
# model input, never parses logs as trusted beyond this operator run.
#
# PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS must already be set by the operator;
# there is no default evidence lifetime.
#
# Usage: bash scripts/collect_evidence.sh
set -euo pipefail
cd "$(dirname "$0")/.."

targets=(vm-01 vm-02 vm-03)

if [ -z "${PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS:-}" ]; then
  echo "Set PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS (seconds) first; there is no default." >&2
  exit 1
fi

run_log=$(mktemp)
export_file=$(mktemp)
trap 'rm -f "$run_log" "$export_file"' EXIT

echo "Running playbooks/inspect.yml on: ${targets[*]}"
ansible-playbook playbooks/inspect.yml >"$run_log" 2>&1
grep -E '^vm-|RECAP' "$run_log" || true

python3 - "$run_log" "$export_file" <<'PY'
import json, sys
text = open(sys.argv[1], encoding="utf-8").read()
marker = '"fleet_evidence":'
start = text.rindex(marker)
value = text.index("{", start)
envelope, _ = json.JSONDecoder().raw_decode(text[value:])
json.dump(envelope, open(sys.argv[2], "w", encoding="utf-8"),
          ensure_ascii=True, allow_nan=False)
print(f"extracted fleet_evidence: collected_at={envelope['collected_at']}")
for name, record in envelope["hosts"].items():
    print(f"  {name}: status={record['status']} packages={len(record['packages'])}")
PY

uv run --no-sync python -m patch_agent.collector "$export_file" --targets "${targets[@]}"
