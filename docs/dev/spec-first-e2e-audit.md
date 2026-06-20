# Spec-first E2E Audit

本文定义 Browser e2e / Playwright 的 Spec-first 审计规则。目标是让测试保护页面功能、业务流程和跨页面一致性，而不是保护当前代码实现的偶然行为。

## 核心原则

Spec-first 的事实源顺序：

1. 产品和业务口径：`docs/product-specs/`。
2. 页面、运行链和跨页面影响：`docs/app-architecture/`。
3. 模块维护事实：`docs/modules/<module>/README.md`、`state-machine.md`、`tests.md`、`implementation-notes.md`。
4. API 和验证入口：`docs/dev/api-contracts.md`、`docs/dev/testing.md`。
5. 代码：只用于确认 route、selector、API shape、mock 数据和运行细节；不能反向决定验收标准。

如果现有代码和 Spec 冲突，优先把冲突标记为 `product-bug` 或 `spec-unclear`。不要放松 Playwright 断言来适配错误行为。

## 审计产物

每个页面模块和高风险资源模块逐步补齐：

- `docs/modules/<module>/e2e-spec.md`：页面/功能应该如何工作。
- `docs/modules/<module>/e2e-coverage.md`：现有 Playwright/Vitest/API/integration 是否证明这些 Spec。
- `docs/dev/spec-first-e2e-inventory.md`：全局页面、功能和跨页面链路 inventory。

模块 `e2e-spec.md` 必须包含：

- 模块目标和用户角色。
- 页面入口、主要用户流程和核心业务动作。
- 数据状态：loading、empty、error、refreshing、stale、fresh。
- 权限规则：`admin`、`full_access`、`read_export_only`、forbidden/expired session。
- API/read model/worker/freshness 边界。
- 跨页面 fan-out。
- 失败场景和不可自动化风险。

模块 `e2e-coverage.md` 必须包含：

- Spec ID 到现有测试文件的映射。
- 覆盖状态。
- 缺口分类。
- 下一轮补测建议。

`e2e-coverage.md` 和 `docs/dev/spec-first-e2e-inventory.md` 中登记的 `web/e2e/...` Browser 证据必须指向当前文件，或使用至少能匹配一个当前文件的 glob。`tests/test_spec_first_e2e_docs.py` 会校验这些路径，防止 Playwright 文件删除/改名后 coverage 仍引用失效证据。

## Spec ID 约定

格式：

```text
<MODULE>-E2E-<NNN>
```

示例：

```text
RECON-WB-E2E-001
WB-REL-E2E-001
BANK-DETAILS-E2E-001
IMPORT-BANK-E2E-001
```

一个 Spec ID 代表一个用户可观察业务流程，不代表一个函数、组件或 API 方法。

## 覆盖状态

| 状态 | 含义 |
| --- | --- |
| `covered` | 已有自动化测试从用户可见行为或稳定业务契约证明该 Spec。 |
| `partial` | 已覆盖主路径，但缺少关键角色、失败、stale/refreshing、跨页面或真实浏览器断言。 |
| `missing` | 没有足够自动化覆盖。 |
| `code-driven` | 测试按现有代码行为写成，尚未证明业务 Spec。 |
| `wrong-behavior-protected` | 测试正在保护与 Spec 冲突的错误行为，必须重写或修代码。 |
| `product-bug` | Spec 明确、测试合理，但当前代码不满足。 |
| `spec-unclear` | 业务口径不清，不能写成稳定断言。 |
| `external-risk` | 需要真实 OA、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、对象存储、Nginx/iframe、真实下载或生产数据，不能作为 deterministic 本地 CI 通过项。 |

## 每轮 GSD 流程

每轮只处理一个模块或共享边界：

1. 读取模块事实源和相关产品/app 架构文档。
2. 建立或更新 `e2e-spec.md`。
3. 建立或更新 `e2e-coverage.md`。
4. 审计现有 `web/e2e/*.spec.ts`，映射到 Spec ID。
5. 分类缺口：`covered`、`partial`、`missing`、`product-bug`、`spec-unclear`、`external-risk`。
6. 只在 Spec 稳定且可本地自动化时新增或重写 Playwright。
7. 如果测试暴露产品 bug，修代码并补对应七类测试。
8. 运行目标验证和必要 smoke。
9. 更新 `docs/dev/testing-closure-state.md`、模块 `tests.md` 和 inventory。

## 何时保留、加强、重写或删除现有 E2E

| 决策 | 条件 |
| --- | --- |
| 保留 | 已映射到 Spec ID，断言用户可见结果和业务契约，mock 数据符合业务。 |
| 加强 | 主路径有效，但缺权限、失败、freshness、跨页、下载、弹窗或大表格断言。 |
| 重写 | 测试只证明页面未崩、只适配现有 bug、断言实现细节、mock 与业务不符。 |
| 删除/合并 | 重复覆盖同一 Spec 且增加维护成本；删除前必须确认其他测试仍覆盖该 Spec。 |

## Playwright 编写规则

- 优先用 role、label、test id 和用户可见文本定位。
- 断言最终用户结果：状态标签、表格行、弹窗、下载事件、导航、错误反馈和刷新次数。
- 不断言 React state、内部函数、临时 CSS class 或非业务字段。
- 写操作后必须验证 freshness/barrier/refetch 结果；不能只断言 POST 被调用。
- 权限场景必须证明 UI gate 和 mutation API 未触发。
- API mock 必须表达业务事实，不得为了当前代码方便而缩短业务链路。

## 七类测试结合规则

Playwright 只证明真实浏览器流程。每个 Spec 仍按仓库七类测试判断：

1. Business core unit tests。
2. Service-layer tests。
3. API contract tests。
4. Read model/cache/background job tests。
5. Frontend component and interaction tests。
6. End-to-end business-flow integration tests。
7. Existing feature regression tests。

如果 Playwright 发现问题，先判断问题属于哪一层；不要把所有逻辑都塞进 e2e。

## CI 分层

| 层级 | 内容 |
| --- | --- |
| PR / local target | 目标模块 Playwright、Vitest、API/integration 最小闭环。 |
| `npm run e2e:smoke` | deterministic Chromium smoke，覆盖高 fan-out 业务链路和权限矩阵。 |
| `bash scripts/verify.sh all` | backend unittest、frontend Vitest/build、e2e smoke、docs。 |
| staging/manual smoke | 真实 OA、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、对象存储、Nginx/iframe、真实下载、大数据和生产 runbook。 |

不能把 `external-risk` 写成本地 CI 已覆盖。
