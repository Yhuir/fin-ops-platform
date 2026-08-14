# Read Model 退役 E2E Spec

## Scenario

`READ-MODEL-RETIREMENT-E2E-001`：

所有页面读取 canonical facts；写后当前页单次重读；其它页面下次正常访问读取相同事实。任何旧 projection
event、worker、schema、DTO 或 fallback 都使验证失败。
