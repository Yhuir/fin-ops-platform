---
quick_id: 260803-3pf
status: passed
date: 2026-08-03
---

# Quick Task 260803-3pf Verification

## 合同验证

| 合同 | 自动化证据 | 结果 |
|---|---|---|
| 自动风险分级且不可手工降级 | exact release tree executable fixture：frontend/runtime/ACL；CLI 无 profile/skip | PASS |
| 普通发布 005-only | release gate 只读一个 stdin token；frontend checkpoint 精确校验 005 | PASS |
| ACL 自动升级 | ACL owner 文件 digest 变化得到 `acl` 并要求 candidate-bound preflight | PASS |
| ACL 只接受稳态 | deploy consumer 仅接受 `eligible=true`，不再接受 `cutover_eligible` | PASS |
| frontend 快速门禁 | 无 RabbitMQ、closure、domain/page audit、T+60/T+300 | PASS |
| runtime 完整门禁 | pre/T+0/T+60/T+300 与最终 evidence 合同保留 | PASS |
| 旧链路删除 | env rewrite、OA binding cleanup/rollback 函数和历史 SQL 均不存在 | PASS |
| 关联台高度回归 | 42 组件测试、2 Chromium 几何/确认流 | PASS |

## 命令证据

```text
PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script tests.test_deploy_runtime_examples tests.test_platform_runtime_boundary_guards tests.test_settings_access_control_preflight tests.test_permissions_write_entry_inventory
npm test -- --run src/test/RelationGroupGrid.test.tsx src/test/ReconciliationWorkbenchPage.test.tsx
npx playwright test e2e/workbench-relation-fanout.spec.ts
npm run build
bash scripts/verify.sh lint
bash scripts/verify.sh docs
bash -n deploy/oa/bin/finops-deploy-control.sh
git diff --check
```

全部通过。生产部署必须从最终 clean `origin/main` 新建候选，禁止复用 `main-9bd767e4-workbench-pane-height-20260803`。
