# Canonical Facts Wave 5 - Mongo exporter definition package removal

日期：2026-06-29

## 目标

删除旧 App Mongo/stage export definition package。`export_manifest.py` 和 Mongo staging migration CLI 已删除后，`backend/src/fin_ops_platform/tools/exporters/` 只剩自引用 export definition 常量和 Python bytecode cache，不再有当前 owner、runbook 或调用方。

## 删除

- `backend/src/fin_ops_platform/tools/exporters/__init__.py`
- `backend/src/fin_ops_platform/tools/exporters/core.py`
- `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py`
- `backend/src/fin_ops_platform/tools/exporters/read_models.py`
- `backend/src/fin_ops_platform/tools/exporters/workbench.py`
- `backend/src/fin_ops_platform/tools/exporters/__pycache__/`

## Guard

- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_legacy_mongo_exporter_definition_package_is_removed`

Guard 覆盖：

- `tools/exporters/` 目录不能回归。
- tools 目录不能重新 import `fin_ops_platform.tools.exporters`。
- tools 目录不能重新出现旧 stage export markers：`ExportDefinition`、`CORE_EXPORTS`、`WORKBENCH_EXPORTS`、`OPS_TAX_ETC_EXPORTS`、`READ_MODEL_EXPORTS`、`gridfs_files_manifest`、`stage 03`、`stage 04`。

## 验证计划

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_mongo_exporter_definition_package_is_removed
test ! -d backend/src/fin_ops_platform/tools/exporters
rg -n "fin_ops_platform\\.tools\\.exporters|ExportDefinition|CORE_EXPORTS|WORKBENCH_EXPORTS|OPS_TAX_ETC_EXPORTS|READ_MODEL_EXPORTS|gridfs_files_manifest|stage 03|stage 04" backend/src/fin_ops_platform/tools tests/test_platform_runtime_boundary_guards.py -g '*.py'
```

## 剩余风险

- 这是旧 migration/export definition 删除，不改变生产 API、worker、repository、read model runtime 或业务事实写路径。
