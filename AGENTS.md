# AGENTS.md — DT_OpenDSS_cloud

## Mission and source of truth
Maintain and extend the existing OpenDSS Cloud project, not rebuild it. User works in Windows/PowerShell, local repo historically at `F:\U\Maestria\Monitoria\Proyecto`, remote `https://github.com/JuanSarS/DT_OpenDSS_cloud`. Confirm actual path, branch, commit, remote and dirty state before changing anything. Current repository, tests and runtime observations override historical handoff notes. Do not assume suggested file paths, endpoint contracts or bug hypotheses are current until inspected.

Read `docs/codex/PROJECT_CONTEXT.md`, `docs/codex/BUG_REPAIR.md`, `docs/codex/INTERACTIVE_QSTS.md`, `docs/codex/VALIDATION_AND_AWS.md` and `docs/codex/WORKFLOW.md`. If pre-existing AGENTS.md or other scoped instructions exist, preserve and reconcile them rather than replacing them. Respond to the user in Spanish; follow existing code and naming conventions.

## Non-negotiable invariants
- One simulation/session has one independent AltDSS/OpenDSS context; one QSTS job has one worker/context and sequential timesteps. Never distribute temporally dependent steps across workers. Independent jobs may run concurrently.
- Preserve snapshot and existing batch QSTS, REST/WS contracts and authorization; new features must be additive or explicitly migrated and tested. Preserve D1/D2/D3 original evidence, do not edit historical reports or silently change pass criteria.
- API-manager is single replica today because session/WS state is in memory. Worker discovery is dynamic via Cloud Map in AWS; retain worker affinity, job admission, context cleanup and existing recovery semantics. Do not claim stateful interactive failover unless tested.
- Keep authorization on the server. Existing viewer remains read-only; a future scoped operator may control permitted simulation actions, not sharing/administration. No arbitrary DSS command endpoint. Controls affect simulated circuits only.
- Custom models: respect model ownership/access, validated master path and shared storage. Treat uploaded DSS/ZIP as untrusted; prevent traversal, symlink escape, excessive archives, unauthorized paths and unsafe engine commands/file access. Do not weaken validation for convenience.
- Never read or print secret values, tokens, .env contents or AWS credentials unless specifically necessary and authorized; never commit them. Do not send private model data to external services.
- Do not run deploy/destroy, AWS resource-changing commands, push, merge, force push, destructive Git operations or paid cloud actions without explicit user approval. No AWS Organizations/IAM Identity Center changes. No global machine changes or broad permissions. Local edits and local tests only when user authorizes implementation.
- Do not overwrite existing work, discard changes, delete models/evidence, or reset history. Do not use git stash/reset/clean automatically. Do not upgrade dependencies unless required and justified.

## Immediate priority and gates
1. Read-only audit first: inspect repo state, actual routes, JS, schemas, worker, model storage, tests; reproduce collaboration and custom-model defects if local services already available; report concrete file:line references, expected/actual behavior, and a minimal repair plan. Do not edit yet unless user separately authorizes.
2. After authorization: isolate fixes on a safe branch if appropriate (protect existing uncommitted work), reproduce via regression tests, repair sharing/join and custom models end-to-end; run local tests and browser smoke. Stop and report results for approval.
3. Only after user accepts repair gate: design/refactor QSTS into common initialization and one-step primitives, implement manual then timed mode, switch controls and operator permissions. Run full regression, correctness equivalence and concurrency tests. Stop before AWS.
4. Provide exact file-by-file changes, test commands/results, unresolved blockers, Git diff summary and next step. Distinguish verified facts, hypotheses and proposed features. No false PASS or fabricated evidence.

## Local checks
Start with `git status --short --branch`, `git rev-parse --show-toplevel`, `git rev-parse HEAD`, `git remote -v`, `git log -5 --oneline`. Avoid exposing secrets from remote URLs if present. Discover current dependency setup, compose files and test entry points from repo. Candidate commands: `python -m pytest tests -q`, `docker compose config --quiet`, `docker compose ps`. Do not run compose startup/build or install dependencies silently if it changes environment; explain and obtain authorization as appropriate. Never start the cloud scripts as part of local tests.
