# 关联台 Pair Relations 轻量写模型设计

日期：2026-04-08

## 目标

把当前关联台 `确认关联 / 取消配对` 从“重建整张关联台 + 重写 override 快照”的重路径，重构成：

- 只修改当前配对关系
- 后端快速返回
- 前端成功后立即局部更新
- 后台再静默刷新整页兜底

核心目标不是改变业务规则，而是把“配对关系”从杂糅在 row override 里的状态，抽成独立的轻量写模型。

## 当前问题

现有实现已经做过一次优化：

- `取消配对` 不再默认重建整张关联台
- overrides 也改成了增量写入
- 前端动作成功后会先局部更新，再后台刷新

但当前链路仍有两个结构性问题：

1. 配对关系仍然寄存在 `workbench_row_overrides`

- `confirm_link` / `cancel_link` 通过 row override 逐条写入
- 对于“只需要建立或删除一组关系”的动作，这仍然偏重

2. 读取模型和写入模型边界不清

- `pairing`
- `ignore`
- `exception`
- `detail note`

这些不同语义仍然在 override 层混用，导致动作 API 无法做到真正轻量。

## 设计原则

### 1. 配对关系单独建模

配对关系应成为独立真相源：

- 不再依赖 row override 承载“谁和谁配对”
- 用单独集合存储一组记录的关系状态

### 2. 配对与覆盖分层

后续状态应分成两层：

- `pair relations`
  - 只描述一组记录是否已配对
- `row overrides`
  - 只描述忽略、异常处理、备注覆盖、访问账户设置等非配对状态

### 3. 写动作最小化

`确认关联 / 取消配对` 必须只影响当前组：

- 不重建整张关联台
- 不重写整份 override
- 不触碰无关记录

### 4. 读模型统一

工作台读取时：

1. 读取原始 OA / 银行流水 / 发票
2. 读取 `active pair relations`
3. 读取 row overrides
4. 统一组装成 grouped payload

## 新增持久化模型

建议新增集合：

- `workbench_pair_relations`

### 字段

- `_id`
- `case_id`
- `row_ids`
- `row_types`
- `status`
- `relation_mode`
- `month_scope`
- `created_by`
- `created_at`
- `updated_at`

### 字段语义

#### `case_id`

统一作为配对组唯一标识。

#### `row_ids`

当前组内所有记录 ID。

#### `row_types`

用于快速判断组的组成，例如：

- `["oa", "bank"]`
- `["bank", "invoice"]`
- `["oa", "bank", "invoice"]`
- `["bank", "bank"]`

#### `status`

第一阶段至少支持：

- `active`
- `cancelled`

#### `relation_mode`

第一阶段至少支持：

- `manual_confirmed`
- `auto_internal_transfer`
- `auto_salary`

#### `month_scope`

用于保留请求上下文，兼容当前 `month=all` 的跨月视图。

## 数据职责拆分

### `pair relations` 负责

- 记录哪些 row 已组成一组配对
- 记录是人工确认还是自动匹配形成
- 为 `取消配对` 提供 O(1) 级别定位入口

### `workbench_row_overrides` 继续负责

- 忽略 / 撤回忽略
- 异常处理 / 撤回异常
- 详情备注覆盖
- 其他非配对类行级覆盖

### 不再让 overrides 负责

- `confirm_link`
- `cancel_link`

## 后端读写路径重构

### 1. 确认关联

当前目标：

- 输入：`row_ids + case_id(optional)`
- 写入：一条 `active pair relation`
- 返回：当前组受影响 rows

不再做：

- 按 row override 逐条保存配对关系

### 2. 取消配对

当前目标：

- 输入：`row_id` 或 `case_id`
- 先从 `pair relations` 定位组
- 把对应 relation 标成 `cancelled` 或删除
- 返回当前组所有 row

不再做：

- 通过 override 推断整个配对组

### 3. 工作台加载

工作台最终 grouped payload 生成逻辑改成：

1. 原始 live rows / OA rows
2. 叠加 `active pair relations`
3. 再叠加 row overrides
4. 再走 candidate grouping

这样能保证：

- 人工确认配对
- 自动工资匹配
- 自动内部往来款匹配

最终都走同一套关系源。

## 自动匹配统一策略

当前系统已有：

- 工资自动匹配
- 内部往来款自动匹配

本轮设计要求把它们逐步统一落进 `pair relations`：

- `工资`：单边银行流水，`relation_mode=auto_salary`
- `内部往来款`：双边银行流水，`relation_mode=auto_internal_transfer`

这样做的收益是：

- 自动匹配和人工确认的展示逻辑统一
- `取消配对` 不再需要区分“这是自动的还是人工的”
- 已配对 / 未配对的边界更稳定

## 前端交互口径

前端保持现有体验方向：

- 动作发出后显示 `处理中`
- 后端成功返回后立即局部更新 UI
- 后台静默刷新整页兜底

但动作耗时要依赖新的轻量写模型下降。

### 确认关联

- 成功后把当前选择从 `未配对` 移到 `已配对`

### 取消配对

- 成功后把当前组从 `已配对` 移到 `未配对`

## Mongo 与索引建议

建议至少建立：

- `case_id + status`
- `row_ids`
- `status`

推荐：

- `row_ids` 上支持按单个 row 查所属 active relation
- `case_id` 上支持唯一 active relation 约束

## 风险与边界

### 1. 双状态源迁移风险

在迁移阶段，系统会短时间同时存在：

- override 中历史配对痕迹
- pair relations 新模型

因此需要明确迁移规则：

- 新写入只写 `pair relations`
- 历史读取优先读 `pair relations`
- 必要时提供一次性迁移脚本，把历史 active pairing 搬到新集合

### 2. 自动匹配兼容

如果只把人工确认改成 `pair relations`，自动匹配仍留旧逻辑，会导致：

- 已配对展示仍有两套来源

所以本轮应至少把工资与内部往来款也接进新集合，或者在读取层统一抽象成同一结构。

### 3. 忽略/异常不应受影响

忽略、异常处理、撤回异常必须继续稳定工作，不能因为关系源拆分导致：

- 行消失
- 错误进入 paired/open
- case 断裂

## 验收标准

### 功能

- `确认关联` 成功后，关系写入 `pair relations`
- `取消配对` 成功后，关系从 `pair relations` 失效
- 自动工资与内部往来款可通过同一关系层进入 `已配对`
- 加载关联台时，`paired/open` 分组仍然正确

### 性能

- `确认关联 / 取消配对` 不再依赖整张关联台重建
- `确认关联 / 取消配对` 不再依赖整份 row override 重写
- 用户感知中的 `处理中` 明显缩短

### 稳定性

- 忽略 / 异常 / 搜索 / 已处理异常 / 已忽略 / 成本统计 / 税金抵扣不被回归打坏
