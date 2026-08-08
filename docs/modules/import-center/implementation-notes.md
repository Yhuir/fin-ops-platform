# 导入中心实施记录

## 2026-08-09

- 复用现有 import facts API 和 FinanceTable/HeroUI，不新增后端聚合状态、依赖或导入状态机。
- 新增只读组合 Page Audit；三个业务导入 proof 仍是唯一审计 owner。
- 文件 SHA、防重、解析资源上限、源控制合计和银行强/弱身份规则仍由共享后端导入边界负责。
