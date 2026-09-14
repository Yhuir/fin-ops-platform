# 设置 E2E 合同

设置页维护普通平台设置以及 005 专属 control plane。普通 settings 与访问账户必须是两个独立 API/状态边界，任何一方失败不得污染另一方草稿。

| Spec ID | 场景 | 验收标准 |
| --- | --- | --- |
| `SETTINGS-E2E-001` | 普通设置 | 拥有 settings 页面权限的账号可读取和保存项目、银行映射、OA 导入范围等；请求不携带 ACL 或凭据。 |
| `SETTINGS-E2E-002` | 管理员隔离 | 非 005 不显示/调用访问账户、OA 凭据和数据重置；直接 admin API 返回 403。 |
| `SETTINGS-E2E-003` | 双栏访问账户 | 左栏 OA 搜索/账号/姓名/删除，右栏 17 页面 checkbox/全选/清空，底部保存；005 固定展示且不可编辑。 |
| `SETTINGS-E2E-004` | ACL CAS | PUT 只接受 `{expected_version,accounts[{username,page_keys}]}`；409 保留草稿，no-op 零 DB/audit/OA I/O。 |
| `SETTINGS-E2E-005` | OA 角色与补偿 | 真实变化先同步两角色，再原子提交 PostgreSQL ACL+audit；OA/PG/补偿失败分别返回明确 502/503，不能伪报成功。 |
| `SETTINGS-E2E-006` | 凭据安全 | OA 申请人密码不进入普通 settings、响应、日志或 audit。 |
| `SETTINGS-E2E-007` | 数据重置 | 005 双确认、OA 密码复核、后台 job 进度和结果保持既有合同。 |
| `SETTINGS-E2E-008` | 水平设置导航 | 原生 HeroUI Tabs 连接活动 Panel；桌面 8 项完整可见，窄屏横向滚动。1920/1440/1280/768 下 8 个子页面与居中工作区对齐且页面不横向溢出；保留必要状态与安全确认。 |
| `SETTINGS-E2E-009` | 跨 Tab 草稿 | 普通草稿切换后保留，切换不触发保存；保存全部设置只提交普通 DTO，成功后未保存状态清除。ACL/凭据/reset 保持独立。 |

访问账户不触发 read model、cache、dirty scope、background worker 或页面数据重建。
