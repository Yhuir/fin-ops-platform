# App 内 PyMongo 安全补丁

当前发行版为 `4.17.0+finops.1`，保留上游 4.17 的 MongoDB 4.2 协议支持。
这是财务 App 自行构建的补丁版本，不是 MongoDB 官方发布版本，也不修改 OA 服务。

`security.patch` 移植官方 4.18.1 / 4.18.2 中的 CVE-2026-88029、
CVE-2026-96747、CVE-2026-96748、CVE-2026-96749 修复，覆盖同步、异步和共享实现。
另移植 4.18 的 BSON 数组嵌套文档越界检查与 Extended JSON timestamp 字段检查。
不移植 4.18 取消旧服务器支持的改动，也不降低协议版本检查。

来源：[官方发布说明](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/release-notes/)、
[官方安全修复差异](https://github.com/mongodb/mongo-python-driver/compare/4.18.0...4.18.2)。
补丁衍生代码沿用上游 Apache-2.0 许可证；安装包保留上游 LICENSE。

构建、安装、审计由 [python_dependencies.py](../../../scripts/python_dependencies.py) 唯一负责：

```bash
python3 scripts/python_dependencies.py install
python3 scripts/python_dependencies.py audit
```

构建固定上游源码摘要及构建后端，精确应用补丁后重新生成发行元数据和 C 扩展。
安装包与来源信息存于 ignored `.runtime/python-wheels/`。摘要仅验证构建与安装边界，
不是业务数据身份。修改补丁后使用新的构建目录，不复用旧构建记录。

审计在独立环境中安装 App 及审计工具，扫描实际安装依赖（含传递依赖）。PyMongo
按上游 4.17.0 查询漏洞库，防止本地版本号被扫描器跳过；先核对安装内容与构建包，
执行 `test_security.py`，再将已验证的四个补丁单独列为 `verified_backports`。
原始结果完整保留，未知漏洞、其他版本或未验证构建不被豁免。

原生安全回归：`python3 backend/vendor/pymongo/test_security.py -v`。
真实协议测试在 [test_pymongo_security.py](../../../tests/test_pymongo_security.py)，只使用显式设置的
`FIN_OPS_TEST_MONGO_URI` 和随机 `fin_ops_driver_test_*` 数据库，结束删除该测试库。
CI 使用独立 MongoDB 4.2.6 容器；不得将该变量指向 OA 实例。

版本维护责任在 App：新增漏洞必须重新评估，补丁版不能保证永久兼容或未来零漏洞。
