# 成本统计状态机

成本统计没有后台刷新状态机。

```text
idle
  -> loading
      -> ready
      -> error
error
  -> 用户刷新
      -> loading

ready
  -> searching / changing-surface
      -> ready（只替换内容区）
      -> error（保留已加载上游内容）
  -> loading-next-page
      -> ready（追加 rows）
      -> next-page-error（保留已有 rows，可局部重试）

detail-closed
  -> detail-loading（抽屉立即打开）
      -> detail-ready
      -> detail-error
detail-error
  -> detail-loading（抽屉内重试）
detail-loading / detail-ready / detail-error
  -> detail-closed（关闭并取消未完成请求）

no-oa-drawer-closed
  -> no-oa-drawer-ready（打开现有“无 OA 成本范围”抽屉）
      -> saving
          -> no-oa-drawer-ready（保存成功并刷新成本数据）
          -> save-error（保留用户输入，可重试）
  -> no-oa-drawer-closed
```

## 状态合同

- `loading`：当前 HTTP 请求尚未完成，按钮和页面展示正常加载反馈。
- `ready`：响应全部来自同一个数据库一致性快照。
- `error`：本次请求失败，不显示旧数据为 fresh。
- `searching / changing-surface`：当前视图搜索、范围或下钻请求进行中，只显示内容区反馈，不清空页头或刷新整个页面。
- `loading-next-page`：表格内部接近底部后自动追加 cursor 下一页；同一 cursor 同时只允许一个请求。
- `next-page-error`：下一页失败不丢弃已加载 rows，只在明细区提供重试。
- `detail-loading`：只在右侧抽屉展示无文字 skeleton；不显示“正在加载流水”，不修改 explorer/导出 loading 状态。
- `detail-error`：错误与重试按钮只存在于抽屉；已加载统计内容保持不变。
- `no-oa-drawer-ready`：只显示当前实际无 active OA 关系的支出标签；名称和标签默认都为空。选择标签后必须填写虚拟项目名，未选择标签时名称可为空。
- `saving / save-error`：使用 settings version CAS；冲突或失败不得伪报成功，也不得清空用户输入。保存成功后下一次 canonical GET 对全部历史期间逐笔应用规则。
- 重新访问、浏览器刷新或页面内刷新都会发起全新请求；没有 `202 refreshing`、`409 read_model_not_fresh` 或后台轮询。
- 页面打开期间事实源发生变化时不主动推送；用户下次刷新读取最新已提交事实。
