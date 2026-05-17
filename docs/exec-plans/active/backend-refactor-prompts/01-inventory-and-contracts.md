# Prompt 01：现有后端盘点与 API/数据契约梳理

```text
/goal
你是 Codex 子代理：现有系统盘点负责人。工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
只读盘点当前 Python 后端、前端调用、app Mongo、GridFS、业务模块和迁移风险，为 Axum + PostgreSQL 重构提供低耦合模块边界。不实现新代码。

必须读取：
- AGENTS.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/data-model-and-read-models.md
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- backend/README.md
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/app/routes_workbench.py
- backend/src/fin_ops_platform/app/routes_tax.py
- backend/src/fin_ops_platform/app/routes_turnover_ledger.py
- backend/src/fin_ops_platform/services/state_store.py
- backend/src/fin_ops_platform/services/mongo_oa_adapter.py
- web/src 中 API client 文件

禁止：
- 不连接任何 Mongo。
- 不操作 OA 源数据库。
- 不修改业务代码。
- 不生成假字段、假接口、假数据库列。

任务拆分：
1. API 路由盘点
   - 从 Python server/routes 文件提取路由。
   - 标注方法、路径、所属业务域、是否读/写、是否高风险。
   - 找到前端调用点。

2. 业务模块边界
   - 按模块分组：auth/session、settings、imports/files、workbench、reconciliation、exceptions、tax/ETC、cost statistics、turnover、health/jobs。
   - 每个模块标注依赖：state_store、OA adapter、file storage、background job、read model。

3. app Mongo 数据对象
   - 从 ApplicationStateStore 代码盘点 app Mongo collections。
   - 标注是否核心事实、read model、缓存、任务状态、文件元数据、历史兼容。
   - 标注是否包含 pickle/binary payload。

4. GridFS 使用点
   - 盘点所有 GridFS 读写路径。
   - 标注文件类型、业务归属、是否需要迁移到 MinIO/S3。

5. OA 边界
   - 只从代码和文档盘点 OA adapter 依赖。
   - 明确不得备份/导出/操作 OA 源库。
   - 标注哪些 API 当前可能在请求路径触发 OA 读取。

6. 迁移优先级
   - 给每个模块建议迁移批次：低风险读接口、文件/导入、read model、工作台读、写操作、运维高风险接口。

交付物：
- 新建 docs/exec-plans/active/backend-refactor-inventory.md

文档结构：
- 概览
- API 路由清单
- 前端调用点清单
- 业务模块边界
- app Mongo collection 清单
- GridFS 文件路径清单
- OA adapter 只读边界
- 迁移批次建议
- 风险和待确认问题

验收：
- 能看出每个现有接口应该属于哪个未来 Axum module。
- 能看出哪些 Mongo 数据迁入 PostgreSQL，哪些只重建 read model，哪些归档。
- 没有要求或暗示备份 OA 源数据库。
- 所有不确定字段都标为“待确认”，不猜。
```

