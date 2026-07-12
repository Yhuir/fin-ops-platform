# Phase 20 研究：三组可逆关系写操作闭环

日期：2026-07-12

## 研究结论

现有系统已经分别具备 canonical relation command/UoW、24 个 operation profiles（117 条 scope expectations）、durable queue/worker、HTTP freshness probe、17 页同快照 System Audit 和 relation consumer Browser tests。缺口不是新建这些能力，而是 `write_operation_e2e_smoke` 只在整个 scenario 的所有静态 steps 执行完后等待一次 operation SLO；它不能把 confirm 和 withdraw 分别绑定到独立的 fan-out、freshness、页面结果与新 System Audit，也不解析 System Audit body 形成 fail-closed closure verdict。

## 当前正式链路

- Mutation owner：Workbench action API → `WorkbenchRelationCommandService` → `WorkbenchWriteUnitOfWork` → `app.workbench_pair_relations` / history。
- Transactional fan-out owner：UoW 收集 refresh intents，由 `RuntimeQueueReadModelRefreshWriter` 批量写 `job.read_model_dirty_scopes` 与 `job.outbox_events`。
- Worker/readiness owner：runtime worker registry、PostgreSQL durable queue、read model projection repositories、source versions/readiness。
- Write proof owner：`write_operation_slo_audit.DEFAULT_OPERATION_EXPECTATIONS`。
- System proof owner：`OperationsAuditService` → `PostgresOperationsAuditRepository.audit_system(...)`；单一 `REPEATABLE READ READ ONLY` snapshot。
- Deployed write orchestrator：`write_operation_e2e_smoke`，已有 auth、approval、dry-run、HTTP write steps、SLO wait 和 post API freshness/SLO probes。

## 推荐的单一 runner 扩展

扩展 `write_operation_e2e_smoke`，不新增第二套 CLI：

1. 将 scenario 从“共享 operations + 多个无检查点 steps”扩展为有序 `checkpoints`；每个 checkpoint只拥有一组 mutation steps、operation profiles、post API probes 和可选 `system_audit` gate。
2. 每个 checkpoint 在写前取得数据库时间；写后只查询该时间之后且匹配该 checkpoint operation expectations 的 outbox/dirty rows。
3. required expectations 全部 pass 后运行 post API probes；现有 `http_slo_probe` 已把 top-level non-fresh/refresh_enqueued 判失败。
4. `system_audit` 通过同一个 HTTP request boundary调用 admin-only `GET /api/operations/app-health/page-audit?page=app-health-operations`，解析 JSON 并强制：HTTP 200、JSON、`page_key=app-health-operations`、`proof_availability=ready`、非空 contract revision/system audit id/snapshot identity、database snapshot true、`integrity=pass`、`freshness=fresh`、`queue=drained`、16/16 business pages pass、零 blocking issue。external unknown 允许且必须与 internal status 分开。
5. 每个 checkpoint输出独立 started_at、write results、write SLO、post API、System Audit ID/snapshot和 verdict；confirm/withdraw不得共享一次最终检查。
6. 保留当前 legacy scenario shape 的 parser only for existing one-way controlled smoke during migration；Phase 20 三组新场景必须只使用 checkpoints。调用方迁移后删除旧内部 execution branch，避免长期双 orchestration。

## 三组可逆关系形状

| Shape | Confirm profile | Withdraw profile | Required consumer emphasis |
| --- | --- | --- | --- |
| bank + invoice | `workbench_relation_confirm_bank_invoice_cross_page` | `workbench_relation_withdraw_bank_invoice_cross_page` | workbench/relation、bank detail、invoice lifecycle、pending invoice、input usage、search；cost/tax 不得伪 fan-out |
| bank + turnover | `workbench_relation_confirm_bank_turnover_cross_page` | `workbench_relation_withdraw_bank_turnover_cross_page` | workbench/relation、bank detail、pending invoice、cost、search；invoice/tax 不得伪 fan-out |
| bank + OA + invoice | `workbench_relation_confirm_cross_page` | `workbench_relation_withdraw_cross_page` | workbench/relation、bank detail、invoice lifecycle、pending invoice、input usage、cost、search；OA consumer由System Audit edge equality覆盖 |

每个 shape 使用两个 checkpoint：confirm 与 withdraw。withdraw 必须经正式 preview/version contract，或者使用由安全 scenario builder基于刚才 confirm 响应生成的正式 submit body；禁止 cleanup SQL。

## 场景数据与环境边界

- 本地 deterministic tests：fake connection/request只验证 schema、顺序、fail-closed、System Audit parser和兼容迁移，不作为真实 worker证明。
- Disposable PostgreSQL integration：使用 `FIN_OPS_TEST_DATABASE_URL`、全 migrations、test-owned canonical OA/bank/invoice/turnover facts、真实 app composition/UoW/queue/worker/audit；数据库名必须含 test 并在测试后 truncate/reset。
- Staging/production apply：必须有真实 user auth + admin auth、scenario file、approval ticket、bounded test-owned fixture identity、dry-run/preflight和回滚/withdraw；不得自动选择普通业务关系来执行 confirm。
- 当前本机未配置 `FIN_OPS_TEST_DATABASE_URL`，所以实现后该层必须 fail/skip 为结构化 external input required，不能冒充已运行的真实基础设施证据。

## 旧链与保留判断

### 删除候选（以 whole-repo caller scan 为准）

- 新 checkpoint runner落地后，旧 `_run_one_scenario` 中“所有 steps 执行完才等待一次 SLO”的重复 execution branch。
- 任何 Phase 20 fixture 直接写 relation/read model/outbox/dirty/readiness 或手工 mark-fresh 的 helper。
- 只证明 HTTP 200、不证明 per-mutation fan-out/freshness/Audit，却被文档标为完整 closure 的旧声明/测试。
- 若新三组场景接管后无 caller，删除静态 multi-step reversible scenario workaround；不保留隐藏 fallback。

### 保留

- `write_operation_slo_audit`：唯一 operation expectation evaluator。
- `http_slo_probe`：唯一 HTTP/SLO/freshness metadata probe；Phase 20不复制其网络和auth I/O。
- `write_operation_scenario_discovery` 当前 standing withdraw/bank-flow discovery：受控生产运维 owner，但它不冒充三组 confirm+withdraw fixture builder。
- deterministic Playwright relation fan-out specs：继续证明 DTO/renderer和用户可见结果；不冒充真实 durable worker evidence。
- no-OA legacy profiles：不在Phase 20新链使用；是否退休属于另一个 owner/phase，避免本阶段越界删除真实 legacy API。

## 计划切片

1. Runner contract：checkpoint schema、per-checkpoint write SLO/post API/System Audit、fail-closed tests、旧 branch迁移/删除。
2. Three-shape scenario contract：profile pair registry/impact matrix、safe fixture/scenario builder、confirm/withdraw response handoff、whole-repo legacy scan和docs。
3. Integration/verification：disposable PostgreSQL opt-in闭环、failure/restart/duplicate/dependency negative gates、frontend regression、full verification和真实环境preflight。

## 主要风险

- 一个 HTTP token可能只有mutation权限而无admin Audit权限；runner必须支持同一 headers同时携带 user bearer和admin cookie/token，并对缺admin明确失败。
- 只用时间窗可能混入并发同profile事件；场景应携带 trace/action metadata并在可用时进一步过滤，至少输出事件id/scope供审计。
- confirm/withdraw的动态 preview/version handoff不能用字符串替换DSL泛化；优先复用正式预览API和最小响应字段提取。
- System Audit通过只证明写后snapshot，不证明外部来源完整；报告必须保持bounded claim。

## GSD 研究执行说明

两次独立 researcher 调度均在工具层超时且未写artifact；主控按 CodeGraph、正式代码、测试与长期文档完成研究并记录此降级，没有跳过研究内容或验证边界。

## RESEARCH COMPLETE
