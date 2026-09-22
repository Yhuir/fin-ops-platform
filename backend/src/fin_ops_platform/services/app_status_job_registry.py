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
    "file_import": AppStatusBackgroundJobDefinition(
        "file_import",
        "文件导入",
        (),
        "/operations/app-health",
        legacy=True,
    ),
    "bank_transaction_import": AppStatusBackgroundJobDefinition("bank_transaction_import", "银行流水导入", ("imports_bank_transactions", "bank_details"), "/imports/bank-transactions"),
    "invoice_import": AppStatusBackgroundJobDefinition("invoice_import", "发票导入", ("imports_invoices",), "/imports/invoices"),
    "etc_invoice_import": AppStatusBackgroundJobDefinition("etc_invoice_import", "ETC发票导入", ("imports_etc_invoices", "etc_tickets"), "/imports/etc-invoices"),
    "file_import.confirm": AppStatusBackgroundJobDefinition(
        "file_import.confirm", "文件导入", (), "/operations/app-health",
    ),
    "etc_invoice_import.confirm": AppStatusBackgroundJobDefinition(
        "etc_invoice_import.confirm", "ETC发票导入", ("imports_etc_invoices", "etc_tickets"), "/imports/etc-invoices",
    ),
    "tax_certified_import.confirm": AppStatusBackgroundJobDefinition(
        "tax_certified_import.confirm", "税金认证导入", ("tax_offset",), "/tax-offset",
    ),
    "oa_manual_import.create": AppStatusBackgroundJobDefinition(
        "oa_manual_import.create", "OA手动导入", ("settings",), "/settings",
    ),
    "tax_certified_import": AppStatusBackgroundJobDefinition("tax_certified_import", "税金认证导入", ("tax_offset",), "/tax-offset", legacy=True),
    "oa.sync": AppStatusBackgroundJobDefinition("oa.sync", "OA同步", ("oa_pending_payments",), "/oa-pending-payments"),
    "settings_refresh": AppStatusBackgroundJobDefinition("settings_refresh", "刷新设置", ("settings",), "/settings", legacy=True),
    "settings_data_reset": AppStatusBackgroundJobDefinition("settings_data_reset", "设置数据重置", ("settings",), "/settings", legacy=True),
    "bank_relation_requirement_recalculation": AppStatusBackgroundJobDefinition(
        "bank_relation_requirement_recalculation",
        "重算流水关联要求",
        ("settings", "workbench"),
        "/bank-flow-rule-batches",
    ),
    "historical_etc_reconcile": AppStatusBackgroundJobDefinition("historical_etc_reconcile", "历史ETC核对", ("etc_tickets",), "/etc-tickets", legacy=True),
}
