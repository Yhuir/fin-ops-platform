---
quick_id: 260803-3pf
status: complete
mode: execute
date: 2026-08-03
description: 拆分通用发布门禁与 ACL 双身份专项门禁，部署关联台高度修复并完成生产验证
must_haves:
  truths:
    - 发布类型由候选与当前 active release 的受控文件差异自动判定，操作者不能手工降级安全级别
    - 普通发布只要求 YNSYLP005 管理员身份，不再要求 YNSYLP006；ACL 权限边界变更自动升级为 005/006 双身份专项门禁
    - 纯前端发布不执行无关的队列拓扑写入、全页面审计和 T+60/T+300 等待
    - 已完成的一次性 ACL 环境键与 OA 菜单绑定切换代码退出通用激活链路，历史数据库 migration 保留
    - 新候选精确绑定最终 remote main，旧 9bd767e4 候选不得复用
    - 生产 active release 健康，且关联台非一一对应 OA/流水/发票栏占满组高，完整一一对应仍同行
  artifacts:
    - deploy/oa/bin/finops-deploy-control.sh
    - scripts/deploy_oa.py
    - tests/test_deploy_oa_script.py
    - docs/modules/deploy/
    - deploy/oa/README.md
  key_links:
    - candidate package -> automatic change profile -> profile-specific release gate -> atomic activation -> profile-specific evidence
    - ACL boundary digest change -> candidate-bound 005/006 preflight -> ACL activation/postdeploy
    - final git SHA -> release manifest/fingerprint -> production active release -> browser/HTTP geometry and latency evidence
---

# Quick Task 260803-3pf: 发布门禁收敛与关联台生产闭环

## Task 1：自动风险分级与最小门禁

**Files**

- `deploy/oa/bin/finops-deploy-control.sh`
- `scripts/deploy_oa.py`（复用既有上传/激活入口，无需修改）

**Action**

- 比较候选与当前 active release 的受控文件内容，自动判定 `frontend`、`runtime` 或 `acl`；缺失或无法证明时 fail-safe 为更严格级别。
- 所有发布保留精确 release/SHA/fingerprint、存储、迁移、原子切换、ready 与 YNSYLP005 管理员会话验证。
- `frontend` 只运行激活前/后必要健康、worker inventory、shell/assets/session 与 release 绑定检查；不执行 RabbitMQ apply、全页面审计或 T+60/T+300。
- `runtime` 保留完整运行时门禁，但只使用 005；`acl` 自动要求候选绑定的 005/006 双身份 preflight，并保留 ACL 专项 postdeploy。
- 从通用激活链路删除已经完成的一次性 retired env 清理、OA 旧绑定清理与 rollback 恢复路径；steady state 只做严格只读断言。

**Verify**

- 无操作者 `--skip` / 手工 profile 参数。
- 自动分类覆盖纯前端、普通后端/部署、ACL 边界、未知/缺失 active release。
- 通用发布链路无 006 token、OA cleanup DML 或退休环境键写入。

## Task 2：测试、文档与回归

**Files**

- `tests/test_deploy_oa_script.py`
- `docs/modules/deploy/README.md`
- `docs/modules/deploy/boundary-io.md`
- `docs/modules/deploy/state-machine.md`
- `docs/modules/deploy/tests.md`
- `docs/modules/deploy/implementation-notes.md`
- `deploy/oa/README.md`

**Action**

- 更新部署脚本契约测试，覆盖自动升级、005-only 通用门禁、ACL 双身份专项门禁、frontend 快速证据和旧切换链路删除。
- 同步模块边界、I/O、状态机、运维入口与测试矩阵；明确 migration 0132/0133 是不可删除的历史事实，不是每次发布的运行步骤。
- 运行部署目标测试、全量 deploy 相关回归、lint、docs 与 shell syntax。

**Done**

- 生产级安全属性由可执行测试保护，文档与实现一致，无新增依赖或第二套 deploy controller。

## Task 3：提交、全新候选、部署与生产验证

**Action**

- 审阅 diff 后提交并 push 到 `origin/main`，确认本地/remote main 精确一致。
- 从最终 SHA 创建全新 no-activate 候选并以同文件系统原子 bootstrap 新 deploy-control；不复用 `main-9bd767e4-workbench-pane-height-20260803`。
- 通过新的自动门禁激活候选；失败时保持 maintenance 并 forward repair，不回退 unsafe 旧版本。
- 验证 active SHA、ready、服务/worker、005 会话、关联台 API/页面无错误；用真实浏览器几何检查非 1:1 OA/流水/发票全高和 1:1 同行，并采样页面/API 性能。

**Done**

- `main == origin/main == production active commit`，门禁证据与 UI 几何/性能证据完整可复核。
