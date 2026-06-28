from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppStatusBackgroundJobDefinition:
    type: str
    label: str
    affected_domains: tuple[str, ...]
    route: str
    progress_policy: str = "optional_percent"
    legacy: bool = False


APP_STATUS_BACKGROUND_JOB_REGISTRY: dict[str, AppStatusBackgroundJobDefinition] = {
    "workbench_rebuild": AppStatusBackgroundJobDefinition("workbench_rebuild", "重建关联台", ("workbench",), "/"),
    "oa_sync_workbench_rebuild": AppStatusBackgroundJobDefinition("oa_sync_workbench_rebuild", "OA同步关联台", ("workbench",), "/"),
    "workbench_matching": AppStatusBackgroundJobDefinition("workbench_matching", "关联台匹配", ("workbench",), "/"),
    "file_import": AppStatusBackgroundJobDefinition(
        "file_import",
        "文件导入",
        ("imports_bank_transactions", "imports_invoices", "imports_etc_invoices"),
        "/operations/app-health",
        legacy=True,
    ),
    "bank_transaction_import": AppStatusBackgroundJobDefinition("bank_transaction_import", "银行流水导入", ("imports_bank_transactions", "bank_details"), "/imports/bank-transactions"),
    "invoice_import": AppStatusBackgroundJobDefinition("invoice_import", "发票导入", ("imports_invoices",), "/imports/invoices"),
    "etc_invoice_import": AppStatusBackgroundJobDefinition("etc_invoice_import", "ETC发票导入", ("imports_etc_invoices", "etc_tickets"), "/imports/etc-invoices"),
    "import.process.requested": AppStatusBackgroundJobDefinition(
        "import.process.requested",
        "导入处理",
        ("imports_bank_transactions", "imports_invoices", "imports_etc_invoices"),
        "/operations/app-health",
    ),
    "tax_certified_import": AppStatusBackgroundJobDefinition("tax_certified_import", "税金认证导入", ("tax_offset",), "/tax-offset", legacy=True),
    "tax_offset_cache_warmup": AppStatusBackgroundJobDefinition("tax_offset_cache_warmup", "税金抵扣缓存预热", ("tax_offset",), "/tax-offset"),
    "cost_statistics_cache_warmup": AppStatusBackgroundJobDefinition("cost_statistics_cache_warmup", "成本统计缓存预热", ("cost_statistics",), "/cost-statistics"),
    "oa.sync": AppStatusBackgroundJobDefinition("oa.sync", "OA同步", ("oa_pending_payments",), "/oa-pending-payments"),
    "settings_refresh": AppStatusBackgroundJobDefinition("settings_refresh", "刷新设置", ("settings",), "/settings", legacy=True),
    "settings_data_reset": AppStatusBackgroundJobDefinition("settings_data_reset", "设置数据重置", ("settings",), "/settings", legacy=True),
    "historical_etc_reconcile": AppStatusBackgroundJobDefinition("historical_etc_reconcile", "历史ETC核对", ("etc_tickets",), "/etc-tickets", legacy=True),
}
