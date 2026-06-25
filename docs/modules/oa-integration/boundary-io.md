# OA 集成模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：OA 集成负责 OA 身份、Mongo adapter、projection sync、附件识别、OA 凭证和 OA 相关页面/API 的外部系统边界。
- 当前缺口：OA 相关能力横跨 OA 待付款、ETC、进项反提、设置和权限，变更必须声明受影响模块。
- 旧代码删除条件：旧 Mongo 直读/手写 projection path 不再被业务页面直接调用。

## 职责边界

### 负责

- OA 身份/权限适配、OA Mongo 读取、OA projection sync、OA 附件发票识别和 OA applicant credentials。
- 对 OA 待付款、ETC、进项反提等模块提供外部系统 adapter。

### 不负责

- 不拥有业务页面状态机。
- 不直接确认业务关联或付款。
- 不把外部 OA 数据直接当作页面 fresh read model。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| OA session/token | `auth.py`、session API | 权限和身份必须可校验 |
| OA Mongo/query | `mongo_oa_adapter.py` | 外部数据进入 adapter/projection |
| OA attachment/import | OA attachment services | 识别结果必须审计和可追踪 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| OA projection rows | repositories/read models | 带 source version |
| OA session/permission payload | frontend session | 不泄露 secret |
| Attachment invoice result | invoice/ETC/input usage modules | 经 service 边界传递 |

## 持久化与投影

- Own read model：无单一页面 read model；影响 `oa_pending_payment`、`input_invoice_usage`、`invoice_lifecycle` 等。
- External system：OA Mongo / OA app。
- Repository：`postgres_repositories/oa_projection.py`、`oa_applicant_credentials.py`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Auth/session | `backend/src/fin_ops_platform/app/auth.py`、`web/src/features/session/api.ts` |
| Adapter/projection | `mongo_oa_adapter.py`、`oa_projection_sync.py`、`postgres_repositories/oa_projection.py` |
| OA services | `oa_identity_service.py`、`oa_manual_import_service.py`、`oa_attachment_invoice_service.py`、`oa_applicant_credentials.py`、`target_oa_applicant_token_provider.py` |
| Related routes | `routes_oa_pending_payments.py`、`routes_etc.py`、`routes_input_invoice_usage_oa_reverse.py`、`server.py` |
| Related modules | OA pending payments、ETC、input invoice usage、settings、permissions |
| Tests | `tests/test_oa_*.py`、`tests/test_mongo_oa_adapter.py`、`tests/test_session_api.py` |

## 依赖方向

- 允许依赖：external adapter, credential repository, access control service。
- 必须通过：OA adapter/service boundary。
- 禁止绕过：业务页面直接查 OA Mongo；service 直接读取 HTTP cookie/header。

## 测试与验证

- `tests/test_mongo_oa_adapter.py`
- `tests/test_oa_projection_sync_service.py`
- `tests/test_oa_pending_payment_api.py`
- `tests/test_target_oa_applicant_token_provider.py`

## 当前缺口和删除条件

- OA token/credential 变更必须同步 permissions/security docs。
- 删除旧 OA projection path 前必须验证 source version 和 downstream freshness。
