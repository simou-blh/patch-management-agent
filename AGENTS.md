# Project instructions

## Development

- Read `mvp.md` for requirements and `plan.md` for the four-sprint roadmap. Follow
  existing code and consult relevant documentation/tools when useful.
- Choose the simplest correct implementation. Spend effort identifying realistic
  failures rather than adding unnecessary abstractions or dependencies.
- Before editing, check affected callers, schemas, stored data, dependencies and
  workflows. Preserve unrelated user changes and compatibility deliberately.
- Clarify materially unclear, contradictory or risky requirements before dependent
  changes; resolve ordinary implementation choices from the code and requirements.
- Keep features small enough to understand, test and review. Run relevant tests with
  `python -m pytest`; report remaining limitations and distinguish mocks from live checks.
- Never commit, push or merge. The user handles those actions and branch selection.
- `local.md` is private planning material: keep it excluded locally and never stage,
  commit, publish or copy its contents into shared documentation or PR descriptions.

## Project boundaries

- Use OpenCode, MCP, osquery, Debian 12, Semaphore/SQLite and fixed Ansible playbooks.
  Environment/setup instructions belong in `SETUP.md`; respect its download budget.
- Inventory queries stay fixed, read-only and restricted to configured hosts.
- Only the operator CLI grants approval. Bind execution to the exact approved scope;
  never expose upstream Semaphore mutation tools directly to the model.
- Keep deployment blocked until approval, preflight, canary verification, sequential
  rollout, recovery and reporting pass the applicable live sprint gates together.
- Keep credentials, SSH keys and runtime evidence/plans/reports out of Git and model
  context. Preserve the teacher's reference for the later platform integration phase.

## Progress and efficient assessment

- `plan.md` owns five acceptance checkpoints per sprint. Check one only after merged
  work and recorded verification; include an `Evidence:` reference. Do not infer
  progress from commits, code volume, mocks or individual contribution scores.
- After a checkpoint change, run `python scripts/update_progress.py`, then its
  `--check` option. Keep generated README bars consistent in the same proposed change.
- During patch assessment, use MCP evidence instead of loading project documents.
  Batch queries, avoid redundant calls and stop on a reported blocker. The `patch`
  runtime's three-step/short-answer rules do not limit development investigation.
