# Phase 27 本地参考数据性能证据

> 结论：确定性 Chromium reference run 全绿，用户操作从触发到最终 settled 的整体 p95 为 1.370s、p99 为 1.769s、max 为 2.591s。本文不是生产延迟证明；生产 PostgreSQL、网络、systemd worker、真实数据规模和访问时 freshness 必须由 Plan 27-07 单独验证。

## 口径与边界

- 命令：`bash scripts/verify.sh all`，其中 deterministic Chromium 为 183/183 passed，单 worker，总耗时 9.7 分钟。
- 原始证据：`web/test-results/**/operation-latency-*.json`，排除 Playwright attachment 副本后共 543 条；所有记录均 `pass=true`，覆盖 450 个唯一 `operationId`。
- 17 个 `appPageDefinitions` 全部有页面/操作记录；另外记录 `app-shell-navigation` 作为 shell 生命周期证据。导入页面 artifact key 使用连字符，对应 registry 中的 `imports.bank-transactions`、`imports.invoices`、`imports.etc-invoices`。
- `finalSettledLatencyMs` 从用户动作开始计到该场景定义的最终可观察稳定状态。故障、重试、权限、下载、显式 batch 与普通写均包含在 reference aggregate；不能把该 aggregate 误称为“already-fresh GET”或生产 command SLO。
- 12 条记录只定义了 first-visible/API checkpoint，没有定义独立 final-settled checkpoint；它们全部通过，但不进入 settled 百分位。没有用 0、跳过或宽松断言填补缺失值。

## 总体结果

| Metric | Count | p50 ms | p95 ms | p99 ms | max ms | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| first visible response | 218 | 228.68 | 1460.14 | 1866.48 | 2272.13 | pass |
| observed API | 254 | 201.84 | 1111.44 | 1350.90 | 1672.65 | pass |
| explicit operation barrier | 8 | 142.03 | 400.46 | 400.46 | 400.46 | pass；普通写断言 barrier=0 |
| final settled | 531 | 232.13 | 1370.04 | 1768.53 | 2591.03 | pass；全样本 max < 3s |

## 逐页面结果

下表混合页面访问、写操作、失败恢复和显式 batch。它用于证明每个页面的完整用户流没有超过 3 秒的单个 recorded settled checkpoint；更严格的生产 already-fresh/access-to-fresh SLO 在 27-07 重新按专用 probe 计时。

| Page/artifact key | Records | Settled | p50 ms | p95 ms | p99 ms | max ms | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `app-health-operations` | 5 | 5 | 516.99 | 1293.42 | 1293.42 | 1293.42 | pass |
| `app-shell-navigation` | 5 | 5 | 347.05 | 1327.18 | 1327.18 | 1327.18 | pass |
| `bank-details` | 17 | 17 | 215.48 | 494.84 | 494.84 | 494.84 | pass |
| `bank-flow-rule-batches` | 10 | 10 | 91.39 | 341.50 | 341.50 | 341.50 | pass |
| `batch-accounting` | 15 | 15 | 130.22 | 1479.43 | 1479.43 | 1479.43 | pass |
| `cost-statistics` | 47 | 47 | 198.22 | 867.51 | 1029.49 | 1029.49 | pass |
| `etc-tickets` | 36 | 36 | 420.59 | 2068.85 | 2148.71 | 2148.71 | pass |
| `imports-bank-transactions` | 39 | 39 | 270.49 | 1406.65 | 1468.96 | 1468.96 | pass |
| `imports-etc-invoices` | 25 | 25 | 233.48 | 1455.60 | 1613.34 | 1613.34 | pass |
| `imports-invoices` | 30 | 30 | 264.06 | 1233.69 | 1519.37 | 1519.37 | pass |
| `input-invoice-usage` | 43 | 42 | 233.14 | 1186.43 | 1518.74 | 1518.74 | pass |
| `oa-pending-payments` | 39 | 39 | 149.28 | 1104.20 | 1151.95 | 1151.95 | pass |
| `output-invoice-collections` | 68 | 67 | 231.56 | 1259.97 | 1524.98 | 1524.98 | pass |
| `pending-invoices` | 65 | 58 | 208.49 | 1615.28 | 1634.69 | 1634.69 | pass |
| `reconciliation-workbench` | 36 | 36 | 225.08 | 873.61 | 1801.09 | 1801.09 | pass |
| `settings` | 11 | 10 | 122.82 | 1768.53 | 1768.53 | 1768.53 | pass |
| `tax-offset` | 30 | 28 | 1028.69 | 2334.52 | 2591.03 | 2591.03 | pass |
| `turnover-ledger` | 22 | 22 | 170.29 | 1324.09 | 1404.64 | 1404.64 | pass |

## 按动作类型结果

| Action type | Records | Settled | p50 ms | p95 ms | p99 ms | max ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `check` | 26 | 26 | 100.01 | 237.00 | 243.61 | 243.61 |
| `click` | 353 | 342 | 215.37 | 641.04 | 1111.30 | 2068.85 |
| `download` | 2 | 1 | 62.03 | 62.03 | 62.03 | 62.03 |
| `fill` | 10 | 10 | 79.41 | 880.51 | 880.51 | 880.51 |
| `navigate` | 107 | 107 | 1193.85 | 1622.50 | 2334.52 | 2591.03 |
| `poll` | 1 | 1 | 9.77 | 9.77 | 9.77 | 9.77 |
| `select` | 21 | 21 | 191.79 | 247.92 | 264.06 | 264.06 |
| `uncheck` | 1 | 1 | 106.83 | 106.83 | 106.83 | 106.83 |
| `upload` | 21 | 21 | 135.49 | 234.17 | 306.28 | 306.28 |
| `wait` | 1 | 1 | 1330.90 | 1330.90 | 1330.90 | 1330.90 |

## 36 个 operation probe group 闭环

`pass-local` 表示该 group 的业务/API/read-model/权限/浏览器合同通过；生产列只说明 27-07 的安全策略，不能把“未执行危险生产写”伪装成实测。

| Probe id | Class | Local reference evidence | Local result | Production policy |
| --- | --- | --- | --- | --- |
| `p27-op-background-job` | explicit-batch | background job service/API/App Health tests；dashboard 操作 latency | pass-local | 只读状态与有现存 test-owned job 时的 operator action；不制造失败 job |
| `p27-op-bank-category` | fact-write | bank category assign/confirm/revoke Chromium + API/service | pass-local | 不改真实业务分类；由零 fan-out guard 与可逆 relation fixture 验证共享写合同 |
| `p27-op-bank-flow-batch` | explicit-batch | submit/selection/withdraw/reset Chromium + service/API | pass-local | 不对真实生产批次 apply |
| `p27-op-bank-flow-rule` | rule-write | tag Drawer save Chromium + CAS/service | pass-local | 不改生产规则 |
| `p27-op-bank-rule-reapply` | explicit-batch | auto-tag reapply Chromium + exact month API/service | pass-local | 不执行生产全量 reapply |
| `p27-op-bank-rule-save` | rule-write | auto-tag Drawer open/save/failure Chromium | pass-local | 不改生产规则 |
| `p27-op-barrier` | read-like-command | 8 条显式 barrier timing；普通写场景断言 0 barrier | pass-local | 只读 freshness/status probe |
| `p27-op-batch-accounting` | fact-write | submit/withdraw/current-page convergence Chromium | pass-local | 由 test-owned relation fixture代表共享 relation command |
| `p27-op-cost-rule` | rule-write | 新增 tag Drawer open/save；PUT once、normal GET、barrier=0 | pass-local | 不改生产标签规则 |
| `p27-op-etc-batch` | fact-write | ETC business batch/OA status/create/delete Chromium | pass-local | 不触发真实 OA side effect |
| `p27-op-etc-import` | explicit-batch | ETC import confirm/job/downstream access Chromium | pass-local | 不导入生产文件 |
| `p27-op-etc-preview` | read-like-command | zip preview/stale/corrupt Chromium | pass-local | 只读/临时 preview 可验证，不提交 |
| `p27-op-etc-task` | explicit-batch | reconciliation task/source/upload/manual matching Chromium | pass-local | 不修改真实任务 |
| `p27-op-import-confirm` | explicit-batch | bank/invoice/ETC confirm/job/access convergence Chromium | pass-local | 不导入生产文件 |
| `p27-op-import-preview` | read-like-command | bank/invoice/ETC preview/retry/error Chromium | pass-local | 不提交临时 preview |
| `p27-op-input-oa-batch` | explicit-batch | OA reverse draft/batch selection Chromium + API | pass-local | 不创建真实 OA draft |
| `p27-op-input-oa-preview` | read-like-command | OA reverse preview/read-only Chromium | pass-local | 不创建真实 OA draft |
| `p27-op-input-oa-state` | fact-write | OA reverse status/revoke/draft current Drawer flows | pass-local | 不调用真实 OA |
| `p27-op-input-rule` | rule-write | payment rule Drawer save/current rows Chromium | pass-local | 不改生产规则 |
| `p27-op-manual-oa` | fact-write | manual OA API/component/service、settings page access；零旧 barrier guard | pass-local | 不导入/删除真实 OA；没有伪造生产 mutation latency |
| `p27-op-oa-pending` | fact-write | bank link/paid writeback/failure/current rows Chromium | pass-local | 不写回真实 OA |
| `p27-op-output-fact` | fact-write | status/reminder/red relation/receipt create-void-reissue Chromium | pass-local | 不改真实发票/收据 |
| `p27-op-output-preview` | read-like-command | receipt/export preview Chromium | pass-local | 只读 preview 可验证 |
| `p27-op-output-settings` | rule-write | 新增 admin receipt settings open/save；PUT once、rows delta=0、barrier=0 | pass-local | 不改生产编号规则 |
| `p27-op-pending-fact` | fact-write | attach/status batch success/conflict/failure Chromium | pass-local | 不改真实发票关系 |
| `p27-op-pending-preview` | read-like-command | candidates/attach preview/conflict Chromium | pass-local | 只读 preview 可验证 |
| `p27-op-pending-rule` | rule-write | expense rule Drawer save/failure/retry Chromium | pass-local | 不改生产规则 |
| `p27-op-settings-batch` | explicit-batch | reset impact/password/job polling Chromium | pass-local | 不执行生产 reset |
| `p27-op-settings` | rule-write | project status/scope、credential/account API/component/permission flows | pass-local | 生产仅只读验证，不改配置/凭据 |
| `p27-op-tax-import` | explicit-batch | certified preview/confirm/job modal Chromium | pass-local | 不导入生产文件 |
| `p27-op-tax-plan` | fact-write | calculate/save/version-conflict Chromium | pass-local | 不改生产税务计划 |
| `p27-op-tax-preview` | read-like-command | calculate/certified preview Chromium | pass-local | 只读/临时计算可验证 |
| `p27-op-turnover-fact` | fact-write | closure confirm/withdraw、extra Drawer save、current GET Chromium | pass-local | test-owned reversible turnover fixture，confirm→withdraw 三轮 |
| `p27-op-turnover-rule` | rule-write | tag Drawer save/current GET Chromium | pass-local | 不改生产规则 |
| `p27-op-workbench-fact` | fact-write | relation/exception/ignore/cash confirm/withdraw Chromium | pass-local | test-owned reversible relation contract代表共享 command |
| `p27-op-workbench-preview` | read-like-command | confirm/withdraw/exception preview/conflict Chromium | pass-local | 只读 preview 可验证 |

## Drawer 全量复审

- 22/22 个业务 `*Drawer.tsx` 均登记：10 个 read-only、8 个 writable、4 个 mixed；`AppDrawer.tsx` 仅为 layout primitive。
- 23/23 个 dynamic opener 由权限矩阵真实打开并扫描可见、可用写控件；read-export 场景不允许 durable mutation。
- 本轮发现并补齐三个缺少独立 latency artifact 的关键保存流：

| Operation id | API ms | first visible ms | settled ms | Result |
| --- | ---: | ---: | ---: | --- |
| `cost-statistics.open-tag-rules-drawer` | — | 313.77 | 322.61 | pass |
| `cost-statistics.save-tag-rules` | 172.29 | 421.36 | 421.36 | pass |
| `output-invoice-collections.open-receipt-settings` | 214.14 | 228.68 | 237.38 | pass |
| `output-invoice-collections.save-receipt-settings` | 66.77 | — | 329.50 | pass |
| `turnover-ledger.open-relation-extra` | 214.24 | 230.77 | 243.47 | pass |
| `turnover-ledger.save-relation-extra` | 183.20 | 243.80 | 243.81 | pass |

- 复审纠正覆盖矩阵错误：`CollectionStatusRulesDrawer` 的代码标题明确为“Sheet6 静态规则，只读展示”，没有 `onSave` 或 mutation；现已归类 read-only，禁止为了满足表格而虚构保存操作。

## 只有 partial checkpoint 的 12 条记录

- `pending-invoices.open-attach-picker-before-conflict`: first 200.08ms。
- `pending-invoices.open-export-preview`: first 140.51ms，API 124.90ms。
- `tax-offset.open-input-counterparty-filter`: first 1054.34ms。
- `input-invoice-usage.open-payment-rules-full-access`: first 238.34ms，API 215.61ms。
- `pending-invoices.open-attach-picker-before-failure`: first 180.24ms。
- `pending-invoices.confirm-attach-existing-retry`: first 421.58ms，API 128.58ms。
- `settings.confirm-data-reset`: first 117.51ms，API 93.59ms。
- `pending-invoices.confirm-attach-existing`: first 430.39ms，API 127.21ms。
- `output-invoice-collections.sort-invoice-no`: API 90.11ms。
- `pending-invoices.return-after-fanout-confirm`: first 262.49ms。
- `tax-offset.open-certified-import-dialog-happy-path`: first 215.05ms。
- `pending-invoices.download-export-row-limit`: first 87.15ms，API 70.53ms。

这些记录均 pass；它们没有 final marker，所以没有进入 settled p50/p95/p99。生产验证不会用这些 partial 值替代专用 HTTP/access-to-fresh 指标。

## 本地结论

1. reference data 下所有 recorded operation 均通过，单条 settled max < 3s。
2. 普通写的 browser contract 是 canonical commit + 当前页 normal GET；跨页消费者在自身访问时读取，测试断言普通写不调用旧 operation barrier。
3. full-history/import/reset/reapply 仍是 explicit batch，只承诺接受/提交有界，不能把全历史完成时间伪装成普通 3 秒 SLO。
4. 生产性能仍未知；必须部署后用 17 页 HTTP/browser probe、test-owned 可逆 relation fixture、queue delta 与 System Audit 得出真实结论。
