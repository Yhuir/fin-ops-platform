# 进项发票使用情况 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

本节记录当前 read model/all scope 相关测试入口。`以发票反提 OA` 闭环实施时，还必须覆盖下一节的新增测试要求。

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 不适用 | - | 本次未改变支付状态、金额、生命周期或权限业务规则。 |
| 2. Service-layer tests | 适用 | `tests/test_invoice_usage_collection_sql_runtime.py` | 覆盖 `PostgresReadModelRepository.list_input_invoice_usage_rows` 的 all scope source_versions 聚合。 |
| 3. API contract tests | 适用 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_input_invoice_usage_api.py` | 覆盖 `/api/input-invoice-usage/rows` 在 all scope 基础版本 fresh 时返回 `200/fresh/rows`，source version 缺失时仍返回 `202/refreshing`。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_read_model_freshness.py` | 覆盖 read model scope freshness、source version mismatch 和 all scope worker 展开。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/InputInvoiceUsagePage.test.tsx` | 覆盖页面 fresh rows、refreshing 空 rows、空态和表格渲染契约。 |
| 6. End-to-end business-flow integration tests | 不适用 | - | 本次只修复已构建 read model 的 all scope 读取判定，没有改 import、OA、workbench 写入或 worker 生成链路。 |
| 7. Existing feature regression tests | 适用 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx` | 保护 output/oa 同仓储行为、输入发票页面既有 API shape 和前端加载/空态行为。 |

## 以发票反提 OA 闭环测试要求

实施 `创建 OA 草稿` 闭环时，七类测试按以下口径覆盖：

### 已落地覆盖

- Phase 1 后端凭据管理：
  - `tests/test_oa_applicant_credentials_service.py`：覆盖 admin-only、必填校验、`已配置/未配置` 状态、内部登录凭据解析不经 API 暴露。
  - `tests/test_oa_applicant_credentials_api.py`：覆盖 `/api/workbench/settings/oa-applicant-credentials` 保存、列表、删除、非 admin 403，以及普通 settings payload 不泄露密码。
  - `tests/test_postgres_oa_applicant_credentials_repository.py`：覆盖保存使用 `pgp_sym_encrypt`、列表不解密/不选密码材料、内部解析使用 `pgp_sym_decrypt`。
  - `tests/test_postgres_migrations.py`：覆盖 `0066_oa_applicant_credentials.sql`、`encrypted_password bytea`、状态约束和 runtime grant。
- Phase 2 目标申请人 token provider 与一步创建草稿：
  - `tests/test_target_oa_applicant_token_provider.py`：覆盖 OA 登录 client 发送 RSA 加密密码、错误不暴露密码、provider 使用目标申请人凭据构造 draft client、凭据缺失不触发登录。
  - `tests/test_input_invoice_usage_oa_reverse_service.py`：覆盖一步创建内部 batch 和 OA draft、凭据缺失不创建 batch、preview hash stale、`已提交 OA` 落 `submitted_confirmed`、`未提交 OA` 清理本地 draft 字段并可重新创建、已提交历史不暴露内部 id。
  - `tests/test_input_invoice_usage_api.py`：覆盖一步创建 API、凭据缺失、旧 batch draft 路径改用目标申请人 provider、管理员保存凭据后 full-access 用户用目标申请人登录创建草稿、手动已提交、`未提交 OA` 后重新创建和已提交历史接口 shape。
  - `tests/test_postgres_input_invoice_usage_oa_reverse_repository.py`：覆盖 PG batch repository 按 status 查询已提交历史所需记录。
- Phase 3 设置页凭据管理 UI：
  - `web/src/test/SettingsPage.test.tsx`：覆盖管理员可见 `OA申请人凭据`、非 admin 隐藏、保存密码走独立凭据 endpoint、保存成功清空密码输入、普通 settings 保存体不包含密码。
  - `web/src/test/WorkbenchSelection.test.tsx`：覆盖既有关联台设置入口和权限回归。
- Phase 4 进项发票使用页反提 OA UI 闭环：
  - `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`：覆盖一键草稿 API mapper、抽屉不展示 `创建本地批次`/大块不可提交原因、有效候选直接 `创建 OA 草稿`、确认弹窗、`已提交 OA` 进入历史、`未提交 OA` 回到可重新创建、已提交历史不展示内部 id/英文状态。
  - `web/src/test/InputInvoiceUsagePage.test.tsx`：覆盖页面入口接线到 `/api/input-invoice-usage/oa-reverse/oa-draft`，以及 `待处理 | 已提交` tab 和已提交历史渲染。

| 类别 | 是否适用 | 必须覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | 权限级别到 `can_mutate_data`/创建权限的判断；目标申请人凭据 `已配置`/`未配置`；active OA 关系发票不可重复反提；`ready_to_create`、`creating_draft`、`oa_draft_created`、`submitted_confirmed` 状态流转；`未提交 OA` 回到可重新创建状态。 |
| 2. Service-layer tests | 适用 | 凭据 service/repository 不返回密码或 token；密码保存后状态变为已配置；target applicant token provider 使用目标申请人身份；创建 OA 暂存草稿的幂等、preview hash 过期、OA 登录失败、OA 创建失败；确认已提交和未提交本地回滚。 |
| 3. API contract tests | 适用 | 凭据管理接口 admin-only；凭据列表只返回非敏感字段；创建草稿接口的成功响应、未配置凭据、权限不足、候选过期、active OA 关系冲突、OA 外部失败；确认已提交、未提交回滚和已提交历史接口 shape。 |
| 4. Read model/cache/background job tests | 视实现影响适用 | 如果创建草稿或确认已提交会影响 input invoice usage rows、OA 关系或 read model freshness，必须覆盖 dirty scope、refreshing/fresh 和旧数据不可伪装 fresh；如果已提交历史独立于 read model，则说明不适用。 |
| 5. Frontend component and interaction tests | 适用 | `待处理 | 已提交` 切换；不展示 `创建本地批次`；只展示 `创建 OA 草稿`；按钮按权限、选择项、凭据状态正确可用/不可用；草稿创建成功弹窗；`已提交 OA` 进入历史；`未提交 OA` 回到可重新创建状态；不展示大块 `不可提交原因` block。 |
| 6. End-to-end business-flow integration tests | 适用 | 管理员配置申请人凭据 -> 全权限操作人选择发票 -> mock OA 创建草稿 -> 用户确认已提交 -> 历史出现；另一路径覆盖用户选择未提交后重新创建。 |
| 7. Existing feature regression tests | 适用 | 输入发票使用情况列表、筛选、导出、read model freshness、设置页现有权限账户维护、session 权限、已有 OA 反查/支付规则设置不被新凭据模块破坏。 |

实现完成前不得只覆盖成功路径；权限不足、未配置凭据、外部 OA 失败、preview stale、重复发票、未提交回滚和历史展示都必须有测试保护。

## 现有验证命令

```bash
# 后端 read model / API 回归
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_oa_applicant_credentials_repository -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
PYTHONPATH=backend/src python3 -m unittest tests.test_target_oa_applicant_token_provider -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_oa_reverse_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_input_invoice_usage_oa_reverse_repository -v

# 前端页面回归
cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx
cd web && npm test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx
cd web && npm test -- --run src/test/SettingsPage.test.tsx
cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx

# 全量前端构建，发布前或触及前端代码时运行
cd web && npm run build
```

## 未测风险

- 本地单元测试覆盖 all scope 判定与页面契约；生产环境仍需在部署后通过只读查询确认 `/api/input-invoice-usage/rows` 默认查询返回 `read_model_status=fresh` 且 `pagination.total` 大于 0。
- 以发票反提 OA Phase 4 已覆盖前端设置页凭据管理、进项发票 drawer 的 `待处理 | 已提交`、确认弹窗、未提交回滚和页面入口接线；真实 OA 登录、真实 OA 草稿页面打开和生产后端联调仍需发布前验证。
- `OpenSslRsaPasswordEncryptor` 的生产 OpenSSL 调用未在本地测试中用真实 OA 公钥做端到端加密联调；发布前需确认服务器存在 `openssl` 且 `FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY` 与 OA 登录接口匹配。
