# Finance Table System Spec-first E2E 合同

## 模块目标

`finance-table-system` 保护财务页面共享表格体验：列角色对齐、分页摘要、筛选/排序/分页参数、横向滚动、窄屏可达性、导出入口、loading/empty/error/unavailable 状态和详情 drawer/dialog 的可读性。共享 `FinanceTable` 只提供展示 primitive；页面级业务查询、权限、direct API contract、导出 API 和写操作由对应页面模块负责。

## 用户角色

- `admin` / `full_access`：可以使用页面允许的表格操作、筛选、排序、分页、详情、导出和写入口。
- `read_export_only`：可以读取和导出允许的数据，但写入口必须隐藏或禁用。
- forbidden / expired session：不能渲染受保护表格或触发 protected API。

## Spec ID

| Spec ID | 业务可见要求 | 优先级 |
| --- | --- | --- |
| `FIN-TABLE-E2E-001` | 共享 pagination、summary、disabled next/previous 和页码边界稳定。 | P1 |
| `FIN-TABLE-E2E-002` | 金额、方向、状态、空值、截断文本和列角色对齐语义稳定；金额/数量右对齐，日期/状态/方向/选择居中，主体/账户/说明左对齐。 | P1 |
| `FIN-TABLE-E2E-003` | 窄屏和宽表可以横向滚动到右侧列；刷新/导出/操作入口不遮挡表格。 | P0 |
| `FIN-TABLE-E2E-004` | 页面级筛选、排序、分页、search 和 tab 状态会进入对应 API query，不因共享表格迁移丢失。 | P0 |
| `FIN-TABLE-E2E-005` | 页面级导出使用当前筛选/排序，不受当前分页限制；row-limit 或 direct payload 暂不可用时不伪成功下载。 | P0 |
| `FIN-TABLE-E2E-006` | direct empty/error 场景不显示普通空态、不泄露旧 rows、不允许写入或导出伪成功。 | P0 |
| `FIN-TABLE-E2E-007` | 表格详情 drawer/dialog 只展示当前 row 的可用详情；暂不可用时显示不可用诊断，不长期 loading。 | P0 |
| `FIN-TABLE-E2E-008` | table session 只保存轻量 UI 状态，并按 page/state/user/columnsVersion 隔离；不保存 rows/read model payload。 | P1 |
| `FIN-TABLE-E2E-009` | 代表性大表格在真实 Chromium 中无 console/page error，关键右侧列可读。 | P0 |
| `FIN-TABLE-E2E-010` | 页面 wrapper 可以保留自身业务差异；共享 primitive 测试不能替代每页筛选/排序/导出/状态测试。 | P0 |

## 数据状态

- `loading`：显示 loading，不使用旧 rows 冒充当前事实。
- `empty`：只在 direct API 明确返回空结果时显示。
- `error` / `unavailable`：必须显示诊断或错误状态，阻止伪成功写入/导出。
- `ready`：允许筛选、排序、分页、详情和导出按页面规则工作。

## 权限规则

- `read_export_only` 可以读取/导出允许数据，但写入口隐藏或禁用，mutation endpoint 零调用。
- admin-only 表格或运维表格必须由 `app-health-operations` / `permissions-and-audit` 保护。
- forbidden/expired session 不触发表格 protected API。

## API / Runtime 边界

- 共享 primitive 不发 HTTP；API contract 由页面 API 和后端模块负责。
- 页面必须把筛选、排序、分页和导出参数作为稳定契约测试。
- direct payload 可用性由页面 API 模块提供；表格不能伪造可用数据。
- 写操作后的真实后台任务或 direct API 收敛由页面业务流 E2E 或 runtime smoke 验证。

## 跨页面影响

本模块影响银行明细、税金抵扣、导入预览、App Health、进项发票使用、待找发票、OA 待付款、销项收款、往来款、成本统计等页面。任何共享 CSS、primitive、pagination、table session 或 wrapper 迁移，都必须回归代表性页面和对应模块的 E2E coverage。

## 不可自动化或外部风险

- 真实生产百万级大数据滚动性能、浏览器下载保存位置、真实 XLSX 打开结果和超宽列组合属于 `external-risk`。
- 本地 Browser smoke 只能证明 deterministic mock/代表性数据；不能证明真实生产数据规模和真实代理下载 header。
