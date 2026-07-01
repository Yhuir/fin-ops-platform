# Bank Flow Rule Batches Full Closure Goal

This GSD quick workspace contains prompt artifacts for closing the `bank-flow-rule-batches` module.

Files:

- `MASTER_GOAL_PROMPT.md`：可直接粘贴到 Codex `/goal` 的主控 prompt。
- `PROMPT_001_BASELINE_AUDIT.md`：主控第一轮应执行的 bounded prompt。
- `P006_FINAL_VALIDATION_CLOSURE.md` / `P006_IMPLEMENTATION_REPORT.md`：最终 validation drift 收口。

Rules:

- Do not put these prompt artifacts in `docs/`; long-term facts belong in module docs after implementation.
- The controller must generate only one next prompt per loop and execute it immediately.
- Completion requires physical storage, rule persistence, read model/worker, performance, frontend modularity, tests, and docs to close against current evidence.
