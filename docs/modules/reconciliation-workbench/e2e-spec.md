# 关联台 Spec-first E2E Spec

本文件定义关联台页面的浏览器级业务验收合同。代码只用于定位 route、selector、API mock 和运行细节；验收标准以产品、app 架构和模块状态机为准。

## 模块目标

关联台是银行流水、OA 单据、正式发票/OA 附件发票、ETC 和异常关系的统一核销工作台。它必须让用户在真实浏览器中完成候选查看、三栏选择、确认、撤回、异常处理和跨页面 relation fan-out；页面读取 direct Workbench API DTO，不再消费 legacy freshness。

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
| empty | direct Workbench API 返回目标 zone/group 为空时显示空态。 |
| refreshing/stale | 展示 OA sync、App Health 或 backend diagnostic；不能把 unavailable direct payload 的空 rows 当真实无候选；legacy Workbench active generation stale 不全局禁用无关 group 写操作。 |
| error | 展示可恢复错误；不泄露底层 SQL；写入成功但 refetch 失败时必须提示 relation 已写入但页面刷新失败。 |
| operation pending | 确认/撤回 preview 提交后留在弹窗内阻塞，禁用关闭、取消、重复提交和备注编辑；写成功后应用后端 projection 或 direct refetch 后关闭，不请求 operation barrier。 |

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `RECON-WB-E2E-001` | 从候选三栏确认 OA + 银行流水 + 发票关系 | P0 | 用户能进入 open group，选择三栏 row，打开关联预览，看到操作前/操作后三栏和金额状态，提交后直接投影或重新读取后页面展示 paired group，不做本地 optimistic 假移动。 |
| `RECON-WB-E2E-002` | 关联台 confirm 后银行明细 relation tags 更新 | P0 | 从关联台确认后，银行明细重新读取并显示 `有oa` / `有发票`，请求次数增加，不能只依赖前端 event。 |
| `RECON-WB-E2E-003` | 关联台 confirm 后待找发票状态更新 | P0 | 待找发票从 `已支付待开票` 变为 `已支付已开票`，显示发票号码和 OA 申请人。 |
| `RECON-WB-E2E-004` | 关联台 withdraw preview/submit | P0 | 已配对 group 可撤回；preview 锁定 `operation_type`、`preview_id`、`submit_expected_versions`；提交后未恢复 row 独立回 open；弹窗内阻塞直到 operation projection 或 direct refetch 返回。 |
| `RECON-WB-E2E-005` | 自动候选 split_candidate | P0 | 未配对区纯 automatic decision/candidate 点击统一按钮时，后端 preview 判定 `split_candidate`，submit 后 suppress 候选并刷新，不能当 active relation withdraw。 |
| `RECON-WB-E2E-006` | direct unavailable / backend failed 状态 | P0 | direct payload 不可用时页面提示状态；不能把空 rows 当真实无候选；OA sync dirty/refreshing 禁写，普通 backend diagnostic 不全局禁用无关 group。 |
| `RECON-WB-E2E-007` | 写 API 失败或 direct refetch 失败 | P0 | 写 API 失败不移动行、不发成功 toast；写成功但 refetch 失败时停留在弹窗错误状态，提示不要重复写入。 |
| `RECON-WB-E2E-008` | 权限 gate | P0 | `read_export_only` 不显示或禁用确认/撤回/异常写入口，并且不会发出 mutation API。 |
| `RECON-WB-E2E-009` | 异常处理 apply/cancel/ignore | P1 | 异常 preview/apply/cancel/ignore 后通过 direct refetch 更新页面；closed exception relation 必须走 command service。 |
| `RECON-WB-E2E-010` | 大数据/长列表/三栏滚动和详情 | P1 | 大量 group 下筛选、分页、详情抽屉、焦点和三栏滚动不遮挡关键按钮，不破坏选择状态。 |
| `RECON-WB-E2E-011` | 网络恢复和重复提交 | P1 | 网络失败后用户能重试；重复点击/重复 submit 不创建第二条 active relation。 |
| `RECON-WB-E2E-012` | App Health write safety / OA dirty gate | P1 | `overall.write_safety.blocks_mutations=true` 或 OA dirty/refreshing 时禁写，并保留读侧诊断。 |
| `RECON-WB-E2E-013` | 已配对现金流水特殊处理 | P1 | full-access 用户可从已配对银行流水更多菜单执行 `确认为过账`、`确认为买票` 和 `取消现金处理`；买票弹窗必须校验买票成本和项目名称；三个 mutation 都必须携带完整 group row ids、直接投影或重新读取，并且成功后不能出现隐藏的错误弹窗、浏览器异常或 stale UI。 |

## 不属于本地 deterministic E2E 的风险

- 真实生产历史 SQL/active generation 存储迁移审计。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd 后台任务收敛。
- 真实 OA Mongo/iframe/cookie。
- 大数据 P95/P99 性能和生产历史污染 repair。

这些必须在 staging、生产只读 audit 或 runbook smoke 中验证，不能写成本地 CI 已覆盖。
