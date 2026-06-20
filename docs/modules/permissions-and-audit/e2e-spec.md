# 权限与审计 Spec-first E2E Spec

本文件定义权限与审计横切边界在真实浏览器和 API contract 中的验收合同。测试必须保护 session gate、角色矩阵、导出/写入/admin gate、零 mutation、审计边界和敏感数据不泄露，而不是保护某个页面当前实现细节。

## 模块目标

权限事实源在后端 OA session + `AccessControlService`。前端权限 hook 只负责用户体验，不能替代后端 guard。所有 protected API 必须先解析 session；写 API 必须检查 `can_mutate_data`；高风险 admin API 必须检查 `can_admin_access`；重要 command 必须记录 actor/tenant/audit 并和业务事实、dirty scope/outbox 保持同一原子边界或等价安全边界。

## 角色合同

- `denied`：不能进入受保护应用；protected API 返回 403/401 语义，不触发页面业务 API。
- `read_export_only`：可读取和导出；不得触发写入、导入确认、数据重置、OA 凭据、运维 dashboard 或 admin mutation。
- `full_access`：可执行普通业务写入；不得访问账户管理、数据重置、OA 凭据或 AppHealth 运维 dashboard。
- `admin`：可进入 admin-only settings 高风险区和 AppHealth 运维 dashboard。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `PERM-E2E-001` | session bootstrap 和 protected shell gate | P0 | `admin`/`full_access`/`read_export_only` 可进入对应页面；forbidden/expired session 在 shell gate 停止，不能渲染受保护页面或调用 protected page APIs。 |
| `PERM-E2E-002` | read-export 全页面可读零 mutation | P0 | `read_export_only` 能打开所有非 admin 页面，页面 ready，期间 `POST/PUT/PATCH/DELETE` 调用为 0，且不调用 admin-only dashboard API。 |
| `PERM-E2E-003` | read-export 高风险写入口禁用/隐藏 | P0 | settings、tax、imports、no-OA、bank details、output/input invoice、workbench 等高风险入口对 `read_export_only` 隐藏/禁用，直接或间接 durable mutation 为 0。 |
| `PERM-E2E-004` | full-access 业务写入口与 admin gate | P0 | `full_access` 可见普通业务写入口和 import file input，但不能进入访问账户、数据重置、OA 凭据或 AppHealth dashboard。 |
| `PERM-E2E-005` | admin 高风险入口 | P0 | `admin` 可进入 settings 访问账户、OA 申请人凭据、数据重置和 AppHealth dashboard；admin-only API 被调用且页面可见。 |
| `PERM-E2E-006` | API guard 和 body actor spoofing | P0 | read/write/admin API 区分 401/403；mutation endpoint 不信任 body actor；只读 session 直接调用 mutation API 时后端拒绝且不调用下游写服务。 |
| `PERM-E2E-007` | 审计和事务一致性 | P0 | 高风险写入、设置变化、标签规则、relation command、批量提交/撤回、data reset、导出等记录 actor/tenant/action/metadata；失败 rollback 不留下半写 audit。 |
| `PERM-E2E-008` | 敏感数据不泄露 | P0 | token、密码、DSN、凭据密文、附件正文不出现在 response、settings payload、audit metadata、日志或前端 state。 |
| `PERM-E2E-009` | Browser hidden-error safety | P0 | role matrix Browser 流不得出现隐藏 `pageerror`、`console.error`、非 abort request failure 或未预期 dialog；认证 gate 的预期 401 只能在专门 session gate 流中显式豁免。 |
| `PERM-E2E-010` | 真实 OA/代理/staging 权限 smoke | P1 | 真实 OA 菜单、OA 角色同步、生产 token 过期、真实导出下载 header、审计查询/导出和代理层权限行为必须在 staging/production smoke 验证。 |

## 不属于本地 deterministic E2E 的风险

- 真实 OA 菜单、OA role sync、OA session 接口超时/失败和生产 token 过期语义。
- 真实浏览器下载、代理层 `Content-Disposition` / `Access-Control-Expose-Headers` 和跨域 header 暴露。
- 生产审计查询/导出、日志脱敏和外部安全审计。
- 每个页面未来新增按钮/抽屉/批量动作后，必须把新写入口补到本矩阵或对应页面 E2E；现有矩阵不是新增入口的自动证明。
