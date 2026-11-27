# Phase A/B — Repair collaboration and custom models

These are candidate findings discussed in ChatGPT against an earlier copy, not verified on current GitHub HEAD. Locate actual files and contracts before implementing. Do not paste guessed snippets blindly. Use exact code references and reproduce symptoms.

## A. Collaboration / joining sessions
User reports inability to add people and enter simulations. Candidate files:
- `services/frontend/static/js/app.js`: `joinSession`, `loadSharing`, `loadUsers`, `loadSessions`, invitation and request actions, WS lifecycle, render functions and error handler.
- `services/frontend/templates/index.html` and CSS (discover actual filenames): required DOM IDs, sharing panel, forms, session selector and hidden state.
- `services/api_manager/api/routes/simulations.py` and `services/api_manager/orchestration/simulation_service.py`: actual access request, invite, accept/reject, remove, session listing, per-session auth.
- Auth dependencies, WS route, Pydantic schemas, tests; discover actual locations.

Prior hypothesis: `loadSharing(sessionId)` calls undefined `renderViewers` and `renderAccessRequests`; `joinSession()` awaits sharing setup before finishing navigation, so a ReferenceError may cancel entry even when REST GET succeeds. Verify both functions actually missing, DOM refs, response shape (strings vs objects), HTTP methods and status codes. A distinct bug may exist when opening as a viewer or owner, when joining directly by ID, or during cookie/WS auth. Inspect browser console and network, capture sanitized error. Check races from stale `state.sessionId`, overlapping join, and disconnect/reconnect.

Historical route candidates (verify before use):
```
GET/POST /simulations/{id}/viewers
DELETE   /simulations/{id}/viewers/{user}
GET/POST /simulations/{id}/access-requests
POST     /simulations/{id}/access-requests/{user}/approve
```
Rejection endpoint was proposed but not verified to exist; do not add a frontend call to a nonexistent route. Historical state labels owner/viewer/admin/requestable/requested may differ from actual schema.

Repair principles: joining must not fail because an optional sharing panel fails; distinguish unauthorized 401/403, missing 404, worker unavailability and UI exception; show useful errors and keep session UI consistent. Implement render functions using DOM textContent rather than unsanitized innerHTML; bind actions with correct session identifier and validate response contract. Owner/admin privileges must follow actual current design; do not grant write to viewer. Allow request flow for nonmember only if backend explicitly supports it. Refresh membership after success; revoke REST and existing WebSocket access on removal (or close/re-authorize), including cached state. Avoid leaking restricted session metadata in listing and users endpoint. Do not introduce operator permissions in this bugfix stage unless indispensable and separately approved.

Acceptance tests: owner creates/opens; second user requests access; owner approves; user can join and observe results REST/WS; direct invite works; denial/rejection behaves according to existing contracts; unrelated user gets no private data; viewer write attempts forbidden; owner removes viewer and access is revoked on REST/WS; two-browser UI smoke; optional panel failure does not block session; refresh/login and duplicate requests handled. Test with existing auth cookie/token flow and avoid exposing credentials.

## B. Custom models
User reports custom models not working correctly. Candidate paths:
- `services/api_manager/orchestration/custom_models.py`: upload, archive extraction, metadata, model lookup, master selection, storage catalog.
- `services/api_manager/api/routes/models.py`: route ordering (`/custom` before conflicting parameterized routes), response models, role checks, upload/list/metadata.
- `services/frontend/static/js/app.js`: `loadModels`, `selectModel`, upload handler, custom selector, master choice, session creation.
- Worker preparation/executor, remote executor, topology catalog/engine, contracts, compose/EFS mounts, tests: trace actual `model_id` and master path from browser to worker, including shared storage access in local and ECS.

Prior hypotheses to reproduce:
1. `rglob("*.dss")` excludes uppercase `.DSS` on Linux; use case-insensitive suffix matching without altering actual filenames. References inside DSS may also have case mismatch on Linux; detect/report rather than arbitrarily renaming files. Preserve relative paths.
2. All .dss files returned as master candidates, frontend auto-selects first alphabetical file (e.g. Capacitors.dss). Prefer clear entrypoints such as Master.dss/Main.dss (case-insensitive basename) but do not guess if multiple; allow explicit choice and validate compile/new circuit. For models without conventional master name, expose candidates and require selection where ambiguous. Do not accidentally execute dependency files as standalone circuits. Preserve model's relative redirect and CSV profile structure.
3. Upload appends an option to HTML but not `state.models`, so changing/reselecting or refreshing loses custom model. Catalog should be backed by authoritative storage/metadata and loaded with correct permissions. Proposed `GET /models/custom` or extend existing catalog, depending on existing contracts. If a list endpoint already exists, fix it instead. Existing admin upload restrictions should remain; define who may list/create/read custom models from actual policy, with no cross-user disclosure. Metadata should include stable id, display name, available/selected masters and any validation status. Frontend must preserve selection on refresh/change and send correct master with create-session request.
4. A custom model can upload correctly but fail at worker compile because API and worker use differing roots, path conventions, missing redirects/profile files, or mounted EFS/compose permissions. Validate path resolution from both services. Use workspace-relative identifiers, not browser-provided absolute filesystem paths. Read original engine errors and show sanitized actionable messages; never hide failure behind successful upload.

Safety for archives and DSS (do not weaken existing safeguards): zip slip, absolute/parent paths, drive letters/UNC, symlinks, file count/size and decompression limits, collisions, model id validation, atomic staging then publish, no writes outside model workspace, no arbitrary commands from API, file-access isolation for untrusted DSS (redirect/compile and export/write operations need attention). Path validation alone does not sandbox an arbitrary script. Preserve allowed supported DSS use cases and avoid claiming hostile-script isolation if not implemented. Do not expose EFS paths or secrets to users.

Acceptance tests: lowercase and uppercase extensions; multiple dependent DSS files; nested archive and relative redirects/CSV; ambiguous/no master handled clearly; invalid model rejected with error; archive traversal rejected; authorized list persists across page refresh and service restart if volume persists; unauthorized users cannot access model; custom snapshot converges for valid fixture; custom batch QSTS works with model profile; API-manager→worker path verified using local remote executor, not only direct engine. Never delete actual user models for tests; use isolated temporary fixtures. Test UI reselect after built-in model and refresh.

## Repair gate
First report exact file/line root causes and a minimal plan. Once approved, add failing tests, fix incrementally and run full local regression. User should see test outcomes, browser reproduction (if available), changed files, remaining unknowns. Stop before interactive work until user confirms fixes.
