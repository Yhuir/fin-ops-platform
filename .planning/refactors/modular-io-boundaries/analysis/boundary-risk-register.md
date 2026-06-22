# 边界风险登记表

**用途:** 持续记录模块化 IO 重构期间发现的风险、状态和处理计划。

| ID | 风险 | 影响 | 当前证据 | 状态 | 处理计划 |
| --- | --- | --- | --- | --- | --- |
| BR-001 | `server.py` 仍是 legacy 路由和 handler 中心 | route owner 不清晰，改动可能影响多个模块 | `server.py` 约 22849 行，保留大量 `/api/*` dispatch | Open | 按模块迁移，不全局清理；每个模块合同列出 legacy handler 状态 |
| BR-002 | `read_models.py` 过大 | read model SQL/freshness/source version 变更可能跨模块扩散 | 文件约 11329 行 | Open | 先登记 read model owner，再按测试保护拆分 |
| BR-003 | read model refresh 调用点分散 | scope、reason、dedupe、operation barrier 难统一审计 | 多个 service 直接实例化 `ReadModelRefreshGateway` | Open | 建立 refresh 调用点登记和测试闸门 |
| BR-004 | 大 service 职责混杂 | command/query/policy/export/audit 可能耦合 | 多个 service 超过 2000 行 | Open | 单模块 audit 时做责任切片，不机械按行数拆 |
| BR-005 | 前端大页面和大 API client | loading/error/stale/action 状态容易相互影响 | workbench API、ETC/Bank/Workbench/Cost 页面较大 | Open | 先补交互和 API contract 测试，再抽取 view model/components |
| BR-006 | 模块合同缺失 | 后续 agent 容易凭文件名猜边界 | `docs/modules/` 完整但没有统一 IO 合同模板 | Open | 使用 `02-MODULE-IO-CONTRACT-TEMPLATE.md` |
| BR-007 | 试图一次性全局重构 | 高概率制造新回归 | 模块多、shared boundary 多 | Open | 必须先试点，试点通过后再推广 |
| BR-008 | 当前 worktree 有用户未提交变更 | 误改或回滚用户工作 | `git status --short` 显示 workbench/OA 相关修改 | Open | 后续实现前必须阅读相关 diff，不能回滚用户变更 |
| BR-009 | 没有本地 `PGSQL_URL` 和 staging 数据库 | 真实 PostgreSQL/read model/worker 验证无法在本地闭环 | 用户确认只有 SSH 服务器密码 | Open | 验证计划分为 local fake/stub、production read-only、production controlled-write；不能把未跑真实环境的验证标为完成 |
| BR-010 | SSH 密码被误写入文档/脚本/日志 | 生产凭据泄露 | 用户只有 SSH 密码，后续 agent 可能要求粘贴密码 | Open | 明确禁止记录 secret；生产命令使用交互式登录或服务器 root-only env，不在仓库保存密码 |
| BR-011 | 当前 SSH 只具备非特权 `finops-deploy` 访问 | 无法完成 root/systemd/secret/read model/worker 级生产验证 | `finops-prod` 可登录为 `finops-deploy`，无无密码 sudo；`finops-prod-root` 仍 Permission denied | Open | 将生产验证拆成非特权只读、特权只读、受控写入；获得 root/sudo/fin-ops 组/只读 DB 前不能关闭生产验证 |
| BR-012 | 自动推进可能误提交当前 main 工作区的用户变更 | 污染 Dev 分支或覆盖用户工作 | 当前 main 工作区有大量业务修改和新增文件 | Open | 启动自动推进前，用户必须先提交并 push 当前 main；主 repo 工作区必须干净，自动流程才能切到 `dev` |
| BR-013 | 无人值守流程遇到模块失败后停滞 | 无法趁用户离开持续推进其它安全模块 | 多模块队列中部分模块可能失败 | Open | 模块失败后最多 3 次修复，保存证据并标记 deferred，然后继续下一个独立模块 |
| BR-014 | 旧代码和旧链路污染新链路 | 新模块看似完成，但运行时仍通过旧 route/service/repository/frontend API 写入事实源或 refresh 状态 | 用户明确要求移除旧逻辑并禁止旧模块污染新链路 | Open | 每个模块必须填写 legacy 退役/隔离合同；默认删除旧链路，保留则必须 `compat-only`、有 owner、调用者清单、删除条件和污染防护测试 |
| BR-015 | Read Model 强制刷新被做成页面补丁 | 页面 A 更新后页面 B 仍读旧数据，或者通过“刷新所有”掩盖 scope/freshness 错误 | 用户明确要求重点关注 Read Model 强制刷新和跨页面同步 | Open | force refresh 必须通过统一 gateway/runbook/API contract；测试覆盖 affected scopes、dedupe、freshness proof、operation barrier 和跨页面回归 |
| BR-016 | Go Fiber 被误用为全量后端替换 | 重写范围暴涨，权限/审计/API/read model/worker 回归风险成倍增加 | 用户讨论后确认不做全量 Go Fiber 替换，只做热点模块 carve-out | Open | `11-GO-HOT-PATH-CARVE-OUT.md` 明确候选列表和 admission gates；候选外不得自动 Go 化 |
| BR-017 | Go candidate 未经准入直接实现 | 性能证据不足或边界不清，Go 新链路复制旧耦合问题 | Go/Fiber 候选需要性能证据、IO contract、shadow run、rollback | Open | 自动流程只能先做 Go admission；失败标记 `go-candidate-deferred` |
| BR-018 | Python worker 与 Go worker 双写/双 ack | 同一 dirty scope/outbox 被重复处理，readiness 或 generation 被污染 | 目标态是 Go Worker + PostgreSQL dual queue，但迁移需 worker-by-worker | Open | shadow-only 不得 ack/publish/write readiness；authoritative 切换必须有 per-worker ownership 和 rollback |
| BR-019 | Scoped incremental projection 缺少 partition/scope 设计 | incremental 退化成全量 rebuild，页面同步仍慢且易 stale | 用户要求所有页面 read model 优化为更高性能方案 | Open | 每个页面/domain 必须登记 partition key、scope key、incremental trigger、full rebuild fallback 和 parent/aggregate 规则 |
