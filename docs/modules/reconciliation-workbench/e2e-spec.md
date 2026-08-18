# 关联台 Spec-first E2E Spec

本文件定义关联台页面的浏览器级业务验收合同。代码只用于定位 route、selector、API mock 和运行细节；验收标准以产品、app 架构和模块状态机为准。

## 模块目标

关联台是银行流水、OA 单据、正式发票/OA 附件发票、ETC 和异常关系的统一核销工作台。它必须让用户在真实浏览器中查看未配对行、选择至少 2 个不同 canonical 成员完成确认、从 paired/unpaired active relation 执行关系级撤回，并通过右上统一抽屉处理系统自动异常；未配对工具栏不再提供人工“异常处理”。页面以 direct canonical API 为唯一事实源；普通写成功后恰好一次 normal GET，其他页面在访问时按自身 owner 合同收敛，不得回退 Workbench projection/cache 或 generation polling。

## 用户角色

| 角色 | 期望 |
| --- | --- |
| `admin` | 可进入关联台并执行业务写操作，同时可访问系统状态。 |
| `full_access` | 可查看关联台、执行确认/撤回/异常等业务操作。 |
| `read_export_only` | 可查看和导出，但不得触发确认、撤回、异常处理等 mutation API。 |
| forbidden/expired session | 不渲染受保护业务页面，不调用受保护页面 API。 |

## 页面状态合同

| 状态 | 验收标准 |
| --- | --- |
| loading | 初次请求时显示加载，不把旧 snapshot 当事实。 |
| empty | 只有 direct canonical GET 成功且目标 zone/group 精确 total 为零时才显示空态。 |
| query unavailable/timeout | 展示可重试 direct read 错误，不显示空 rows，不读旧 projection/cache，不轮询 refresh-status。 |
| error | 展示可恢复错误；不泄露底层 SQL；写入成功但 refetch 失败时必须提示 relation 已写入但页面刷新未完成。 |
| operation pending | 只覆盖确认/撤回 HTTP 请求本身，禁用重复提交和备注编辑；canonical command 成功后关闭写阻塞，清理 selection/cursor 并运行一次 normal direct GET，不等待 operation barrier。 |

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `RECON-WB-E2E-001` | 从未配对行人工确认任意合法成员关系 | P0 | 用户能在 unpaired 区域选择至少 2 个不同 canonical rows；同栏或跨栏均可打开关联预览。只有 `amount_check.requires_note=true` 时继续要求填写 `note`，完整性不阻止创建；提交后零 operation barrier，通过关联台正常 GET 展示 paired 或同-case unpaired relation group，不做本地 optimistic 假移动。 |
| `RECON-WB-E2E-002` | 关联台 confirm 后银行明细 relation tags 更新 | P0 | 从关联台确认后，银行明细重新读取并显示 `有oa` / `有发票`，请求次数增加，不能只依赖前端 event。 |
| `RECON-WB-E2E-003` | 关联台 confirm 后待找发票状态更新 | P0 | 待找发票从 `已支付待开票` 变为 `已支付已开票`，显示发票号码和 OA 申请人。 |
| `RECON-WB-E2E-004` | paired/unpaired active relation withdraw preview/submit | P0 | 两区 active relation 均可关系级撤回，未配对 singleton 不可撤回；显式 row ids 在 preview/submit 都必须与目标 case 的完整 active typed member set 精确相等。preview identity 绑定 current/after relation 的 case/version/status/排序成员和 confirm-history identity。提交在同一 UoW 内依次锁 current 与 predecessor topology，重验 canonical member、restored case 和唯一 active owner后，才从最近 confirm history 的 `before_relations` 恢复上一稳定拓扑；冲突整笔 fail closed，无 predecessor 的成员回 singleton。通过当前页正常 GET 收敛且不等待跨页面 target。 |
| `RECON-WB-E2E-005` | 无正式关系的对象保持可见 | P0 | 历史非正式 automatic metadata 不应合并对象；没有 active relation 时每个对象必须独立显示在 unpaired，撤回 preview 必须拒绝。 |
| `RECON-WB-E2E-006` | direct query failed/timeout 状态 | P0 | direct query 503/超时时显示可重试错误，不显示 false-empty、不读旧 projection/cache、不请求 refresh-status；OA sync dirty/refreshing 仍按独立安全合同禁写。 |
| `RECON-WB-E2E-007` | 写 API 失败或 fresh refetch 失败 | P0 | 写 API 失败不移动行、不发成功 toast；写成功但 refetch 失败时停留在弹窗错误状态，提示不要重复写入。 |
| `RECON-WB-E2E-008` | 权限 gate | P0 | `read_export_only` 不显示或禁用确认、关系级撤回和异常抽屉内写操作，并且不会发出 mutation API；未配对工具栏对任何角色都不显示旧人工“异常处理”。 |
| `RECON-WB-E2E-009` | 统一异常审阅与分区流转 | P1 | OA—流水、OA—发票、流水—发票和附件异常必须默认留在未配对；`290=145+145`、`405=350+55`、`350=150+100+100` 同行且无误报，普通付款关系 `1050-35=1015` 与 OA/发票 `1015` 不生成异常，`turnover_manual_closure` 的同额收支闭环只比较付款本金且不误报。金额异常必须先人工多选具体分类或互斥的“无异常”，附件异常逐项审阅后才可 accept/keep；accept 后 chip 统一显示 `已接受：<原异常>` 并进入已配对异常，撤回后抽屉与主区同步回未配对。每次决定一次 canonical GET、一次目标 bucket GET，零 downstream job；旧 ignore/restore routes 与 UI 不存在。 |
| `RECON-WB-E2E-010` | 大数据/长列表/三栏滚动和详情 | P1 | 两区首屏各保留 10 组且没有手动“加载更多”；滚动接近区底部才自动读取下一页，失败不循环重试；区域搜索可命中尚未加载的全部服务端数据并高亮；详情、焦点和三栏滚动不遮挡关键按钮，不破坏选择状态。 |
| `RECON-WB-E2E-011` | 网络恢复和重复提交 | P1 | 网络失败后用户能重试；重复点击/重复 submit 不创建第二条 active relation。 |
| `RECON-WB-E2E-012` | App Health write safety / OA dirty gate | P1 | `overall.write_safety.blocks_mutations=true` 或 OA dirty/refreshing 时禁写，并在已选择记录的操作区说明禁用原因；OA 状态恢复后按权威 OA status 自动恢复，不引入 Workbench generation/version gate。 |
| `RECON-WB-E2E-013` | 已配对现金流水特殊处理 | P1 | full-access 用户可从已配对银行流水更多菜单执行 `确认为过账`、`确认为买票` 和 `取消现金处理`；买票弹窗必须校验买票成本和项目名称；三个 mutation 都必须携带完整 group row ids，成功后只重跑当前页 GET、零 operation barrier，并且不能出现隐藏错误、浏览器异常或 stale UI。 |
| `RECON-WB-E2E-014` | 关联台金额与 OA 完成时间搜索 | P1 | `202`、`202.0`、`202.00`、`￥202.00`、`¥202.00` 命中同一完整关系组；OA 申请日期和完成时间都可命中。搜索不改变 group membership、异常状态或选择状态。 |
| `RECON-WB-E2E-015` | 三组复合表头筛选与长项目名布局 | P1 | 银行金额菜单显示收支方向、已映射银行账户和 canonical 流水标签，不把已配置账户显示为“未识别”；OA 申请人菜单在已配对与未配对区均固定显示“支付申请 / 日常报销”“已完成 / 进行中”，并显示实际申请人；项目菜单显示 OA 费用类型和项目名称。项目菜单宽度至少 400px，长名称换行后选项随内容增高，相邻选项不得重叠。 |

## 不属于本地 deterministic E2E 的风险

- 真实生产 direct SQL planner/buffer/temp-spill 与长尾。
- 真实 PostgreSQL 连接池，以及保留的 RabbitMQ/systemd relation/matching worker drain。
- 真实 OA Mongo/iframe/cookie。
- 大数据 P95/P99 性能和生产历史污染 repair。

这些必须在 staging、生产只读 audit 或 runbook smoke 中验证，不能写成本地 CI 已覆盖。
