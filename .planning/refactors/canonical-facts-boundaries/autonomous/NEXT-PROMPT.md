# Next Prompt: Canonical Facts Closure Preservation

```text
/goal

Preserve the completed canonical facts closure in /Users/yu/Desktop/fin-ops-platform.

Current state:
- 08 canonical facts is closed.
- No final closure blocker remains.
- `file_object.gridfs_migration` production worker path is removed.
- `ApplicationStateStore` / local pickle is accepted only as guarded non-production fixture/tooling I/O.
- Retained bank/ETC operational tools use `tools/runtime_application.py` as an app-owned public tool-port adapter.
- `tools/runtime_application.py` uses `build_tool_runtime_application(...)`; do not restore `build_full_snapshot_application(...)`.
- `Application.tool_runtime_ports()` must not expose the whole `state_store`.
- Tool initialization state must come from `Application.tool_runtime_state_snapshot()`.

Do not generate new deletion work unless a production API/worker/source-of-truth path regresses.

If a future change touches this boundary:
1. Read `docs/architecture/module-boundaries/canonical-facts.md` and `docs/modules/canonical-facts/boundary-io.md`.
2. Keep old source-of-truth paths out of production API/worker runtime.
3. Keep retained tools outside production hot paths and guarded by dry-run/explicit execute semantics.
4. Run:
   - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
   - `bash scripts/verify.sh docs`
   - `git diff --check`

Stop condition:
- If guards and docs verification pass, report that canonical facts closure remains preserved.
```
