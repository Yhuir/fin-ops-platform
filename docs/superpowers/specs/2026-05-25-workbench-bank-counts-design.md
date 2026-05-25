# 关联台银行流水计数一致性设计

日期：2026-05-25

## 背景

银行明细页面展示所有已导入银行流水。关联台同样消费银行流水，并把银行流水与 OA、发票、免 OA 批次、异常处理等关系组合展示。

当前生产数据中，银行明细页面显示流水 `431` 条。关联台页面用户看到“已配对 67 项、未配对 194 项”，直觉上严重少于银行明细流水数。经查，这不是银行流水漏导入，也不是关联台完全漏投影，而是计数口径混用了：

- 银行明细事实源是 `app.bank_transactions`，当前非删除流水为 `431` 条。
- 银行明细 SQL 读模型 `read_model.bank_detail_rows` 按月合计也是 `431` 条。
- 关联台 `all` scope 展开 `collapsed_rows.bank` 后，真实银行流水集合也是 `431` 条，缺失 `0`，多余 `0`。
- 关联台已配对区存在免 OA 批次折叠。多条真实流水被压成一条 `source_kind=no_oa_bank_batch_summary` 摘要行，原始流水保存在 `collapsed_rows.bank`。
- 当前 `workbench_summary.bank_count` 和 `/api/workbench/groups` 的 `row_counts.bank` 会把摘要行当作银行行，并且在部分路径只统计 `bank_rows`，没有按统一事实口径统计 `collapsed_rows.bank`。

因此，截图里的银行明细 `431` 是正确的；关联台缺的是生产级计数契约，而不是临时前端补数。

## 目标

- 建立统一口径：银行明细真实流水数必须等于关联台真实银行流水集合数。
- 区分事实行和展示行，避免免 OA 摘要行污染银行流水事实计数。
- 保留免 OA 批次折叠展示，不牺牲关联台性能和可读性。
- 让 `summary`、`groups page`、`group detail`、前端区域标题、栏位标题使用同一套计数契约。
- 增加自动化校验，防止未来读模型、折叠展示或特殊关系再次引入计数漂移。

## 非目标

- 不重做银行流水 Excel 导入、预览、确认和幂等防重。
- 不取消免 OA 批次折叠展示。
- 不把计数修复做成前端临时加法。
- 不改变手工配对、免 OA 批次、异常处理的业务事实模型。
- 不把关联台区域标题改成 group 数；group 数继续只用于分页和内部组织。

## 已确认口径

### 银行明细口径

银行明细流水数是事实数：

```sql
select count(*)
from app.bank_transactions
where status <> 'deleted';
```

在当前数据中，该值为 `431`。

### 关联台真实银行流水口径

关联台真实银行流水数按 row id 集合统计：

- 普通组：统计 `bank_rows` 中真实银行流水。真实银行流水判定为 `type=bank`，且 `source_kind` 缺失、为空或不等于 `no_oa_bank_batch_summary`。
- 免 OA 折叠组：统计 `collapsed_rows.bank` 中的真实银行流水。
- 摘要行：`source_kind = no_oa_bank_batch_summary` 只作为展示行，不计入真实银行流水事实数。
- 同一 scope 内同一真实银行流水 row id 只能计一次。
- `open` 与 `paired` 两个主展示区的真实银行流水集合应互斥。

计数等式分两层：

- 主 zone 等式：`summary.bank_count = zone_counts.open.bank + zone_counts.paired.bank`。
- 银行明细对齐等式：`bank_detail_count = summary.bank_count + ignored_bank_count`。

当前数据 `ignored_bank_count = 0`，因此 `431 = 237 + 194` 成立。如果未来存在已忽略银行流水，`open + paired` 可以小于银行明细事实数，但差额必须由 `ignored_bank_count` 解释。

`source_kind` 判定必须使用显式等于摘要行的排除规则，不能写成会排除 null 的 SQL 谓词。例如 `coalesce(source_kind, '') <> 'no_oa_bank_batch_summary'` 是合法口径，裸 `source_kind <> 'no_oa_bank_batch_summary'` 不是合法口径。

辅助视图口径：

- 已忽略行不进入 `open|paired` zone，因此不参与 `open.bank + paired.bank = bank_count` 的主等式。
- 已处理异常如果被投影为 `paired` 的 processed-exception group，则参与 `paired` 事实计数。
- 仍处于 open/confirmed/reopened 的异常 case 留在 `open`，参与 `open` 事实计数。
- 如果一条非删除银行流水只存在于已忽略辅助视图，银行明细与关联台主 zone 会产生预期差异；一致性诊断必须单独报告 `ignored_bank_count`，并用 `bank_detail_count = summary.bank_count + ignored_bank_count` 解释差异，不能静默把忽略行混入 `open|paired`。

当前数据按该口径为：

| 区域 | 真实银行流水 |
| --- | ---: |
| 已配对 | 237 |
| 未配对 | 194 |
| 合计 | 431 |

### 关联台展示行口径

展示行是 UI 行，不等于事实行：

- 免 OA 折叠组显示一条摘要行。
- 摘要行可参与“当前显示多少行”的说明，但不能参与真实银行流水数量。
- 折叠组必须能明确展示“1 条摘要 / N 条流水”。

当前数据中，`all` scope 已配对区有 `45` 条免 OA 摘要展示行，代表 `215` 条折叠真实银行流水。

## 后端设计

### 1. 标准化 group 计数字段

每个 workbench group 输出两类计数：

```json
{
  "row_counts": {
    "oa": 1,
    "bank": 12,
    "invoice": 0,
    "rows": 13
  },
  "display_row_counts": {
    "oa": 1,
    "bank": 1,
    "invoice": 0,
    "rows": 2
  }
}
```

约定：

- `row_counts` 是事实行数，兼容当前前端已使用字段，优先保持语义为真实业务项数。
- `display_row_counts` 是可见展示行数，仅用于解释折叠显示。
- 对非折叠组，两者通常相同。
- 对免 OA 折叠组，`row_counts.bank = len(collapsed_rows.bank)`，`display_row_counts.bank = 1`。
- 如果未来其他类型也折叠，必须复用同一规则，不新增平行字段。

### 2. 修正 SQL read model 持久化

保存 `read_model.workbench_groups` 时，不能靠 `jsonb_array_length(payload->'bank_rows')` 推断事实行数。

投影阶段应在 group payload 中写入标准化计数：

- 遍历 `oa_rows`、`bank_rows`、`invoice_rows` 和 `collapsed_rows`。
- 识别展示摘要行 `source_kind=no_oa_bank_batch_summary`。
- 对事实计数，排除摘要行，纳入折叠原始行。
- 对展示计数，统计实际 `*_rows` 可见行。
- `row_count` 列保存事实行总数。
- `read_model.workbench_group_rows` 继续保存真实可筛选行；如果当前 group rows 已包含摘要行和折叠原始行，需要明确 `row_role = summary|collapsed|normal` 或等价字段，避免搜索、筛选、统计再次混淆。

### 3. 修正 summary 查询

`GET /api/workbench/summary` 的 `summary` 必须来自事实计数：

- `summary.bank_count` 等于 scope 内真实银行流水去重数。
- `summary.zone_counts.open.bank + summary.zone_counts.paired.bank` 等于 `summary.bank_count`。
- `zone_counts.*.rows` 等于该 zone 三栏事实行合计。
- `paired_count` 和 `open_count` 继续表示 group 数时，必须在 API 文档中明确；前端区域标题不得再用它们显示“项”。
- 银行明细全量对齐不由 `summary.bank_count` 单独表达，而由诊断字段表达：`bank_detail_count = summary.bank_count + ignored_bank_count`。

对于 `all` scope，可以从 materialized `workbench_summary` 读取。如果 materialized summary 不存在，需要 fallback SQL 也使用同一事实计数函数，而不是重新写一套 `jsonb_array_length` 逻辑。

### 4. 修正 groups page 查询

`GET /api/workbench/groups` 的 `row_counts` 返回当前查询条件下、分页之前的事实行数。

要求：

- 不直接用 `payload->'bank_rows'` 长度当银行流水事实数。
- 在有搜索、列筛选、时间筛选时，`row_counts` 统计命中的真实行；折叠组如果命中的是摘要行，仍需能追溯到原始流水并返回真实命中数。
- `detail_level=summary` 可以裁剪可见行，但 `row_counts` 不受裁剪影响。
- `total` 继续是分页前、匹配当前筛选条件的 group 总数，用于分页。
- `page` 和 `page_size` 只影响返回的 `groups` 列表，不影响 endpoint 级 `total` 和 `row_counts`。

### 5. 关系标签和银行明细联动

银行明细的 `oa_relation_tag`、`invoice_relation_tag` 继续来自关联台关系投影，但必须使用真实银行流水 row id。

免 OA 摘要行不应写回银行明细关系标签。关系标签应落在 `collapsed_rows.bank` 里的真实流水上。

## 前端设计

### 1. 区域标题

区域标题继续显示“已配对 N 项 / 未配对 N 项”，但 `N` 使用 `zone_counts.*.rows` 或 groups page 的 `row_counts.rows`，即事实三栏合计行数。

不显示 group 数为“项”。如需要给用户解释分页，可在次要位置显示“X 组”，但不作为主要标题。

### 2. 银行流水栏标题

银行流水栏标题显示真实银行流水数：

- 已配对银行流水：当前数据应为 `237`。
- 未配对银行流水：当前数据应为 `194`。
- 合计：`431`。

前端不自己从 rows 展开计算真实数，只消费后端 `row_counts.bank`。

### 3. 免 OA 折叠组展示

免 OA 折叠组保持一条摘要行，组内显示：

- “当前显示 1 条摘要”
- “实际 N 条流水”

当用户打开详情或展开时，通过 group detail 获取完整 `collapsed_rows.bank`。

### 4. 异常和忽略视图

已忽略是 `display_state` 外的辅助视图，不进入 `open|paired` zone 标题。异常 case 是否进入主 zone 取决于投影状态。

- 已忽略银行流水从主 zone 中移除后，不再参与区域标题和 `open.bank + paired.bank`，但必须进入一致性诊断的 `ignored_bank_count`。
- 已处理异常是否计入主 zone 取决于投影状态：processed-exception paired group 计入 `paired`；open exception group 计入 `open`。
- 如果未来需要让银行明细事实数与“关联台所有处理视图”完全对齐，应新增单独诊断口径，不把辅助视图混入 open/paired 标题。

## API 契约

### Summary

`GET /api/workbench/summary?month=all` 返回：

```json
{
  "summary": {
    "bank_count": 431,
    "zone_counts": {
      "paired": {
        "groups": 67,
        "bank": 237,
        "rows": 324
      },
      "open": {
        "groups": 483,
        "bank": 194,
        "rows": 688
      }
    }
  },
  "diagnostics": {
    "bank_detail_count": 431,
    "ignored_bank_count": 0,
    "bank_detail_reconciliation_status": "matched"
  }
}
```

说明：

- 上例 `rows` 为三栏事实行合计，具体值以后端重算结果为准。
- `groups` 不用于区域标题的“项”。
- `bank_count = paired.bank + open.bank`。
- `bank_detail_count = bank_count + ignored_bank_count`。当前数据没有已忽略银行流水，所以 `431 = 431 + 0`。

### Groups Page

`GET /api/workbench/groups?month=all&zone=paired&page=1&page_size=200&detail_level=summary` 返回：

```json
{
  "total": 67,
  "row_counts": {
    "oa": 27,
    "bank": 237,
    "invoice": 60,
    "rows": 324
  },
  "groups": [
    {
      "group_id": "case:...",
      "display_mode": "collapsed_summary",
      "row_counts": {
        "oa": 0,
        "bank": 12,
        "invoice": 0,
        "rows": 12
      },
      "display_row_counts": {
        "oa": 0,
        "bank": 1,
        "invoice": 0,
        "rows": 1
      },
      "bank_rows": [
        {
          "source_kind": "no_oa_bank_batch_summary"
        }
      ],
      "collapsed_rows": {
        "bank": []
      }
    }
  ]
}
```

`detail_level=summary` 下 `collapsed_rows.bank` 可以裁剪或省略重字段，但 `row_counts.bank` 必须保留真实数量。

### Group Detail

`GET /api/workbench/groups/detail` 返回完整组详情：

- `row_counts` 与 summary page 相同。
- `display_row_counts` 与 summary page 相同。
- `collapsed_rows.bank` 包含真实银行流水。

## 数据回填和发布

1. 部署代码后，标记所有 workbench scope dirty。
2. 重建 `YYYY-MM` scope。
3. 重建或聚合 `all` scope。
4. 清理 Redis workbench groups cache version，避免旧 payload 被复用。
5. 运行一致性检查：
   - `app.bank_transactions(status <> deleted)`。
   - `read_model.bank_detail_rows`。
   - `read_model.workbench_groups` 展开事实 bank row 集合。
   - 已忽略 bank row 集合。
   - `bank_detail_count = open_bank_count + paired_bank_count + ignored_bank_count`，且缺失/多余 row id 为 0。

发布期间如果某 scope 尚未重建，API 应返回 `read_model_status=refreshing|stale`，前端显示现有健康提示，不静默展示错误计数为 fresh。

## 验证方案

### 后端单元和集成测试

- 免 OA 多流水折叠组：
  - `bank_rows` 只有摘要行。
  - `collapsed_rows.bank` 有 N 条真实流水。
  - group `row_counts.bank = N`。
  - group `display_row_counts.bank = 1`。
- `GET /api/workbench/summary`：
  - `summary.bank_count` 不计摘要行。
  - `zone_counts.paired.bank + zone_counts.open.bank = summary.bank_count`。
  - `diagnostics.bank_detail_count = summary.bank_count + diagnostics.ignored_bank_count`。
- `GET /api/workbench/groups`：
  - `total` 是 group 数。
  - `total` 和 `row_counts` 都按当前筛选条件、分页之前统计。
  - `row_counts.bank` 是真实流水数。
  - `detail_level=summary` 裁剪不影响 `row_counts`。
- 银行明细与关联台一致性：
  - 非删除银行流水事实数等于关联台主 zone 真实银行流水去重数加已忽略银行流水去重数，即 `bank_detail_count = open_bank_count + paired_bank_count + ignored_bank_count`。
  - 当前 fixture 或构造数据中覆盖免 OA 折叠、普通手工配对、未配对、异常 open group、processed-exception paired group、已忽略 bank row。
  - 已忽略 bank row 不参与 `open|paired` 主等式，但在一致性诊断中以 `ignored_bank_count` 单独报告。

### 前端测试

- 区域标题使用 `row_counts.rows` 或 `zone_counts.*.rows`。
- 银行流水栏使用 `row_counts.bank`。
- 折叠免 OA 批次显示摘要行，同时显示实际流水数。
- 不从当前已加载 preview rows 推断总数。

### 手工验收

当前数据重建后应满足：

- 银行明细页：流水 `431`。
- 关联台真实银行流水合计：`431`。
- 已配对真实银行流水：`237`。
- 未配对真实银行流水：`194`。
- 已忽略真实银行流水：`0`。
- 一致性检查：缺失 `0`，多余 `0`。

## 风险和约束

- `all` scope 是跨月聚合，必须避免同一真实银行流水跨 scope 重复进入 `all`。
- 搜索和列筛选如果继续依赖 summary row，可能出现“摘要命中但原始行未命中”的解释问题。实现时必须定义 row role 或统一 group row 投影。
- 旧前端或兼容接口如果仍读取 `paired_count/open_count` 作为项数，会继续显示 group 数；实现时需要同步检查所有调用点。
- 读模型回填前后短时间内可能出现旧缓存；发布步骤必须包含 Redis cache 清理和 read model status 提示。

## 接受标准

- 银行明细事实数与关联台诊断口径一致：`bank_detail_count = summary.bank_count + ignored_bank_count`；当前生产数据因 `ignored_bank_count = 0`，所以 `431 = 237 + 194`。
- 免 OA 摘要行不参与银行流水事实计数。
- Summary、groups page、group detail 对同一组的事实计数一致。
- 前端不再把 group 数或摘要展示行数当作流水数量。
- 自动化测试覆盖免 OA 折叠、普通配对、未配对、异常视图和 summary/groups API。
- 当前生产数据回填后，`431 = 237 + 194` 成立，并能通过一致性检查脚本或 app-health 诊断复核。
