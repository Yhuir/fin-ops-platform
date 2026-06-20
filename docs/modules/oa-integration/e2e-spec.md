# OA Integration Spec-first E2E Spec

OA 集成的 Spec-first 目标是证明真实 OA 登录、权限、Mongo 投影、目标申请人凭据、OA 草稿和 iframe/同域代理不会破坏页面业务流。本地 mock 可以保护合同，但不能替代真实 OA/staging smoke。

## Spec IDs

| Spec ID | 用户可观察合同 | 必须证明 |
| --- | --- | --- |
| `OA-E2E-001` | OA iframe 或同域入口打开后，`/api/session/me` 能返回正确用户、access tier 和权限。 | 真实 OA token/session、app 内权限二次校验、expired/forbidden gate。 |
| `OA-E2E-002` | OA Mongo 同步/投影失败时，页面不能把旧 OA projection 伪装 fresh。 | Mongo read status、worker projection、App Status/read model freshness 一致。 |
| `OA-E2E-003` | OA 待付款页面 rows/filter/detail 在 fresh/non-fresh/权限状态下表现正确。 | OA pending page Browser + API/read model tests。 |
| `OA-E2E-004` | 进项发票 OA 反提使用目标申请人创建草稿，preview hash/version/idempotency/失败恢复正确。 | 目标申请人凭据、OA login token、draft create、submitted history。 |
| `OA-E2E-005` | ETC OA 草稿/人工确认只修改本系统状态，不自动删除真实 OA 草稿/流程。 | ETC Browser/API/service tests；真实 OA 草稿页面需 staging。 |
| `OA-E2E-006` | Settings 中目标 OA 申请人凭据 admin-only，保存/list/delete 不回显 password。 | API/前端/权限矩阵测试。 |
| `OA-E2E-007` | OA role sync、iframe cookie、Nginx 同域路径和下载/跳转在部署环境可用。 | staging/production smoke，不由本地 mock 证明。 |

## 外部风险

真实 OA 登录接口、RSA 公钥、目标申请人账号状态、OA Mongo 字段变体、OA 草稿页面、iframe cookie、Nginx 代理和 OA role sync 都是 `external-risk`。缺真实凭据时只能保持 partial/external-risk。
