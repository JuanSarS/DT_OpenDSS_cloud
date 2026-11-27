# Project context — OpenDSS Cloud / DT_OpenDSS_cloud

Transfer prepared from prior ChatGPT discussion, 2026-11-25. This is a curated technical handoff, not a verbatim chat export or a fresh verification of GitHub HEAD. Names, paths and scripts below are historical and must be checked against the actual working tree. The project concerns power distribution system simulation and a collaborative digital-twin-like research platform, not control of physical electrical equipment.

## Environment and goals
- Windows, PowerShell, Python, Docker Desktop; Git repository historically at `F:\U\Maestria\Monitoria\Proyecto`. Remote: `https://github.com/JuanSarS/DT_OpenDSS_cloud`.
- FastAPI backend + AltDSS-Python/OpenDSS, HTML/CSS/JavaScript frontend, REST and WebSocket. Built-in IEEE13, IEEE34, IEEE123, IEEE8500. Custom model archives may include Master.dss, dependencies and load profiles. Verify supported formats and API schema.
- Goal: multi-user platform with independently isolated simulations, cloud horizontal scaling of workers, authenticated access, scientific consistency, resilience, custom circuits, and new interactive QSTS with collaborative simulation controls.
- The user wants practical local editing, file-by-file explanations, executable PowerShell commands and regression tests. No Copilot or unnecessary architectural rewrite.

## Architecture (historical validated baseline)
```
Browser / client
    | HTTPS + WSS
CloudFront
    | HTTP origin (historical config; NOT end-to-end TLS)
Public Application Load Balancer
    |
ECS Fargate api-manager (desired 1, in-memory sessions + WS)
    | Cloud Map DNS, authenticated worker API
ECS Fargate simulation-worker (1..N)
    | per-session independent AltDSS context
EFS shared custom-model storage (transit encryption)
```
ECR images tagged by Git SHA; Secrets Manager (JWT_SECRET, WORKER_SHARED_TOKEN, AUTH_USERS_JSON names only); CloudWatch logs/metrics; Application Auto Scaling; no NAT gateway in baseline. API manager assigns a worker and maintains session binding; worker pool discovers workers dynamically and handles recoverable failures. Worker scale-out-only (`DisableScaleIn: true` historically), because blindly terminating stateful workers would lose sessions. Do not change API count to >1 until session and socket state architecture is addressed. Local environment may use a different reverse proxy / compose DNS; verify exact setup.

## Simulation semantics
- Each session uses its own `dss.NewContext()` or equivalent verified engine constructor. Never reuse a global mutable engine across users/sessions. Worker context must be closed when session ends, and cleanup is idempotent.
- Snapshot is one steady-state power flow; batch QSTS is a chronological sequence of solves with state carried between steps, including profiles, controls, regulator/capacitor/storage state as relevant. Do not rebuild the circuit or reset the simulated clock every interactive step. Independent simulations can be parallelized; sequential steps of a single QSTS cannot be arbitrarily split across workers.
- API coordinates, authenticates, validates and broadcasts; simulation worker owns numerical state. Existing REST and WSS should continue working unchanged where possible.
- Historically exposed routes include `/health`, `/models`, `/simulations`, `/ws/simulations/{id}`. Discover exact request/response models and route prefixes.

## Known prior changes (verify in repo)
- Caddy/local trust adjusted, CSS `[hidden]` fixed, HttpOnly auth cookie and BroadcastChannel sync, malformed WSS Literal corrected, auth tests updated. Local regression was previously passing; no guarantee for present HEAD.
- Worker failover: pool recovery around `session_info()` marks unhealthy worker and logs `WORKER_LOST`, resyncs discovery, picks replacement, prepares same topology/load_multiplier and rebinds. A recursive error helper `_raise_prepare_error` in remote executor was corrected with `response.raise_for_status()`. Verify code rather than reapply blindly.
- Resilience harness uses artificial worker delay (35 ms/step) and reduced stop timeout (5 s in resilience mode; normal default 30 s), after prior issues with CloudFront response timing and graceful shutdown masking failover. Windows wrapper validates actual `resilience_result.json`, not just process ExitCode. Raw WebSocket evidence is preserved. `Worker stream ended without SimulationResult` may be recoverable only when correctly classified; do not catch all application errors as worker loss.
- Do not use artificial test delays as the new production interactive scheduler.

## Prior evidence (reported results, immutable historical baseline)
Read actual `docs/evidence` artifacts before using numbers in a report. Canonical run names below are historical, not new executions. More detail in VALIDATION_AND_AWS.md.
- D1 `20261117T050250Z_multicontext`: reported PASS, 4 models, 184 snapshot solves, 16 sequential per model plus levels 2/4/8/16. Reported 184 converged, 184 exact hashes, max delta 0; hash excludes session_id and elapsed_ms. This is not a QSTS equivalence proof.
- D2 `20261116T195840Z_cloud_performance`: MVP nested smoke PASS; formal performance summary `passed_load=false` because one DELETE cleanup 502 at 10 users. 5 users 1861 requests, 0 failures; 10 users 1889 requests, 1 failure. Desired workers 1→4, running 1→3, scale-out observed. Do not report full formal PASS or four running.
- D3 `20261117T043753Z_resilience`: reported `resilience_passed`, `observed_qsts_restart`, `security_passed`, `passed` all true. QSTS restart observed after ECS task stop. No verified proof of multiple unaffected simultaneous jobs or exact recovery time; inspect raw events before asserting.
- Cloud smoke earlier `20261116T074952Z_cloud_smoke`: authenticated snapshot/WS, QSTS REST 288/288, WS 3/3, IEEE8500 snapshot, short QSTS 3/3 and 1h 12/12 reported successful.

## Pending work, in order
A. Collaboration: cannot add users or join a simulation reliably. Fix existing read-only collaboration flow first.
B. Custom models: upload/selection/loading unreliable; repair local and remote flow with secure model catalog and model master selection.
C. Interactive QSTS: manual stepping and timed stepping, wall-clock interval independent of simulated step duration.
D. Collaborative operator role and typed switch open/close commands, synchronized state/results across authorized clients.
E. Regressions and local demo, then AWS only if authorized. Keep thesis evidence distinct from new feature tests.
