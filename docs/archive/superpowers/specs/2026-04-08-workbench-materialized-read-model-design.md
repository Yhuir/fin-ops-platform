# 关联台 Pair Relations + 物化读模型设计

日期：2026-04-08

## 目标

在现有 `pair relations` 轻量写模型基础上，再补一层 `workbench read model`，把关联台重构成：

- 写动作只改最小状态
- 页面加载优先读缓存好的关联台快照
- 前端动作成功后立即局部更新
- 后台再静默刷新或增量修补读模型

目标不只是让 `确认关联 / 取消配对` 更快，也要让整页 `关联台 load` 更快、更稳定。

## 为什么只加 pair relations 还不够

仅拆出 `pair relations` 后：

- `确认关联 / 取消配对` 会明显提速
- 但整页 `关联台` 仍然需要：
  - 拉 OA
  - 拉银行流水
  - 拉发票
  - 做配对叠加
  - 做分组

所以单独的 `pair relations` 解决的是写动作慢，不足以根治读模型慢。

## 目标架构

关联台状态拆成三层：

### 1. `workbench_pair_relations`

只保存一组记录的配对关系：

- `case_id`
- `row_ids`
- `row_types`
- `status`
- `relation_mode`
- `month_scope`
- `created_by`
- `created_at`
- `updated_at`

### 2. `workbench_row_overrides`

继续只负责非配对覆盖：

- 忽略 / 撤回忽略
- 异常处理 / 撤回异常
- 备注 / 展示类覆盖

### 3. `workbench_read_models`

保存已经组装好的关联台快照，作为前端优先读取的数据源。

每份读模型按作用域区分：

- `all`
- `YYYY-MM`

建议文档结构：

- `_id`
- `scope_key`
- `scope_type`
- `generated_at`
- `source_version`
- `payload`

其中 `payload` 直接保存最终给前端的 grouped payload。

## 读写职责

### 写模型

#### `确认关联`

- 只写一条 `active pair relation`
- 不重建整张关联台
- 同步增量修补受影响的读模型 scope

#### `取消配对`

- 只把对应 relation 标成 `cancelled`
- 不重建整张关联台
- 同步增量修补受影响的读模型 scope

#### `忽略 / 异常处理`

- 继续只写 `row overrides`
- 同步修补读模型

### 读模型

#### 页面加载

优先顺序：

1. 先取 `workbench_read_models`
2. 如果该 scope 没有可用快照，再回退实时重建
3. 回退重建成功后，回写新的 read model

#### 动作后刷新

- 前端先按 API 返回结果局部更新 UI
- 后端同时修补当前 scope 的 read model
- 必要时后台再触发一次整页校准

## scope 设计

第一阶段只支持：

- `all`
- `YYYY-MM`

`all` 视图专门服务跨月配对。

`YYYY-MM` 继续保留给：

- 税金抵扣
- 成本统计
- 搜索结果跳转

以及未来需要按月局部加载的场景。

## 物化读模型的更新策略

第一阶段不做复杂消息队列，采用同步小修补 + 必要时后台校准：

### A. 快速路径

- 动作 API 只改当前组
- 直接修补当前组在 read model 中的位置

### B. 校准路径

- 如果当前 scope 缺快照
- 或修补条件不足
- 就异步触发一次该 scope 的重建

这样能兼顾：

- 简单
- 可控
- 性能提升明显

## 自动匹配统一要求

后续这类自动配对都统一落进 `pair relations`，再进入 read model：

- 工资：`auto_salary`
- 内部往来款：`auto_internal_transfer`

这样 `已配对` 区域只依赖关系层，不再混杂多套临时规则。

## 实施顺序

### Prompt 41

- 新增 `workbench_read_models` 持久化层
- 新增 `WorkbenchReadModelService`
- 支持按 scope 保存 / 读取 / 删除

### Prompt 42

- `确认关联 / 取消配对` 改成只写 pair relation
- 动作后同步更新 read model
- 页面加载优先读 read model

### Prompt 43

- 前端局部更新与静默刷新收口
- 性能与回归 QA
- 兼容自动工资、内部往来款

## 验收标准

- `确认关联 / 取消配对` 不再依赖整页重建
- 关联台首次 load 优先读取 read model
- `all` 和 `YYYY-MM` 两种 scope 都有缓存快照能力
- pair relations、row overrides、read models 三层职责清晰
