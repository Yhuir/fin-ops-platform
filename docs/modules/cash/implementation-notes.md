# 实施记录入口

2026-09-07：用户授权后端实施、提交/推送现金分支、部署及生产验证；后续明确指定后端交付完成后先使用Figma Make生成新版UI，交用户确认后才开发App前端。当前新版原型尚未生成/确认，禁止提前写App现金前端代码。不使用GSD。

本模块采用同 PostgreSQL cash schema、独立受限运行身份、route/service/repository、OA 项目只读。原普通财务池、cash-special 和既有安全措施不被删除或复用为现金事实。

详细实测、提交、部署和剩余风险统一维护在[实施计划 §10](../../dev/cash-module-implementation-plan.md)，本文件不复制第二套验收结果。
