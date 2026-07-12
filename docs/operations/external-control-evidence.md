# 外部完整性证据运维合同

本文定义银行、OA、普通发票和 ETC 四类外部来源证据的唯一登记、撤销和 System Audit 使用边界。目标是证明“指定外部完整快照截至某一时点，与当前 App canonical facts 精确一致”，不是把 App 内部绿色扩张为外部系统实时正确。

## 结论边界

- 内部 `overall_status=pass`：只证明同一 App PostgreSQL immutable snapshot 内 17 页已登记合同一致。
- 外部 `status=pass`：四个 domain 的最新、未过期 `complete_snapshot/all` manifest 与当前 canonical facts 在 item set、关键字段 fingerprint 和 controls 上全部双向相等。
- `end_to_end_source_truth=proven_as_of_external_evidence`：只在外部四域 pass 时返回，并严格绑定每个 manifest 的 `observed_at`、`source_snapshot_id` 与当前 `system_audit_id/snapshot_identity`。
- 未登记是 `unknown/unproven`；latest revoked、expired、非法覆盖或任何 missing/extra/duplicate/field/control mismatch 是 `fail/unproven`。撤销最新证据后不得回退旧证据变绿。
- Audit 之后的 App 写入、外部来源变化、collector 身份真实性和外部系统自身控制环境不在该声明内。需要新时点结论时，必须重新采集、登记并复跑 System Audit。

## 模块边界与 I/O

| 边界 | 输入 | 输出/副作用 |
| --- | --- | --- |
| 独立 collector | 外部来源系统或其受控导出 | 原始 artifact 与 manifest；不能读取 App canonical rows 来生成“外部 expected set” |
| `ExternalControlEvidenceService` | manifest mapping | 纯 normalize、identity/fingerprint/control 校验；不读 HTTP、不连外部网络 |
| `PostgresExternalControlEvidenceRepository` | 已校验 manifest、actor、reason | 原子 append header/items 或显式 revoke，写 `audit.events`；不改业务事实/read model |
| `external_control_evidence` CLI | manifest/artifact 或 evidence id | validate/dry-run/inspect/register/revoke 的结构化 JSON；无 HTTP/UI 写入口；API/worker/readonly DB role 只有 select，apply 必须使用受控 migrator/operator 连接 |
| `audit_external_control_evidence` | caller-owned read-only PostgreSQL snapshot | 四域 exact comparison、bounded issue samples、page coverage、as-of claim；不登记、不 refresh、不 repair |

持久化表是 `audit.external_control_evidence` 与 `audit.external_control_evidence_items`。header/items 采用 immutable append；撤销只更新 header 的审计状态，禁止 delete。item 原文和敏感字段不得写入日志或 CLI 输出。

## Manifest v1

固定合同：

- `contract_version=external-control-evidence.v1`
- `coverage_mode=complete_snapshot`
- `scope_key=all`
- `domain` 只能是 `bank`、`oa`、`invoice`、`etc`
- 必填来源信息：`tenant_id`、`source_system`、`source_snapshot_id`、带时区的 `observed_at/valid_until`
- 必填 artifact：原始受控导出文件的 `sha256/size_bytes`
- 必填 collector：`name/version`
- 必填 controls：`item_count`、`counts_by_kind`、`amount_totals_by_kind`、`tax_totals_by_kind`
- `items[]` 每项包含 `kind` 和合同规定的完整 `fields`。service 独立重算 item key、content fingerprint、controls 和 manifest fingerprint；调用方提交不一致的派生值会被拒绝。

Domain/item ownership：

| Domain | Item kinds | Identity contract |
| --- | --- | --- |
| bank | `bank_transaction` | account、direction、trade time、serial、amount、counterparty |
| oa | `oa_application`、`oa_item`、`oa_attachment` | OA source/form；明细 row/type/no/amount；附件 source key |
| invoice | `invoice`、`tax_certified_invoice` | 发票类型/号码/代码/数电号/日期/双方税号；认证唯一 key |
| etc | `etc_invoice`、`etc_archive` | ETC source id；归档 sha256/size/original filename |

普通 `invoice` comparer 排除已由 OA attachment 或 ETC domain 承担来源责任的 canonical source class，防止同一外部对象被两个 domain 重复证明。完整字段及 normalize 规则的机器事实源是 `services/external_control_evidence.py`；修改该合同必须升级版本、迁移、测试和本文，不能静默改变 v1。

## 安全执行流程

以下命令默认在 active release 源码与受控 shell 中执行。生产 `register/revoke --apply` 属于写生产 audit facts，必须先获得明确授权；没有授权时只允许离线 validate、dry-run 或只读 inspect/System Audit。

1. 独立 collector 生成 source artifact 与 manifest。保留来源 snapshot id、采集时间、collector 版本和原始 artifact，不要从 App 数据库导出反向生成。
2. 离线校验，不连接数据库：

```bash
PYTHONPATH=backend/src python -m fin_ops_platform.tools.external_control_evidence \
  validate --manifest /secure/path/bank-manifest.json --artifact /secure/path/bank-source.bin
```

3. 登记前 dry-run；该步骤仍不连接数据库：

```bash
PYTHONPATH=backend/src python -m fin_ops_platform.tools.external_control_evidence \
  register --manifest /secure/path/bank-manifest.json --artifact /secure/path/bank-source.bin \
  --dry-run --actor operator-id --reason ticket-id
```

4. 获得生产写授权后才允许登记。使用 `scripts/with-production-admin-token.sh` 只适用于 HTTP admin token；本 CLI 依赖受控 `FIN_OPS_POSTGRES_DATABASE_URL`/`DATABASE_URL` 和 migrator/operator 数据库权限，API/worker/readonly role 被数据库 grant 禁止写 evidence。不应打印连接串或凭据：

```bash
PYTHONPATH=backend/src python -m fin_ops_platform.tools.external_control_evidence \
  register --manifest /secure/path/bank-manifest.json --artifact /secure/path/bank-source.bin \
  --apply --actor operator-id --reason ticket-id
```

5. 只读检查 header；输出不包含 item payload：

```bash
PYTHONPATH=backend/src python -m fin_ops_platform.tools.external_control_evidence \
  inspect --tenant-id default --domain bank
```

6. 四域全部登记后运行只读 App Health System Audit。只有内部 17 页 pass、外部四域 pass、freshness fresh、queue drained，才能形成对应 snapshot 的 bounded claim。

## 撤销与恢复

错误 evidence 不删除、不覆盖。先 dry-run，再经生产写授权显式撤销：

```bash
PYTHONPATH=backend/src python -m fin_ops_platform.tools.external_control_evidence \
  revoke --evidence-id UUID --dry-run --actor operator-id --reason ticket-id

PYTHONPATH=backend/src python -m fin_ops_platform.tools.external_control_evidence \
  revoke --evidence-id UUID --apply --actor operator-id --reason ticket-id
```

撤销后 System Audit 必须 fail closed。恢复方式是从可信来源重新采集并登记一个新版本，然后复跑 System Audit；禁止修改旧 item、删除审计记录或回退到更旧的绿色证据。

## 失败分流

- `input_error`：修正 manifest/artifact/actor/reason，不触碰数据库。
- `configuration_missing`：只配置受控数据库连接；不得把生产连接串贴入聊天、日志或仓库。
- `unknown`：缺少一个或多个 domain 的最新证据；先补独立 manifest，不能 refresh App read model 来伪造外部证明。
- `fail`：按 domain 的 missing/extra/field/control/revoked/expired code 定位。先判断来源 artifact 错误、collector 合同错误还是 App sync/canonical 错误，再制定单独、可回滚的受控修复；System Audit 本身绝不写数据。
- 任何修复后必须重新登记新 evidence（如外部 snapshot 已变化）并复跑同一只读 System Audit，不沿用旧 `system_audit_id`。

## 生产验收清单

- 四份 artifact/manifest 来自独立、受控来源并能追溯 source snapshot。
- validate 与 register dry-run 成功；actor/reason/ticket 完整。
- 明确批准生产 audit-fact write 后才执行 register/revoke apply。
- `inspect` 显示预期最新版本、未撤销、未过期。
- System Audit 内部 17 页全部 pass；每页 `integrity=pass/freshness=fresh/queue=drained`。
- external 四域全部 pass，page coverage 无缺口，claim 为 `proven_as_of_external_evidence`。
- 保存结构化报告的 system snapshot/evidence IDs/fingerprints/as-of，不保存敏感 item payload。
- Audit 后有任何业务写入或外部 snapshot 更新时，旧报告只保留历史证据身份，不继续作为当前绿色。
