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
  -> editing（固定目标或有效决定回填；未知金额/来源为空）
      -> 切换关系/状态/搜索（保留各任务草稿）；关闭/显式重读（脏草稿确认）
      -> saving
          -> manual-allocation-ready（按响应状态留在 pending 或移到 allocated，刷新当前视图）
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
- `manual-allocation-loading`：只有用户在三个项目成本 view 中打开“待分配” Drawer 后才读取全局关系任务的有界摘要页，展开后定向读取详情；两个流水 view 不显示该入口，也不读取人工分配。
- `pending / allocated`：pending 视图包含 pending 与 stale，allocated 包含当前已解决的来源分配；两者都使用服务端 search 和稳定 cursor，计数来自同一次全局任务快照，不由浏览过的成本项累积。
- `editing`：OA 单元下可以新增/删除来源行。选支出后展示只读账户、主/子标签和付款日期。固定目标不可改，人工目标按来源行精确汇总，零行默认未分配；允许时显式设零，新增取消零标记。当前有效 source_allocations 即使仍 pending 也回填；stale 决定不回填。
- `saving`：一次事务复核版本、事实、OA 目标、逐银行/退款/单元闭合及 C+X=N；只写分配与审计。按钮只在当前任务真正保存时禁用，错误保留输入。
- `allocated`：已确定来源且所需银行信息完整；`pending` 原因为 amount_required/source_required/allocation_stale/bank_tag_missing/bank_account_missing/source_date_missing，可同时存在。保存 200 不等于 allocated，只有状态改变才移动任务和调整计数。
- `validation-error`：400 保留输入；客户端不完整金额先就地提示，不发送 PUT。
- `conflict`：409 保留草稿与“重新读取当前事实”操作；显式重读时确认替换草稿，绝不自动套用旧值。
- 重新访问、浏览器刷新或页面内刷新都会发起全新请求；没有 `202 refreshing`、`409 read_model_not_fresh` 或后台轮询。
- 页面打开期间事实源发生变化时不主动推送；用户下次刷新读取最新已提交事实。


## 紧凑编辑器的保存与读取状态

- 两栏证据分别展示 OA 成本单元与真实流水，标题按展示行计数；下表每行绑定一个成本项和支出来源，新增位于该项首行操作格。表单无网络 I/O，容器负责会话草稿和 GET/PUT。
- 详情读取失败显示重试，不能渲染成无 OA/无流水。重新读取期间锁定当前表单，避免覆盖新输入。
- 4xx 保存拒绝保留草稿，409明确事实变化；权限错误不伪装成功。
- 网络超时、5xx或成功响应无法解析：进入“保存结果待确认”，保留提交对象，暂停再次编辑/提交。用户核实仅GET，必须同时核对版本推进、fingerprint及全部实际金额/来源内容，不能只凭版本认定成功。核实失败仍保留草稿，可显式重新读取并确认替换。
- 保存已确认成功后，统计刷新独立进行；读取失败由页面错误/重试呈现，不能触发第二次PUT。任务状态按服务端响应更新。
- 单条详情与保存15秒超时。Cost PUT显式禁用通用客户端已有的HTML换前缀重试，防止不明确结果被二次提交；其他调用者的既有行为不变。

- 输入校验按来源/金额/owner 独立定位；刚新增或只选择来源不提示未触碰的金额。实际编辑后失焦或提交显示红框与可聚焦短浮层，首次提交主动展开首个原因，不插入单元格说明段落。

## 2026-09-10 预填草稿

`pending + 未保存 + 关联内唯一允许组合 → 详情返回建议 → 可编辑会话草稿 → 用户保存 → 既有 pending/allocated 判断`。

读取建议不发生状态转换或写入，未保存建议不进入统计。没有唯一允许组合、搜索超限、过期、曾保存、非固定目标或存在退款/非成本时不预填；完整候选枚举后可独立证明唯一的组件可预填，其他子组仍为空。折叠/展开和重新渲染不覆盖用户输入，已清空的草稿不被重新填回。
