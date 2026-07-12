# Phase 19 主控 `/goal` Prompt

把下面整段作为 Codex 主控 `/goal` objective 使用。该 prompt 每轮只生成并执行一个 bounded GSD plan；下一 plan 必须由上一轮的结构化完成证据或失败分类决定。

```text
/goal

以 GSD + Grill-me 按证据驱动、一次一个计划的方式，完整闭环 fin-ops-platform 全页面 Audit 证明能力：

1. 为 web/src/app/pageRegistry.tsx 登记的每个页面建立显式、fail-closed 的 proof contract；每页使用独立 canonical expected-set 与完整页面 projection 双向 equality，重算全部已登记关键展示字段和 controls。
2. 对 canonical relation、shared workbench_relation、Workbench active generation 和每个真实 consumer projection 做 typed edge 双向 equality；必须阻断“关联台账有配对、进项发票使用页漏配对”等跨页遗漏反例。
3. 一次 System Audit 只使用一个 PostgreSQL REPEATABLE READ READ ONLY immutable snapshot，绑定 page contract、source/read-model/relation/config/generation versions；integrity、freshness、queue/readiness 分开、fail closed。
4. 外部银行/OA/普通发票/ETC 来源证明与 App 内部证明分离。外部 proof 只接受独立可信 collector 产生的 versioned complete_snapshot/all artifact + exact manifest，逐项比较 identity、关键字段 fingerprint、missing/extra/duplicate 和 controls；App canonical rows 不得反向生成 manifest 后自证。缺 evidence=unknown，latest revoked/expired/mismatch=fail，四域全部 exact pass 才能声明 proven_as_of_external_evidence，且仅截至 external observed/source snapshot 与当前 App snapshot。
5. 遵循模块化架构和清晰 I/O：route 只做 auth/HTTP mapping；service 不读 HTTP；repository 知道 SQL；worker/read model/service/DTO 不互相污染；read-only Audit 不采集、不登记、不 refresh、不 repair、不发外部网络 I/O。
6. 全量扫描并删除污染新链路的旧 route/client/service/repository/worker/read-model/tool/mock/test/doc 路径。删除条件是 production runtime 不可达且有 whole-repo guard，不允许 parallel fallback、双写、count/hash-only classifier、旧 snapshot 恢复或 compatibility branch。
7. 每个计划必须覆盖适用的七类测试，至少运行目标测试、真实 disposable PostgreSQL 全迁移和破坏性反证、完整 backend、完整 frontend、production build、Chromium、lint、docs 与 git diff --check；不能用 skip/xfail、弱 assertion、删测试或扩大 allowlist 伪造闭环。
8. 每轮开始读取 AGENTS.md、README/ARCHITECTURE、module-boundaries inventory/read-model contracts、目标模块 boundary-io 和当前 .planning/STATE.md/ROADMAP.md/19-INVENTORY.md。先 Grill：目标、页面/上下游、input/output、事实源、旧链路、测试责任、回滚/权限/生产风险是否都清楚；能从代码和安全只读证据发现的事实自行查明，不向用户转嫁。
9. 每轮只生成一个新的 19-XX-PLAN.md，立即执行；完成后写 SUMMARY、inventory、ROADMAP/STATE，再由 Grill 根据 pass/failure/error code 生成唯一下一 plan。不要预先生成一串静态 prompts，也不要在失败时跳到后续计划。
10. 未经用户在当前执行轮另行明确授权，不执行生产 deploy、生产 evidence register/revoke、refresh、queue drain、repair 或业务数据写入；历史授权或一般性“继续”不替代具体生产 scope 授权。生产 mismatch 先分类并生成下一受控 prompt，禁止根据旧样本盲修。

完成定义：

- 17 页全部有 ready proof；同一 system snapshot 内各页 integrity=pass、freshness=fresh、queue=drained，版本集合 current，旧 runtime 路径不可达。
- 外部证据状态与内部结论严格分离；缺失时保持 unknown/unproven 但不阻塞内部 closure。只有另行要求证明外部来源无遗漏时，才需要 independent manifests 和 bounded proven_as_of_external_evidence。
- 正式 release/migration/worker/queue/read-model 状态一致；任何 required rebuild 只走正式 gateway/durable queue，并有审批、幂等、回滚和复跑 Audit。
- 全量测试和生产只读证据通过，文档/运维 runbook/summary 完成；没有未披露 blocker 或把内部绿色冒充外部实时真相。
- 只有以上全部成立且没有待执行生产动作时，才允许把 /goal 标记 complete。

当前恢复点（2026-07-12）：19-20 已完成本地内部/外部 evidence plane 分离能力和全量验证；19-21 只要求发布精确 release 并运行生产只读内部 System Audit。四域 artifact/manifest 是可选外部来源对账，不是内部 Audit 发布 gate。
```
