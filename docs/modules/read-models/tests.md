# Read Model 退役测试

- 删除面/worker/API/frontend/deploy/migration：`tests/test_read_model_runtime_removal.py`
- 负向旧事件：`tests/test_retired_projection_event_audit.py`
- 页面 canonical service/API/frontend regression：各业务模块测试。
- 生产：page/system audit、HTTP SLO、health/worker/queue closure。
