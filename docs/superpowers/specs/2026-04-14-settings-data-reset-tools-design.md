# 设置页数据清理与 OA 重刷工具设计

日期：2026-04-14

## 目标

在关联台设置页新增一组高风险管理工具，用于支持财务在“清空旧导入数据后重新导入”的场景下，按域清理应用库数据，并支持按 `保OA` 日期重新构建 OA 相关数据。

本轮设计覆盖三个动作：

- `清除所有银行流水数据`
- `清除所有发票（进销）数据`
- `清除所有 OA 数据并重新写入`

其中第三项固定采用 **模式 B：彻底重刷 OA 相关状态**。

## 核心边界

### 1. 只操作应用库，不操作 OA 源库

工具按钮只允许操作 `fin_ops_platform_app`。

禁止操作：

- `form_data_db.form_data`

原因：

- `form_data_db.form_data` 是 OA 源数据
- 当前系统所有 OA、项目主数据、OA 附件发票解析都从这里读取
- “清 OA” 的正确语义是“清 app 侧缓存 / 派生状态，再重读 OA 源数据”，不是删除 OA 原始记录

### 2. 不允许清全局配置

以下数据绝不能被管理工具删除：

- `app_settings`
- 所有 `*_meta`
- `import_file_metadata`

原因：

- `app_settings` 承载 `保OA` 时间、银行映射、访问账号权限、列布局等全局配置
- `*_meta` 和 `import_file_metadata` 是内部元数据，不应该暴露为用户级清理目标

### 3. 清理必须按“业务域”成组执行

不能只删单表。

例如：

- 只删 `bank_transactions` 会残留指向已删除流水的 `pair relations`
- 只删 `invoices` 会残留匹配结果、税金认证记录和 read model
- 只删导入记录不删 GridFS 原文件，会留下无主文件

因此每个按钮都必须由后端按固定集合组一次性执行。

## 三个按钮的语义

### A. 清除所有银行流水数据

目标：

- 删除 app 内已导入的银行流水
- 删除依赖这些流水的匹配结果与关联状态
- 清空相关缓存与读模型

应清集合：

- `bank_transactions`
- `matching_runs`
- `matching_results`
- `workbench_pair_relations`
- `workbench_row_overrides`
- `workbench_read_models`

建议同时清理的导入历史：

- `import_batches`
  - 仅限 `batch_type=bank_transaction`
- `file_import_sessions`
  - 仅限和银行导入相关的 session
- `file_import_files`
  - 仅限银行导入文件
- `import_file_blobs.files`
- `import_file_blobs.chunks`
  - 仅限上述文件对应 blob

执行后效果：

- 银行流水清空
- 银行相关已配对、异常、忽略状态清空
- 页面后续按剩余发票 / OA 重建

### B. 清除所有发票（进销）数据

目标：

- 删除 app 内已导入的进项票和销项票
- 删除依赖这些发票的匹配结果与税金认证结果
- 清空相关缓存与读模型

应清集合：

- `invoices`
- `matching_runs`
- `matching_results`
- `workbench_pair_relations`
- `workbench_row_overrides`
- `workbench_read_models`
- `tax_certified_import_batches`
- `tax_certified_import_records`

建议同时清理的导入历史：

- `import_batches`
  - 仅限 `batch_type in (input_invoice, output_invoice)`
- `file_import_sessions`
  - 仅限发票导入 session
- `file_import_files`
  - 仅限发票文件
- `import_file_blobs.files`
- `import_file_blobs.chunks`
  - 仅限上述文件对应 blob

边界说明：

- 本动作不删除 OA 源表
- 本动作也不直接删除 OA 附件发票缓存，除非用户另外执行 “清 OA 并重写”

### C. 清除所有 OA 数据并重新写入

目标：

- 清空 app 侧 OA 缓存、派生状态和人工处理状态
- 再按 `app_settings.oa_retention.cutoff_date` 从 OA 源库重新加载

固定采用模式 B：

- 清缓存
- 清 read model
- 清 pair relations
- 清 row overrides
- 再触发完整 OA 重建

应清集合：

- `oa_attachment_invoice_cache`
- `workbench_read_models`
- `workbench_pair_relations`
- `workbench_row_overrides`

执行后应做的重建动作：

1. 读取 `app_settings.oa_retention.cutoff_date`
2. 从 `form_data_db.form_data` 重新加载：
   - `form_id = 2`
   - `form_id = 32`
   - `form_id = 17`
3. 按 `保OA` 日期过滤
4. 重新构建：
   - OA 行
   - OA 附件发票缓存
   - workbench read model
   - 搜索索引相关缓存

执行后效果：

- 所有 OA 相关人工配对 / 异常 / 忽略状态一并清零
- OA 重新回到“仅由源数据 + 当前保OA规则决定”的状态

## 访问控制

这组工具应视为危险操作，只允许管理员可见和可用。

建议口径：

- 仅 `admin_usernames` 可见
- 只读导出账号不可见
- 普通全量操作账号也不可见
- 每次执行动作前，必须要求当前登录用户输入自己的 OA 系统密码
- 后端必须校验该密码属于当前 OA 会话用户，校验通过后才允许清理
- OA 密码只用于本次复核，不允许保存、写日志、写审计明文或在响应中返回

原因：

- 这不是普通业务设置
- 这是数据域级重置
- 不应放给所有能保存设置的用户
- 管理员会话被误用时，密码复核可以降低误触和越权清理风险

## 前端交互设计

### 1. 位置

放在现有 `关联台设置` 的树状两栏结构中，新增一个单独分组：

- `数据重置`

### 2. 交互

每个动作均采用：

- 危险说明
- 明确影响范围
- 二次确认
- 当前 OA 用户密码输入弹窗
- 执行中状态
- 成功 / 失败反馈

确认流程必须是：

1. 用户点击三个危险按钮之一
2. 前端展示影响范围和二次确认
3. 用户确认后，弹出 OA 密码输入框
4. 用户输入当前登录 OA 账户的 OA 系统密码
5. 前端只把密码随本次 reset 请求发送给后端，不在本地持久化
6. 后端校验密码通过后才执行清理；校验失败则返回错误，且不得执行任何删除或重建动作

密码弹窗要求：

- 只显示密码输入框，不允许切换或输入其他 OA 用户名
- 文案明确说明“请输入当前 OA 用户密码以确认本次高风险操作”
- 点击取消时立即关闭弹窗，不执行动作
- 错误提示不能回显用户输入的密码
- 前端日志、调试输出、请求摘要里不能打印密码

### 3. 文案要求

按钮不能写成模糊的“清理”或“刷新”，而要明确写出作用域。

建议主文案：

- `清除所有银行流水数据`
- `清除所有发票（进销）数据`
- `清除所有 OA 数据并重新写入`

建议补充说明：

- `将清空银行流水、相关匹配结果和配对状态，不影响 OA 源库`
- `将清空导入发票、税金认证记录和相关配对状态`
- `将按保OA日期彻底重刷 OA 相关状态，已处理的 OA 配对 / 异常 / 忽略也会被清空`

### 4. 执行模式

按钮点击后不应由前端串多个 API。

正确方式：

- 前端调用单一后端动作 API
- 后端完成整组清理
- 后端负责失效缓存与触发重建
- 前端只展示执行状态与最终结果

## 后端实现边界

建议新增独立的“设置页管理动作”服务，而不是把清理逻辑散落到多个现有 service。

职责：

- 校验权限
- 校验当前 OA 用户密码复核
- 执行按域清理
- 触发失效
- 触发 OA 重建
- 返回影响摘要

后端密码复核要求：

- reset API 入参可以包含一次性的 `oa_password`
- `oa_password` 必须绑定当前 session 解析出的 OA 用户，不能允许客户端指定另一个用户名
- 密码校验失败时直接返回明确错误，不允许执行任何清理、失效或重建
- `oa_password` 不允许落库、不允许写审计日志、不允许写异常堆栈、不允许出现在响应 payload
- 审计日志只记录用户、动作、时间、结果和影响摘要，不记录密码
- 如现有 OA 身份服务支持限流或失败次数控制，应复用；否则至少为该接口预留失败次数限制测试点

返回 payload 建议至少包含：

- `action`
- `status`
- `cleared_collections`
- `deleted_counts`
- `rebuild_status`
- `message`

## 风险与防护

### 高风险

- 误删 `form_data_db.form_data`
- 误删 `app_settings`
- 部分集合删了，部分没删，造成悬挂状态

### 中风险

- OA 重刷期间首次加载变慢
- GridFS 原文件未联动删除导致库膨胀
- 发票或流水被清理后，税金页 / 关联台出现短时空白

### 防护要求

- 后端固定白名单集合，不允许用户传 collection 名
- 后端强制做当前 OA 用户密码复核，不允许只依赖前端弹窗
- 管理动作必须写审计日志
- 审计日志和错误日志必须脱敏，严禁包含 OA 密码
- 返回明确删除计数
- OA 重建失败时要能返回“已清理但重建失败”的明确状态

## 拆分为多任务 Prompt

本需求不适合单 prompt 混做，建议拆为三段：

### Prompt 50：后端底座与安全边界

范围：

- 新增管理动作 service
- 明确三类 reset action
- 建立固定集合白名单
- 增加当前 OA 用户密码复核
- 接通后端 API
- 补后端测试

### Prompt 51：设置页 UI 与 OA 重刷联动

范围：

- 设置页新增 `数据重置` 分组
- 三个危险按钮与确认流程
- 三个危险按钮执行前都弹出当前 OA 用户密码输入
- 执行中 / 成功 / 失败状态
- `清 OA` 固定采用模式 B
- 接通前端 API 和回刷

### Prompt 52：联调、QA 与文档收口

范围：

- 验证三类 reset action 的删表范围
- 验证 OA 按 `保OA` 日期重建
- 验证普通账号不可见
- 验证未输入或输错当前 OA 用户密码时不会执行清理
- 更新 README / 产品文档 / 回归测试

## 结论

这组工具是可行的，但必须满足四个条件：

- 只清 `fin_ops_platform_app`
- 固定集合组操作，不能随意删单表
- 每次执行必须通过当前 OA 用户密码复核
- `清 OA` 固定采用模式 B：彻底重刷 OA 相关状态
