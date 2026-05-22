# 读 API 性能生产级整合计划

## 目标

不换语言，先完成读模型、payload 契约、Redis 容错和连接池预热整合，降低 workbench groups、tax-offset、summary/search 的 p95 风险，并为后续是否进入 Go read API sidecar 提供可量化门槛。

## 验收标准

- `/api/workbench/groups?detail_level=summary` 列表 payload 不返回完整明细，只返回 preview rows、`row_counts`、`collapsed_row_counts`。
- 前端列表计数使用服务端 count 字段，preview rows 不导致总数误判。
- `/api/tax-offset/summary?month=YYYY-MM` 返回小 payload，Redis 使用独立 summary key，旧 `/api/tax-offset` 保持兼容。
- Redis get/set/delete 异常不会让 tax-offset API 失败。
- Postgres pool 在启动构造时可预热，读模型 repository 支持可选 read connection。
- 相关后端和前端测试通过；未能运行的验证必须说明原因。

## 实施顺序

1. 保存执行 prompt 和计划。
2. Groups summary contract：
   - 后端 compact 函数裁剪 preview rows。
   - 前端类型和计数逻辑支持 `rowCounts` / `collapsedRowCounts`。
   - 补后端 repository 测试和前端 API 测试。
3. Tax-offset：
   - 增加 summary route 和 summary Redis key。
   - 对 tax-offset Redis get/set/delete 加局部 best-effort fallback。
   - 补 SQL runtime 测试。
4. Postgres pool/read config：
   - 增加 `warm_up()`。
   - factory 构造后调用 warm_up。
   - 状态仓库支持 read connection，并让 read model repository 使用它。
   - 补 factory/state store 测试。
5. 运行验证并记录结果。

## 回滚点

- Groups：保留 `detail_level=full` 和 group detail 接口，前端可临时改回 full，但默认不建议。
- Tax-offset：旧 `/api/tax-offset` 不改契约，summary route 可单独关闭前端调用。
- Postgres read pool：未设置 `FIN_OPS_POSTGRES_READ_DATABASE_URL` 时读写共用；删除 read env 即可回滚到旧部署形态。

## 风险

- Groups preview rows 会改变列表页“展开 collapsed 明细”语义，需要通过 `collapsed_row_counts` 显示真实数量，详情仍走 full endpoint。
- Tax-offset summary 初期仍可能从整包 SQL read model 裁剪，主要先降低 HTTP/Redis 小 key payload；真正 item 表分页需要后续 migration。
- Pool 预热会把配置/网络问题前移到启动阶段，这是生产上更可取的失败模式，但本地环境需要正确配置 Postgres URL。
