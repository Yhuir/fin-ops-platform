# 关联台 Spec-first E2E Spec

本文件定义关联台页面的浏览器级业务验收合同。代码只用于定位 route、selector、API mock 和运行细节；验收标准以产品、app 架构和模块状态机为准。

## 模块目标

关联台是银行流水、OA 单据、正式发票/OA 附件发票、ETC 和异常关系的统一核销工作台。它必须让用户在真实浏览器中查看未配对行、完成三栏选择、确认、撤回和异常处理；普通写后只让当前可见页面重新 GET，其他页面在访问时各自收敛，并且不能在 read model 非 fresh 时伪装成功。

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
| empty | 只有 fresh active generation 下目标 zone/group 为空时才显示空态。 |
| refreshing/stale | 展示刷新/陈旧提示；不能把空 rows 当真实无候选；普通 Workbench active generation stale 不全局禁用无关 group 写操作。 |
| error | 展示可恢复错误；不泄露底层 SQL；写入成功但 refetch 失败时必须提示 relation 已写入但页面刷新未完成。 |
| operation pending | 只覆盖确认/撤回 HTTP 请求本身，禁用重复提交和备注编辑；canonical command 成功后关闭写阻塞，当前关联台通过正常 GET 进入 refreshing/fresh，不等待 operation barrier。 |

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `RECON-WB-E2E-001` | 从未配对行确认 OA + 银行流水 + 发票关系 | P0 | 用户能进入 unpaired 区域，选择三栏 row，打开关联预览，看到操作前/操作后三栏和金额状态；提交后零 operation barrier，通过关联台正常 GET 展示 paired group，不做本地 optimistic 假移动。 |
| `RECON-WB-E2E-002` | 关联台 confirm 后银行明细 relation tags 更新 | P0 | 从关联台确认后，银行明细重新读取并显示 `有oa` / `有发票`，请求次数增加，不能只依赖前端 event。 |
| `RECON-WB-E2E-003` | 关联台 confirm 后待找发票状态更新 | P0 | 待找发票从 `已支付待开票` 变为 `已支付已开票`，显示发票号码和 OA 申请人。 |
| `RECON-WB-E2E-004` | 关联台 withdraw preview/submit | P0 | 已配对 group 可撤回；preview 锁定 `operation_type`、`preview_id`、`submit_expected_versions`；提交后通过当前页正常 GET 让 row 独立回 unpaired，不等待跨页面 target。 |
| `RECON-WB-E2E-005` | 无正式关系的对象保持可见 | P0 | 历史非正式 automatic metadata 不应合并对象；没有 active relation 时每个对象必须独立显示在 unpaired，撤回 preview 必须拒绝。 |
| `RECON-WB-E2E-006` | stale/refreshing/read model failed 状态 | P0 | stale/refreshing 时页面提示状态；不能把空 rows 当真实无候选；OA sync dirty/refreshing 禁写，普通 Workbench stale 不全局禁用无关 group。 |
| `RECON-WB-E2E-007` | 写 API 失败或 fresh refetch 失败 | P0 | 写 API 失败不移动行、不发成功 toast；写成功但 refetch 失败时停留在弹窗错误状态，提示不要重复写入。 |
| `RECON-WB-E2E-008` | 权限 gate | P0 | `read_export_only` 不显示或禁用确认/撤回/异常写入口，并且不会发出 mutation API。 |
| `RECON-WB-E2E-009` | 统一异常抽屉与 OA/发票异常 ignore/restore | P1 | legacy 异常、按 OA 子付款项/支付申请比较的精确金额差异和 `OA发票附件缺失` 都从统一右侧抽屉处理；`290=145+145`、`405=350+55` 同行且无误报，一个比较单元只显示一个 chip。入口显示 `异常 n | 已忽略 m`，抽屉默认折叠三栏计数/总金额、展开完整成员；异常可忽略并撤回，主表 chip 与计数同步；操作后只通过当前关联台正常 GET 更新页面，closed exception relation 必须走 canonical command service，零 downstream job。 |
| `RECON-WB-E2E-010` | 大数据/长列表/三栏滚动和详情 | P1 | 两区首屏各保留 50 组且没有手动“加载更多”；滚动接近区底部才自动读取下一页，失败不循环重试；区域搜索可命中尚未加载的全部服务端数据并高亮；详情、焦点和三栏滚动不遮挡关键按钮，不破坏选择状态。 |
| `RECON-WB-E2E-011` | 网络恢复和重复提交 | P1 | 网络失败后用户能重试；重复点击/重复 submit 不创建第二条 active relation。 |
| `RECON-WB-E2E-012` | App Health write safety / OA dirty gate | P1 | `overall.write_safety.blocks_mutations=true` 或 OA dirty/refreshing 时禁写，并在已选择记录的操作区说明禁用原因；关联台专属 OA 状态恢复且 active generation fresh/version ready 后自动恢复，不等待较慢的全局 App Health 聚合刷新。 |
| `RECON-WB-E2E-013` | 已配对现金流水特殊处理 | P1 | full-access 用户可从已配对银行流水更多菜单执行 `确认为过账`、`确认为买票` 和 `取消现金处理`；买票弹窗必须校验买票成本和项目名称；三个 mutation 都必须携带完整 group row ids，成功后只重跑当前页 GET、零 operation barrier，并且不能出现隐藏错误、浏览器异常或 stale UI。 |

## 不属于本地 deterministic E2E 的风险

- 真实生产 active generation 全量回放。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。
- 真实 OA Mongo/iframe/cookie。
- 大数据 P95/P99 性能和生产历史污染 repair。

这些必须在 staging、生产只读 audit 或 runbook smoke 中验证，不能写成本地 CI 已覆盖。
