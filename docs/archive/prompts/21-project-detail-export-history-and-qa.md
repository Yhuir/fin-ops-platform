# Prompt 21: 项目明细强导出历史、任务化与验收

## 目标

把项目明细强导出收口成可追溯、可回看、可验收的正式能力，补齐导出历史、任务状态和前后端 QA。

## 你要做的事

- 为强导出增加导出历史模型
- 增加导出任务状态查询
- 支持再次下载最近导出的文件
- 补导出 QA、异常回归、文件校验
- 完成文档验收说明

## 约束

- 仍然以单项目导出为边界
- 不要引入邮件发送或自动任务
- 可以保持同步导出，但要具备任务记录
- 不要破坏现有 `/api/cost-statistics/export`

## 推荐接口

- `POST /api/cost-statistics/project-exports`
- `GET /api/cost-statistics/project-exports/{export_id}`
- `GET /api/cost-statistics/project-exports/{export_id}/download`
- `GET /api/cost-statistics/project-exports?project_name=...`

## 交付物

- 导出历史持久化模型
- 导出任务 API
- 再次下载能力
- 前后端回归测试
- 验收文档

## 验收标准

- 每次项目导出都有历史记录
- 用户能在最近导出里再次下载
- 导出失败有明确状态和错误原因
- 核心导出 sheet 结构和字段可通过测试校验
- 前后端测试通过

## 可直接使用的 Prompt

```md
请为“项目明细强导出”补齐导出历史、任务状态和 QA。

背景：
- 已经有项目强导出后端底座
- 也已经有前端导出交互
- 现在需要把它收口成正式能力

实现要求：

1. 为每次项目导出生成导出历史记录
2. 提供导出历史查询接口
3. 支持基于 `export_id` 再次下载文件
4. 明确导出状态：
   - pending
   - ready
   - failed
5. 补文件结构校验测试：
   - sheet 是否齐全
   - 关键列是否存在
   - 文件名是否符合规则
6. 补前后端验收说明

注意：
- 这一步重点是“可追溯、可回看、可验收”。
- 不要扩展到邮件、通知、自动定时导出。
```
