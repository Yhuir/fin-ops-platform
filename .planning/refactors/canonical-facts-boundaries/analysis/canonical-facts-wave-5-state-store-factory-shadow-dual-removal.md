# Canonical Facts Wave 5: State Store Factory Shadow/Dual Removal

日期：2026-06-29

## Scope

删除 `state_store_factory.build_state_store(...)` 中旧 shadow / dual backend 构造入口：

- `FIN_OPS_APP_STORAGE_BACKEND=shadow`
- `FIN_OPS_APP_STORAGE_BACKEND=dual`
- shadow / dual preflight wrapper helper
- local pickle / PostgreSQL mixed preflight backend builder

## Decision

- shadow-read、runtime policy、controlled mirror-write 和 cutover preflight CLI 已删除。
- factory 继续支持 `shadow` / `dual` 会保留可重新启用 local pickle / PostgreSQL mirror 的旧 source-of-truth path。
- 后续 slice 已删除 default local / mongo / auto factory fallback；`ApplicationStateStore` 本体仍是后续 local pickle implementation slice。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store_factory.py tests/test_state_store_factory_preflight.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store_factory_preflight -v
```

结果：通过。
