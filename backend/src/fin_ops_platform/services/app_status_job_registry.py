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
    "workbench_read_model_rebuild": AppStatusBackgroundJobDefinition("workbench_read_model_rebuild", "刷新关联台", ("workbench",), "/"),
    "oa_sync_workbench_rebuild": AppStatusBackgroundJobDefinition("oa_sync_workbench_rebuild", "OA同步关联台", ("workbench",), "/"),
    "workbench_matching": AppStatusBackgroundJobDefinition("workbench_matching", "关联台匹配", ("workbench",), "/"),
    "workbench.read_model.refresh": AppStatusBackgroundJobDefinition("workbench.read_model.refresh", "刷新关联台", ("workbench",), "/"),
    "workbench_relation.read_model.refresh": AppStatusBackgroundJobDefinition("workbench_relation.read_model.refresh", "刷新批量核销", ("batch_accounting", "workbench"), "/batch-accounting"),
    "file_import": AppStatusBackgroundJobDefinition("file_import", "文件导入", ("imports_invoices",), "/imports/invoices", legacy=True),
    "bank_transaction_import": AppStatusBackgroundJobDefinition("bank_transaction_import", "银行流水导入", ("imports_bank_transactions", "bank_details"), "/imports/bank-transactions"),
    "invoice_import": AppStatusBackgroundJobDefinition("invoice_import", "发票导入", ("imports_invoices",), "/imports/invoices"),
    "etc_invoice_import": AppStatusBackgroundJobDefinition("etc_invoice_import", "ETC发票导入", ("imports_etc_invoices", "etc_tickets"), "/imports/etc-invoices"),
    "import.process.requested": AppStatusBackgroundJobDefinition("import.process.requested", "导入处理", ("imports_invoices",), "/imports/invoices"),
    "tax_offset.read_model.refresh": AppStatusBackgroundJobDefinition("tax_offset.read_model.refresh", "刷新税金抵扣", ("tax_offset",), "/tax-offset"),
    "tax_certified_import": AppStatusBackgroundJobDefinition("tax_certified_import", "税金认证导入", ("tax_offset",), "/tax-offset", legacy=True),
    "tax_offset_cache_warmup": AppStatusBackgroundJobDefinition("tax_offset_cache_warmup", "税金抵扣缓存预热", ("tax_offset",), "/tax-offset"),
    "cost_statistics.read_model.refresh": AppStatusBackgroundJobDefinition("cost_statistics.read_model.refresh", "刷新成本统计", ("cost_statistics",), "/cost-statistics"),
    "cost_statistics_cache_warmup": AppStatusBackgroundJobDefinition("cost_statistics_cache_warmup", "成本统计缓存预热", ("cost_statistics",), "/cost-statistics"),
    "bank_detail.read_model.refresh": AppStatusBackgroundJobDefinition("bank_detail.read_model.refresh", "刷新银行明细", ("bank_details",), "/bank-details"),
    "bank_account_balance.read_model.refresh": AppStatusBackgroundJobDefinition("bank_account_balance.read_model.refresh", "刷新银行余额", ("bank_details",), "/bank-details"),
    "pending_invoice.read_model.refresh": AppStatusBackgroundJobDefinition("pending_invoice.read_model.refresh", "刷新待找发票", ("pending_invoices",), "/pending-invoices"),
    "search.read_model.refresh": AppStatusBackgroundJobDefinition("search.read_model.refresh", "刷新搜索索引", ("pending_invoices",), "/pending-invoices"),
    "invoice_lifecycle.read_model.refresh": AppStatusBackgroundJobDefinition("invoice_lifecycle.read_model.refresh", "刷新发票生命周期", ("pending_invoices", "tax_offset", "input_invoice_usage", "output_invoice_collections"), "/pending-invoices"),
    "input_invoice_usage.read_model.refresh": AppStatusBackgroundJobDefinition("input_invoice_usage.read_model.refresh", "刷新进项发票使用", ("input_invoice_usage",), "/input-invoice-usage"),
    "output_invoice_collection.read_model.refresh": AppStatusBackgroundJobDefinition("output_invoice_collection.read_model.refresh", "刷新销项收款", ("output_invoice_collections",), "/output-invoice-collections"),
    "oa_pending_payment.read_model.refresh": AppStatusBackgroundJobDefinition("oa_pending_payment.read_model.refresh", "刷新OA待付款", ("oa_pending_payments",), "/oa-pending-payments"),
    "oa.sync": AppStatusBackgroundJobDefinition("oa.sync", "OA同步", ("oa_pending_payments", "settings"), "/oa-pending-payments"),
    "no_oa_bank_batch.read_model.refresh": AppStatusBackgroundJobDefinition("no_oa_bank_batch.read_model.refresh", "刷新免OA批次", ("no_oa_bank_batches",), "/no-oa-bank-batches"),
    "turnover_ledger.read_model.refresh": AppStatusBackgroundJobDefinition("turnover_ledger.read_model.refresh", "刷新往来款台账", ("turnover_ledger",), "/turnover-ledger"),
    "etc_business.oa_detection.refresh": AppStatusBackgroundJobDefinition("etc_business.oa_detection.refresh", "刷新ETC业务OA检测", ("etc_tickets",), "/etc-tickets"),
    "settings_refresh": AppStatusBackgroundJobDefinition("settings_refresh", "刷新设置", ("settings",), "/settings", legacy=True),
    "settings_data_reset": AppStatusBackgroundJobDefinition("settings_data_reset", "设置数据重置", ("settings",), "/settings", legacy=True),
    "historical_etc_reconcile": AppStatusBackgroundJobDefinition("historical_etc_reconcile", "历史ETC核对", ("etc_tickets",), "/etc-tickets", legacy=True),
}
