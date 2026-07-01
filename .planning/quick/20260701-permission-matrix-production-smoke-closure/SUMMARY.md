# Permission Matrix And Production Smoke Closure

日期：2026-07-01

## 结论

- ETC 权限矩阵失败需要修。根因是测试绑定旧 UI 文案和旧按钮名，页面当前行为是只读用户看不到或无法触发高风险写入口。
- 远程部署/生产数据 smoke 不应在当前混合 dirty worktree 上直接执行。部署脚本默认拒绝 dirty release；生产发布必须可追溯到 commit。
- 已执行只读线上 shell/API smoke；这证明当前线上路由/API 基础可访问，但不证明本次未部署代码已上线。

## 修复

- `web/e2e/permissions-role-matrix.spec.ts`
  - ETC 只读 warning 改为语义正则，不再精确绑定旧文案。
  - 写入口扫描词表补入 `提交审批`。
  - 移除旧 `提交OA` 必须存在且 disabled 的断言；由写入口扫描和零 mutation 断言保护权限行为。

## 验证

- `npm --prefix web run e2e -- e2e/permissions-role-matrix.spec.ts --project=chromium -g "read-export users cannot trigger high-risk write controls"` -> 1 passed.
- `npm --prefix web run e2e -- e2e/permissions-role-matrix.spec.ts --project=chromium` -> 7 passed.
- `PYTHONPATH=backend/src:. python3 -m fin_ops_platform.tools.production_external_gate_preflight --json` -> `external_input_required`，缺 production Browser/admin/auth/write-operation 所需 token/env。
- 只读线上 shell/API smoke -> passed：`/fin-ops/`、`/fin-ops/cost-statistics`、`/fin-ops/settings` 返回 shell，missing asset 返回 404，session API 返回 JSON 401。
- `./scripts/deploy-oa.sh --dry-run --no-activate --release-name codex-bank-flow-rule-batches-smoke-check` -> dry-run passed；未上传、未激活。

## 剩余边界

- 未执行真实 release deploy。
- 未执行 authenticated production Browser smoke，因为缺 `FIN_OPS_E2E_OA_TOKEN` / `FIN_OPS_E2E_ADMIN_TOKEN`。
- 未执行生产写操作 smoke，因为缺认证、Postgres URL、可回滚 scenario 和审批 ticket。
