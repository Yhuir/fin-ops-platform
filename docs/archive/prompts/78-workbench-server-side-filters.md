# 78. Workbench 服务端列筛选/时间筛选执行 Prompt

/goal 把关联台列筛选和时间筛选下推到 PostgreSQL SQL read model，并保持首屏/加载更多分页渲染，不回退全量加载；补齐测试、文档和验证。

## 串行主线

1. 先写失败测试，锁定 `/api/workbench/groups` 必须接收并透传列筛选和时间筛选参数。
2. 建立生产级 SQL 投影：新增 `read_model.workbench_group_rows`，按 `scope_key/zone/group_id/pane/row_id` 保存三栏行的筛选字段、时间字段和搜索文本。
3. worker/read model rebuild 写入 `workbench_groups` 时同步写入 `workbench_group_rows`，`all` 聚合 scope 也必须同步。
4. 后端 `get_workbench_groups_page` 使用 `workbench_group_rows` 做命中 group 查询，分页仍读取 `workbench_groups`，不读取 snapshot payload。
5. 前端 `buildWorkbenchServerPageQuery` 序列化 `filtersByPaneAndColumn` 和 `timeFilterByPane`，`fetchWorkbenchGroupsPage` 放入 query string。
6. Redis page cache key 必须包含筛选和时间筛选参数，避免缓存串结果。
7. 更新开发/产品文档，把 page size 200 和服务端筛选契约写清楚。
8. 跑后端相关测试、前端相关测试、前端 build、migration 静态检查。

## 并行任务

- 后端并行审查：确认 `read_model.workbench_group_rows` 字段、索引、迁移和 Redis key 覆盖。
- 前端并行审查：确认筛选/时间筛选序列化、本地显示过滤与服务端分页共存，不破坏已有搜索和排序。

## 验收

- 未加载的 group 只要命中列筛选或时间筛选，就能出现在筛选后的第一页或后续分页中。
- 搜索、排序、列筛选、时间筛选都能进入 `/api/workbench/groups` 请求。
- 前端仍只渲染当前页，不全量加载。
- `read_model.workbench_snapshots.payload/raw_payload` 不进入页面热读路径。
- Redis 清空不影响正确性；Redis 命中不会串不同筛选条件的结果。
