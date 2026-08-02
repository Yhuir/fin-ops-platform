---
quick_id: 260803-2x7
status: passed
date: 2026-08-03
---

# Quick Task 260803-2x7 Verification

## 合同验证

| 合同 | 证据 | 结果 |
|---|---|---|
| 非一一对应栏占满组高 | 4 OA / 2 流水 / 1 发票组件回归；Chromium `boundingBox()` | PASS |
| 完整唯一一一对应保持同行 | 2 OA / 2 流水显式来源映射回归 | PASS |
| 部分/重复来源不产生假同行 | display model 与 grid 回归 | PASS |
| 金额推断旧链路已移除 | source scan 零命中；金额相同/组合用例保持 group-level | PASS |
| 不增加请求或状态 | diff 仅调整纯 display model、grid 判定与 CSS | PASS |
| 不影响其他页面 | 前端全量 73 files / 921 tests；production build | PASS |

## 命令证据

```text
npm test -- --run src/test/groupDisplayModel.test.ts src/test/RelationGroupGrid.test.tsx
npm test -- --run src/test/groupDisplayModel.test.ts src/test/RelationGroupGrid.test.tsx src/test/WorkbenchSelection.test.tsx src/test/WorkbenchZone.test.tsx src/test/WorkbenchPaneFilter.test.tsx src/test/WorkbenchColumnLayout.test.tsx
npm test -- --run
npx playwright test e2e/workbench-relation-fanout.spec.ts --project=chromium
npm run build
bash scripts/verify.sh lint
bash scripts/verify.sh docs
git diff --check
```

全部通过。生产发布与只读验证通过仓库标准发布入口执行，不引入临时生产脚本或第二套部署链路。
