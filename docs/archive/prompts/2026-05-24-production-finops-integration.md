# 生产级财务业务整合执行 Prompt

```
/goal 生产级整合 fin-ops-platform 的 9 个财务业务页面：统一前端 apiClient，规范跨页面刷新契约，并把后端 mutation 副作用统一接入 DerivedDataLifecycleService，配套测试与验证。

执行原则：
- 不做救急/临时方案，不新增绕过主流程的兼容分支。
- 先读 README.md、ARCHITECTURE.md、docs/index.md、docs/dev/frontend.md、docs/dev/backend.md、docs/product-specs/index.md。
- 遵守现有工作树，不回滚用户已有改动。
- 所有行为变更先写失败测试，再实现，再跑相关验证。
- 生产路径必须考虑权限、审计、回滚、数据一致性、派生 read model 失效和前端缓存刷新。

串行主线：
1. 建立统一前端 API 客户端。
   - 新增 web/src/features/apiClient.ts。
   - 封装 apiUrl、OA token、credentials、JSON 解析、HTML 代理错误识别、业务错误消息、AbortSignal。
   - 所有 9 页面相关 feature API 禁止直接 fetch("/api/...")。
   - 测试覆盖 /fin-ops/ 部署路径会转到 /fin-ops-api/。

2. 迁移 9 页面 feature API。
   - workbench、tax、cost-statistics、bankDetails、pendingInvoices、noOaBankBatches、batchAccounting、turnoverLedger、etc 全部走统一 apiClient。
   - 导出/download 类接口也必须使用 apiUrl 和统一认证。
   - 保留现有 mapper 和类型，不做无关 UI 重构。

3. 建立前端领域刷新契约。
   - 新增 typed domain mutation bus 或等价查询失效层。
   - 替换零散 window.dispatchEvent 字符串。
   - 至少覆盖 workbench、bank category、invoice fact、ETC batch、turnover relation、cost read model stale 这些域。

4. 后端 mutation 统一接入 DerivedDataLifecycleService。
   - 扩展事件定义，覆盖 bank category changed、manual invoice confirmed、no-OA batch submitted/withdrawn、batch accounting relation changed、turnover relation changed、ETC business batch changed。
   - 每个 mutation API 返回 affected months / row ids / domains / refresh jobs。
   - 禁止在 route 层新增散乱 invalidation。

5. 生产 read model 防线。
   - 热路径生产模式不得 fallback 到全量 runtime scan。
   - 对关联台、成本、待找发票、税金、ETC 的派生 read model 失效做集中测试。

并行检查任务：
- A. 扫描前端 feature API 的 direct fetch，迁移并补测试。
- B. 扫描后端所有 mutation handler 的 invalidation 调用，归并到 lifecycle event。
- C. 扫描 9 页面现有事件监听/派发，改为 typed bus 并补跨页面刷新测试。
- D. 扫描生产部署路径、OA token、credentials、HTML response 错误处理，确保一致。

验收标准：
- rg 'fetch\\(' web/src/features 只允许统一 apiClient 内部或明确注释过的低层封装。
- pytest 覆盖 DerivedDataLifecycleService 和关键 mutation API。
- npm test 覆盖 apiClient、9 页面 feature API 基础路径、跨页面 mutation bus。
- web build 通过。
- 最终报告列出变更文件、验证命令、未完成风险。
```
