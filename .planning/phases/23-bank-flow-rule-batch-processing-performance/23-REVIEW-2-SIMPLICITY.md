# 第二次审阅：是否过度设计

## 候选方案对比

### 新缓存 / 新 read model / 新 worker

拒绝。当前已经有专属 SQL read model和 durable worker；问题是请求端全量读取、Python分页和同步等待。新增基础设施会产生双事实源、失效协议和运维成本，不能直接解决根因。

### 新 UoW 或命令总线

拒绝。现有 relation adapter的 `save_repository=False` 加 `save_bank_flow_rule_batch_mutation(...)` 已经形成一次原子保存。新增 transaction abstraction 会重复现有 owner。

### 全面复制或重写 shared BankBatch 领域算法

拒绝。No-OA 与 bank-flow仍共享当前批次生成算法；复制两千余行会导致规则分叉。只给 shared core增加当前需要的 namespace/schema policy，并让 bank-flow boundary不再调用旧命名 I/O。

### 生产历史 ID迁移

拒绝。成本与风险远高于收益。保留历史身份兼容，新数据停止污染即可闭环。

### Row-level 增量 worker

暂不采用。现有 month-scoped worker、source-version skip和 bulk source读取已经具备合理结构。先删 HTTP同步 rebuild、修列表/详情/前端等待，再以真实 PostgreSQL测量。如果 month p95仍超过 2 秒，只优化同一 worker 内的现有 SQL，不先引入新的 delta contract。

## 保留的最小结构

1. 一个 bank-flow专属 paged read port，基于现有表；
2. 暴露一个已经存在的 bulk bank transaction query；
3. reset复用一个已经存在的 bulk cancel command；
4. 前端复用已有 background refresh状态与 reconcile函数；
5. shared core增加少量显式 namespace/schema配置；
6. architecture guard与必要测试。

没有新增依赖、服务、表、队列、worker、缓存或通用框架。

## 第二轮判定

该设计不是过度设计。它删除昂贵旧路径并复用现有能力，新增边界均对应已经观测到的当前问题。实现时不得顺手重构其它页面或把 page port抽象成全仓通用 pagination framework。
