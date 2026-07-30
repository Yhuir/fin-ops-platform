# 关联台详情 generation 一致性修复

## 目标

彻底修复关联台 OA、银行流水、发票详情抽屉在 generation 刷新期间出现“详情加载失败”的问题，同时保持现有 generation 原子发布模型和 API 边界。

## 实施

- [x] 相同 `source_versions` 且 active generation 健康时跳过重复发布。
- [x] 激活前验证所有可见事实行均已物化到 `workbench_rows`。
- [x] 在同一个只读 repeatable-read 快照内完成版本校验和详情读取。
- [x] 删除空 `workbench_group_rows.payload` 的旧详情 fallback。
- [x] 前端遇到 generation 冲突时等待一次后台刷新并仅重试一次详情请求。
- [x] 更新关联台/read model 边界文档和定向回归测试。
- [ ] 验证全部工作区改动，提交并推送 `main`，部署后执行生产只读链路与性能验证。

## 验收

- OA、银行流水、发票详情均能在 active generation 下稳定读取。
- 并发刷新最多触发一次受控恢复，不出现循环重试或错误详情覆盖。
- 完全相同的事实版本不制造新 generation。
- 不完整 generation 无法激活。
- 定向后端、前端、lint/契约测试通过，生产只读验证通过。
