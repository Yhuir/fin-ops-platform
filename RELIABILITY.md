# 可靠性与生产治理

本文档记录生产级交付的通用要求。具体运维步骤见 `docs/operations/`。

## 基线要求

- 所有外部输入都要校验，包括导入文件、OA 数据、请求体、URL 参数和后台任务参数。
- 影响业务事实的写操作必须幂等，至少能处理重复提交、网络重试和刷新重放。
- 关键动作必须写审计：导入确认、核销确认、撤回、异常处理、数据重置、权限设置。
- 长任务必须有状态、进度、失败原因、重试策略和前端可见反馈。
- 生产发布必须有健康检查、回滚路径和数据备份策略。

## 性能要求

- 页面读取优先使用 read model，不在请求路径上全量重建。
- 导入确认、OA 同步、OCR、成本统计预热等长耗时流程应进入后台任务。
- 高基数字段和核心过滤字段必须有数据库索引或等价的持久化查询结构。
- 搜索和导出不能依赖前端隐藏或临时状态。

## 验证入口

当前仓库常用验证：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
cd web && npm run build
```

实际执行以 `backend/README.md`、`web/README.md` 和 `docs/dev/testing.md` 为准。
