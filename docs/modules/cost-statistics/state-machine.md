# 成本统计状态机

成本统计没有后台刷新状态机。

```text
idle
  -> loading
      -> ready
      -> error
error
  -> 用户刷新
      -> loading

ready
  -> searching / changing-surface
      -> ready（只替换内容区）
      -> error（保留已加载上游内容）
  -> loading-page
      -> ready（成功后原子替换当前页 rows）
      -> page-error（保留当前已确认页，可局部重试）

detail-closed
  -> detail-loading（抽屉立即打开）
      -> detail-ready
      -> detail-error
detail-error
  -> detail-loading（抽屉内重试）
detail-loading / detail-ready / detail-error
  -> detail-closed（关闭并取消未完成请求）

no-oa-drawer-closed
  -> no-oa-drawer-ready（打开现有“无 OA 成本范围”抽屉）
      -> saving
          -> no-oa-drawer-ready（保存成功并刷新成本数据）
          -> save-error（保留用户输入，可重试）
  -> no-oa-drawer-closed

manual-allocation-closed
  -> manual-allocation-loading（打开右侧 Drawer 后才请求全局队列）
      -> manual-allocation-ready
      -> manual-allocation-error
manual-allocation-ready
  -> pending / allocated 切换（服务端 status/search/cursor 分页）
  -> editing（首次 pending/stale 输入为空；allocated 显示逐 OA 单元金额和可选非成本金额）
      -> 切换关系/状态/搜索/关闭（有未保存输入时先确认丢弃）
      -> saving
          -> manual-allocation-ready（保存成功并刷新当前归因视图）
          -> validation-error（保留输入）
          -> conflict（事实或版本变化，要求重新加载）
manual-allocation-loading / manual-allocation-ready / manual-allocation-error
  -> manual-allocation-closed
```

## 状态合同

- `loading`：当前 HTTP 请求尚未完成，按钮和页面展示正常加载反馈。
- `ready`：响应全部来自同一个数据库一致性快照。
- `error`：本次请求失败，不显示旧数据为 fresh。
- `searching / changing-surface`：当前视图搜索、范围或下钻请求进行中，只显示内容区反馈，不清空页头或刷新整个页面。
- `loading-page`：用户显式点击上一页或下一页后，使用目标页 cursor 请求固定 20 条；同一时间只允许一个分页请求，当前已确认页保持可见但分页操作禁用。
- `page-error`：目标页失败不提交页码、不丢弃当前 rows，只在明细区提供目标页重试；滚动不触发请求。
- `detail-loading`：只在右侧抽屉展示无文字 skeleton；不显示“正在加载流水”，不修改 explorer/导出 loading 状态。
- `detail-error`：错误与重试按钮只存在于抽屉；已加载统计内容保持不变。
- `no-oa-drawer-ready`：只显示当前实际无 active OA 关系的支出标签；名称和标签默认都为空。选择标签后必须填写虚拟项目名，未选择标签时名称可为空。
- `saving / save-error`：使用 settings version CAS；冲突或失败不得伪报成功，也不得清空用户输入。保存成功后下一次 canonical GET 对全部历史期间逐笔应用规则。
- `manual-allocation-loading`：只有用户在三个项目成本 view 中打开“待分配” Drawer 后才读取全局队列的有界任务页；两个流水 view 不显示该入口，也不读取人工分配。
- `pending / allocated`：pending 视图包含 pending 与 stale，allocated 只含当前有效人工分配；两者都使用服务端 search 和稳定 cursor，计数来自同一次全局任务快照，不由浏览过的成本项累积。
- `editing`：每个关系以 Disclosure 独立展开并维护自己的草稿和保存按钮。支付申请整单一个输入；日常报销逐 canonical 子付款项一个输入，不按流水重复。pending/stale 不预填数字、不自动计算；allocated 显示已保存值并允许编辑。勾选“不计入成本金额”后才显示 `X` 和原因；显式 `0.00` 有效，空值与零值必须区分。
- `saving`：服务端在单个写事务内锁定当前关系事实，校验 source fingerprint、expected version、完整 OA 单元集合、非负两位小数及 `C+X=N`；`X>0` 时原因必填，`X=0` 时原因不得提交。成功后只移动/刷新当前关系并写 allocation 与 audit。
- `validation-error`：格式、缺项、负数或合计错误返回明确 400；页面保留用户输入。
- `conflict`：事实或版本已变化返回明确 409；旧输入不得作为 fallback 写入，重新加载后以新的空白任务为准。
- 重新访问、浏览器刷新或页面内刷新都会发起全新请求；没有 `202 refreshing`、`409 read_model_not_fresh` 或后台轮询。
- 页面打开期间事实源发生变化时不主动推送；用户下次刷新读取最新已提交事实。
