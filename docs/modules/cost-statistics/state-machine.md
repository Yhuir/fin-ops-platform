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
```

## 状态合同

- `loading`：当前 HTTP 请求尚未完成，按钮和页面展示正常加载反馈。
- `ready`：响应全部来自同一个数据库一致性快照。
- `error`：本次请求失败，不显示旧数据为 fresh。
- `searching / changing-surface`：当前视图搜索、范围或下钻请求进行中，只显示内容区反馈，不清空页头或刷新整个页面。
- `loading-next-page`：表格内部接近底部后自动追加 cursor 下一页；同一 cursor 同时只允许一个请求。
- `next-page-error`：下一页失败不丢弃已加载 rows，只在明细区提供重试。
- 重新访问、浏览器刷新或页面内刷新都会发起全新请求；没有 `202 refreshing`、`409 read_model_not_fresh` 或后台轮询。
- 页面打开期间事实源发生变化时不主动推送；用户下次刷新读取最新已提交事实。
