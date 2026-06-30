from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppStatusReadModelDefinition:
    key: str
    scope_type: str
    worker_instance: str
    refresh_event_type: str
    readiness_strategy: str = "app_status_readiness"
    critical: bool = True


APP_STATUS_READ_MODEL_REGISTRY: dict[str, AppStatusReadModelDefinition] = {
    "workbench": AppStatusReadModelDefinition(
        key="workbench",
        scope_type="workbench",
        worker_instance="workbench",
        refresh_event_type="workbench.read_model.refresh",
        readiness_strategy="active_generation",
    ),
    "workbench_relation": AppStatusReadModelDefinition(
        key="workbench_relation",
        scope_type="workbench_relation",
        worker_instance="workbench-relation",
        refresh_event_type="workbench_relation.read_model.refresh",
    ),
    "bank_detail": AppStatusReadModelDefinition(
        key="bank_detail",
        scope_type="bank_detail",
        worker_instance="bank-detail",
        refresh_event_type="bank_detail.read_model.refresh",
    ),
    "bank_account_balance": AppStatusReadModelDefinition(
        key="bank_account_balance",
        scope_type="bank_account_balance",
        worker_instance="bank-account-balance",
        refresh_event_type="bank_account_balance.read_model.refresh",
    ),
    "pending_invoice": AppStatusReadModelDefinition(
        key="pending_invoice",
        scope_type="pending_invoice",
        worker_instance="pending-invoice",
        refresh_event_type="pending_invoice.read_model.refresh",
    ),
    "search": AppStatusReadModelDefinition(
        key="search",
        scope_type="search",
        worker_instance="search",
        refresh_event_type="search.read_model.refresh",
    ),
    "invoice_lifecycle": AppStatusReadModelDefinition(
        key="invoice_lifecycle",
        scope_type="invoice_lifecycle",
        worker_instance="invoice-lifecycle",
        refresh_event_type="invoice_lifecycle.read_model.refresh",
    ),
    "input_invoice_usage": AppStatusReadModelDefinition(
        key="input_invoice_usage",
        scope_type="input_invoice_usage",
        worker_instance="invoice-usage-collection",
        refresh_event_type="input_invoice_usage.read_model.refresh",
    ),
    "output_invoice_collection": AppStatusReadModelDefinition(
        key="output_invoice_collection",
        scope_type="output_invoice_collection",
        worker_instance="invoice-usage-collection",
        refresh_event_type="output_invoice_collection.read_model.refresh",
    ),
    "oa_pending_payment": AppStatusReadModelDefinition(
        key="oa_pending_payment",
        scope_type="oa_pending_payment",
        worker_instance="invoice-usage-collection",
        refresh_event_type="oa_pending_payment.read_model.refresh",
    ),
    "cost_statistics": AppStatusReadModelDefinition(
        key="cost_statistics",
        scope_type="cost_statistics",
        worker_instance="cost-statistics",
        refresh_event_type="cost_statistics.read_model.refresh",
    ),
    "tax_offset": AppStatusReadModelDefinition(
        key="tax_offset",
        scope_type="tax_offset",
        worker_instance="tax-offset",
        refresh_event_type="tax_offset.read_model.refresh",
    ),
    "no_oa_bank_batch": AppStatusReadModelDefinition(
        key="no_oa_bank_batch",
        scope_type="no_oa_bank_batch",
        worker_instance="no-oa-bank-batch",
        refresh_event_type="no_oa_bank_batch.read_model.refresh",
    ),
    "bank_flow_rule_batch": AppStatusReadModelDefinition(
        key="bank_flow_rule_batch",
        scope_type="bank_flow_rule_batch",
        worker_instance="bank-flow-rule-batch",
        refresh_event_type="bank_flow_rule_batch.read_model.refresh",
    ),
    "turnover_ledger": AppStatusReadModelDefinition(
        key="turnover_ledger",
        scope_type="turnover_ledger",
        worker_instance="turnover-ledger",
        refresh_event_type="turnover_ledger.read_model.refresh",
    ),
}


def read_model_by_scope_type() -> dict[str, AppStatusReadModelDefinition]:
    return {definition.scope_type: definition for definition in APP_STATUS_READ_MODEL_REGISTRY.values()}


def read_model_by_refresh_event_type() -> dict[str, AppStatusReadModelDefinition]:
    return {definition.refresh_event_type: definition for definition in APP_STATUS_READ_MODEL_REGISTRY.values()}
