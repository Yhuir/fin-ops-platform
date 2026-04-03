# Prompt 01: 项目基础骨架

## 目标

为 `fin-ops-platform` 建立银企核销系统的第一版工程骨架，并为 OA 集成和项目成本测算预留扩展边界。

## 你要做的事

- 阅读 `docs/pre.md`、`docs/prd.md`、`docs/domain-model.md`、`docs/solution-design.md`
- 如果仓库为空，先建立合理的前后端与服务目录结构
- 抽出核心领域对象：客商、发票、银行流水、核销单、核销明细、台账、导入批次、审计日志
- 定义核心枚举和状态机
- 建立最小可运行的开发环境说明
- 提供基础示例数据或 seed 数据

## 约束

- 当前重点是 `Reconciliation MVP`
- 不要一开始做复杂权限或复杂消息系统
- 设计上必须为 `OA Integration` 和 `Project Costing` 预留扩展字段和模块边界
- 模块边界必须清晰，避免把导入、匹配、核销、台账揉成一个大模块

## 交付物

- 可运行的项目骨架
- 核心领域模型定义
- 初始数据库迁移或等价建模文件
- 基础 README 或启动说明
- 最小的审计日志能力

## 验收标准

- 仓库结构清晰
- 核心模型可支撑后续 02-08 prompt
- 至少能本地启动基础服务
- 代码中已体现 OA 和项目维度的预留字段或接口

## 可直接使用的 Prompt

```md
你正在为 `fin-ops-platform` 搭建第一版银企核销系统。

先阅读以下文档：
- docs/pre.md
- docs/prd.md
- docs/domain-model.md
- docs/solution-design.md
- docs/roadmap.md

项目当前切入点是银企核销（Reconciliation），但未来蓝图明确包含：
- OA 系统接入
- 项目成本测算（Project Costing）

请直接在仓库中完成第一阶段工程骨架搭建，要求如下：

1. 如果仓库为空，请建立合理的项目结构，并保持模块边界清晰。
2. 抽出这些核心领域对象：
   - Counterparty
   - Invoice
   - BankTransaction
   - ReconciliationCase
   - ReconciliationLine
   - FollowUpLedger
   - ImportedBatch
   - AuditLog
3. 定义关键枚举和状态机，尤其是发票状态、流水状态、台账状态、核销单类型。
4. 提供最小可运行的开发环境和启动说明。
5. 为 OA 和 Project Costing 预留字段或模块，不要后续难以扩展。
6. 不要实现复杂业务细节，但要把后续 02-08 阶段能依赖的底座搭好。

输出要求：
- 直接修改代码
- 补充必要文档
- 说明你创建了哪些模块和文件
- 说明后续最适合先做哪个 prompt
```

