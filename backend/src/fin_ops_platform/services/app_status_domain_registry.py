from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppStatusDomainDefinition:
    key: str
    label: str
    route: str
    read_model_keys: tuple[str, ...] = ()
    worker_instances: tuple[str, ...] = ()
    job_types: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    critical: bool = True


APP_STATUS_DOMAIN_REGISTRY: tuple[AppStatusDomainDefinition, ...] = (
    AppStatusDomainDefinition(
        key="workbench",
        label="关联台",
        route="/",
        read_model_keys=("workbench", "workbench_relation"),
        worker_instances=("workbench", "workbench-relation", "workbench-matching"),
        job_types=("workbench_rebuild", "workbench_read_model_rebuild", "oa_sync_workbench_rebuild", "workbench_matching"),
        dependencies=("oa_sync",),
    ),
    AppStatusDomainDefinition(
        key="imports_bank_transactions",
        label="银行流水导入",
        route="/imports/bank-transactions",
        worker_instances=("import",),
        job_types=("file_import", "bank_transaction_import", "import.process.requested"),
    ),
    AppStatusDomainDefinition(
        key="imports_invoices",
        label="发票导入",
        route="/imports/invoices",
        worker_instances=("import",),
        job_types=("file_import", "invoice_import", "import.process.requested"),
    ),
    AppStatusDomainDefinition(
        key="imports_etc_invoices",
        label="ETC发票导入",
        route="/imports/etc-invoices",
        worker_instances=("import",),
        job_types=("etc_invoice_import", "file_import", "import.process.requested"),
    ),
    AppStatusDomainDefinition(
        key="tax_offset",
        label="税金抵扣",
        route="/tax-offset",
        read_model_keys=("tax_offset", "invoice_lifecycle"),
        worker_instances=("tax-offset", "invoice-lifecycle", "invoice-lifecycle-secondary"),
        job_types=("tax_offset.read_model.refresh", "invoice_lifecycle.read_model.refresh", "tax_certified_import"),
    ),
    AppStatusDomainDefinition(
        key="cost_statistics",
        label="成本统计",
        route="/cost-statistics",
        read_model_keys=("cost_statistics",),
        worker_instances=("cost-statistics",),
        job_types=("cost_statistics.read_model.refresh", "cost_statistics_cache_warmup"),
    ),
    AppStatusDomainDefinition(
        key="bank_details",
        label="银行明细",
        route="/bank-details",
        read_model_keys=("bank_detail", "bank_account_balance"),
        worker_instances=("bank-detail", "bank-account-balance"),
        job_types=("bank_detail.read_model.refresh", "bank_account_balance.read_model.refresh", "bank_transaction_import"),
    ),
    AppStatusDomainDefinition(
        key="pending_invoices",
        label="待找发票",
        route="/pending-invoices",
        read_model_keys=("pending_invoice", "search", "invoice_lifecycle"),
        worker_instances=("pending-invoice", "search", "invoice-lifecycle", "invoice-lifecycle-secondary"),
        job_types=("pending_invoice.read_model.refresh", "search.read_model.refresh", "invoice_lifecycle.read_model.refresh"),
    ),
    AppStatusDomainDefinition(
        key="input_invoice_usage",
        label="进项发票使用",
        route="/input-invoice-usage",
        read_model_keys=("input_invoice_usage", "invoice_lifecycle"),
        worker_instances=("invoice-usage-collection", "invoice-lifecycle", "invoice-lifecycle-secondary"),
        job_types=("input_invoice_usage.read_model.refresh", "invoice_lifecycle.read_model.refresh"),
    ),
    AppStatusDomainDefinition(
        key="oa_pending_payments",
        label="OA待付款核对",
        route="/oa-pending-payments",
        read_model_keys=("oa_pending_payment", "invoice_lifecycle"),
        worker_instances=("invoice-usage-collection", "invoice-lifecycle", "invoice-lifecycle-secondary", "oa-sync"),
        job_types=("oa_pending_payment.read_model.refresh", "invoice_lifecycle.read_model.refresh", "oa.sync"),
        dependencies=("oa_sync",),
    ),
    AppStatusDomainDefinition(
        key="output_invoice_collections",
        label="销项收款",
        route="/output-invoice-collections",
        read_model_keys=("output_invoice_collection", "invoice_lifecycle"),
        worker_instances=("invoice-usage-collection", "invoice-lifecycle", "invoice-lifecycle-secondary"),
        job_types=("output_invoice_collection.read_model.refresh", "invoice_lifecycle.read_model.refresh"),
    ),
    AppStatusDomainDefinition(
        key="no_oa_bank_batches",
        label="免OA批次",
        route="/no-oa-bank-batches",
        read_model_keys=("no_oa_bank_batch",),
        worker_instances=("no-oa-bank-batch",),
        job_types=("no_oa_bank_batch.read_model.refresh",),
    ),
    AppStatusDomainDefinition(
        key="batch_accounting",
        label="批量核销",
        route="/batch-accounting",
        read_model_keys=("workbench_relation",),
        worker_instances=("workbench-relation",),
        job_types=("workbench_relation.read_model.refresh",),
    ),
    AppStatusDomainDefinition(
        key="turnover_ledger",
        label="往来款管理",
        route="/turnover-ledger",
        read_model_keys=("turnover_ledger",),
        worker_instances=("turnover-ledger",),
        job_types=("turnover_ledger.read_model.refresh",),
    ),
    AppStatusDomainDefinition(
        key="etc_tickets",
        label="ETC票据",
        route="/etc-tickets",
        worker_instances=("import",),
        job_types=("etc_invoice_import",),
    ),
    AppStatusDomainDefinition(
        key="settings",
        label="设置",
        route="/settings",
        worker_instances=("oa-sync",),
        job_types=("oa.sync", "settings_refresh"),
        dependencies=("oa_identity", "state_store"),
    ),
    AppStatusDomainDefinition(
        key="app_health_operations",
        label="App Health",
        route="/operations/app-health",
        worker_instances=("oa-sync", "workbench", "bank-detail", "import"),
        dependencies=("background_jobs", "state_store"),
    ),
)


def domain_routes(domains: tuple[AppStatusDomainDefinition, ...] = APP_STATUS_DOMAIN_REGISTRY) -> tuple[str, ...]:
    return tuple(domain.route for domain in domains)


def domains_by_job_type(
    domains: tuple[AppStatusDomainDefinition, ...] = APP_STATUS_DOMAIN_REGISTRY,
) -> dict[str, tuple[AppStatusDomainDefinition, ...]]:
    mapping: dict[str, list[AppStatusDomainDefinition]] = {}
    for domain in domains:
        for job_type in domain.job_types:
            mapping.setdefault(job_type, []).append(domain)
    return {job_type: tuple(items) for job_type, items in mapping.items()}
