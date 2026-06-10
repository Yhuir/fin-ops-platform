# 设置 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_oa_applicant_credentials_service.py` | 覆盖 admin-only、必填校验、`已配置/未配置` 状态和非敏感 payload。 |
| 2. Service-layer tests | 适用 | `tests/test_oa_applicant_credentials_service.py`、`tests/test_postgres_oa_applicant_credentials_repository.py` | 覆盖 service/repository 边界、PostgreSQL pgcrypto 加密、列表不解密。 |
| 3. API contract tests | 适用 | `tests/test_oa_applicant_credentials_api.py` | 覆盖保存、列表、删除、非 admin 403、普通 settings payload 不泄露密码。 |
| 4. Read model/cache/background job tests | 不适用 | - | OA 申请人凭据是设置事实，不经过 read model/worker。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | 覆盖 admin-only 凭据 section、保存密码走独立 endpoint、保存成功清空密码输入、普通 settings save 不携带密码，以及既有关联台设置入口回归。 |
| 6. End-to-end business-flow integration tests | 待 Phase 5 | 待补充 | 完整链路需等凭据 UI、目标申请人 token provider 和创建 OA 草稿闭环接入后覆盖。 |
| 7. Existing feature regression tests | 适用 | `tests/test_oa_applicant_credentials_api.py`、`tests/test_postgres_migrations.py` | 保护普通 `/api/workbench/settings` 不被凭据污染，迁移发现顺序不破坏。 |

## 现有验证命令

```bash
# 后端示例，按实际模块替换
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_oa_applicant_credentials_repository -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v

# 前端示例，按实际模块替换
cd web && npm test -- --run src/test/SettingsPage.test.tsx
cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx
cd web && npm run build
```

## 未测风险

- 设置页凭据 UI 已由组件/交互测试覆盖；尚未通过真实浏览器连接生产后端验证管理员保存凭据。
- 目标 OA 申请人登录/token provider 已有后端 mock 测试；完整反提 OA 创建草稿链路仍待 Phase 4/Phase 5 前端 drawer 和集成测试覆盖。
