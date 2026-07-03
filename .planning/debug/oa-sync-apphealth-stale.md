---
status: investigating
trigger: "OA still not synced in AppHealth after deploying periodic Mongo sync; UI still shows 06/18."
created: 2026-07-03
updated: 2026-07-03
---

# Debug Session: oa-sync-apphealth-stale

## Symptoms

- Expected behavior: periodic OA Mongo sync updates the PostgreSQL OA projection and AppHealth shows a recent OA sync timestamp.
- Actual behavior: AppHealth data inventory still shows OA count 334 and synced time 06/18 10:22 after the 2026-07-03 release installed `finops-enqueue-oa-sync.timer`.
- Error messages: no UI error; timer enqueue log shows an `oa.sync` event was created.
- Timeline: observed immediately after release `main-7a4940fa-20260703173831` deployment on 2026-07-03.
- Reproduction: open `/operations/app-health` and refresh.

## Current Focus

- hypothesis: the timer enqueues `oa.sync`, but the worker either fails to consume it, cannot read OA Mongo, writes no successful `app.oa_sync_runs(sync_type='oa_projection')`, or AppHealth reads the wrong timestamp source.
- test: compare production queue event status, worker logs/heartbeats, `app.oa_sync_runs`, OA projection row timestamps, and AppHealth API payload.
- expecting: one boundary in the chain has fresh evidence while the next boundary remains stale.
- next_action: gather production read-only evidence and inspect the corresponding code path.

## Evidence

## Eliminated

## Resolution

- root_cause:
- fix:
- verification:
- files_changed:
