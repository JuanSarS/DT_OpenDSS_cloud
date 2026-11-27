# Workflow and handoff protocol

## Gate 0 — read only
Inspect git status/branch/commit, actual tree, relevant route/schema/frontend/worker/storage modules, tests and documentation. Identify exact divergences from transfer notes. If local app is already running, reproduce without modifying real sessions/models; otherwise propose isolated reproduction and commands. No edits in this first audit, no new branch needed, no cloud. Return:
- commit/branch and dirty files summary (no sensitive data), actual architecture and route contracts;
- per-bug evidence: expected/observed, precise file:line, hypothesis vs confirmed, reproduction;
- minimal change plan by file, test plan, blockers. Ask approval to apply fixes.

## Gate 1 — repair
After explicit approval, protect dirty working tree and use a branch such as `fix/collaboration-custom-models` if safe and consistent with user's preference; if uncommitted changes overlap, coordinate first. Add targeted failing tests, implement minimal repairs A/B, run targeted and full regressions. Do local compose/browser smoke if allowed. Do not commit or push until user agrees (local branch creation after approval is acceptable). Report git diff, test counts and failures, what is untested, how to reproduce manually. Stop and get acceptance.

## Gate 2 — interactive proposal then implementation
After user confirms bugfixes, inspect current QSTS loop and role model. Present design decisions on timers, forced step during auto, switch application/recompute boundary, worker loss, admission and concurrency. Implement incremental manual stepping and batch equivalence first; timed scheduler next; then typed controls and operator permissions; then UI. Run each test gate before expanding. Preserve old endpoints and historical evidence. Stop before any AWS deployment.

## Gate 3 — release
Only if asked, review changes, prepare local commit(s), show exact deployment commands and costs/risks, request approval before AWS or push. For updated thesis experiments, save new timestamped evidence; never alter canonical D1/D2/D3 reports.

## Continuity
Keep `docs/codex/STATUS.md` up to date AFTER permission to edit: date, branch/commit, actual verified bugs, modifications, tests with commands/results, pending decisions, next step. No secrets or personal credentials. If a new Codex thread is created, read AGENTS.md + relevant docs and STATUS.md, verify working tree. This is how context persists across chats. User can bring status/diff back to ChatGPT for architectural review.
