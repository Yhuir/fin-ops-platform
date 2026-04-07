# Prompt 31：完成 OA 集成部署收口与联调验收

目标：把 OA 集成从“代码已具备”推进到“可部署、可联调、可验收”的状态，补齐部署说明、路径约定、联调验证和回归测试。

前提：

- `28-oa-shell-auth-foundation.md` 已完成
- `29-oa-menu-iframe-integration.md` 已完成
- `30-oa-visibility-and-access-control.md` 已完成

要求：

- 明确部署路径约定：
  - `/fin-ops/`
  - `/fin-ops-api/`
- 补齐同域部署说明
- 补齐 OA token 透传或复用说明
- 补齐联调检查项：
  - 登录复用
  - 菜单可见性
  - 403 拦截
  - workbench / tax / cost / export / search 正常可用
- 补齐运维回滚与发布顺序说明

建议文件：

- `README.md`
- `docs/README.md`
- `OA 集成当前 app 技术方案.md`
- 相关 deploy / env 文档
- `tests/`
- `web/src/test/`

交付要求：

- 文档可支持真实部署
- 联调清单完整
- 关键授权链路有测试覆盖

验证：

- 后端全量测试
- 前端全量测试
- 前端 build
- 手工验收清单完整

