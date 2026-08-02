---
quick_id: 260803-3pf
status: complete
date: 2026-08-03
---

# Quick Task 260803-3pf Summary

## 结果

- 发布 helper 按候选与唯一 active release 的实际包内容自动判定 `frontend`、`runtime` 或 `acl`，没有人工 profile/skip。
- 普通发布只读取 `YNSYLP005`；只有 ACL runtime 边界变化才要求 candidate-bound 005/006 双身份 preflight，且只接受 steady-state `eligible=true`。
- 纯前端门禁缩短为 pre/T+0：exact dist、active release、worker inventory、ready、005 session、公开 shell 与 hashed asset；不运行 RabbitMQ apply、runtime closure、全页面审计或 T+60/T+300。
- runtime/ACL 继续执行 production-equivalent pre/T+0/T+60/T+300；ACL 激活后失败保持 maintenance 并 forward repair。
- 一次性 retired env/OA role-binding cleanup、rollback 和 SQL 已从稳态链删除；strict env/topology 漂移只读失败关闭。

## 边界

- 复用唯一发布入口 `scripts/deploy-oa.sh` 和 root-owned deploy-control，没有新增 deploy controller、依赖、数据库、worker、队列或配置开关。
- 自动分类只以实际 release payload 为事实源；手工 OA SQL 模板不在激活运行时，因此模板注释变化只归 `runtime`，不会误触发 006。
- 关联台高度修复本身未改动；本任务仅确保其最终 SHA 能通过简化后的正式门禁部署。

## 本地验证

- 部署/运行时/权限跨模块回归：318 tests passed。
- 门禁专用契约：39 tests passed。
- 关联台组件回归：42 tests passed。
- Chromium 关联台几何与业务流：2 tests passed。
- `npm run build`、`bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`bash -n deploy/oa/bin/finops-deploy-control.sh`、`git diff --check` 通过。

生产 active SHA、release evidence、005 会话、真实页面几何与性能由本次提交后的标准 deploy-control 和最终交付报告承载，不把环境瞬时状态写入长期代码事实。
