from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PageAuditExecutor = Literal[
    "workbench",
    "page_business",
    "input_invoice_usage",
    "output_invoice_collection",
    "tax_offset",
    "etc_tickets",
    "settings",
    "bank_transaction_import",
    "invoice_import",
    "etc_import",
    "system",
    "unavailable",
]
PageAuditAvailability = Literal["ready", "unavailable"]
ExternalEvidenceDomain = Literal["bank", "oa", "invoice", "etc"]

PAGE_AUDIT_CONTRACT_REVISION = "page-audit-contract.v24"


@dataclass(frozen=True, slots=True)
class PageAuditRegistration:
    page_key: str
    label: str
    executor: PageAuditExecutor
    availability: PageAuditAvailability
    read_model_keys: tuple[str, ...]
    relation_proof_required: bool
    external_source_boundary: str
    external_evidence_keys: tuple[ExternalEvidenceDomain, ...]
    executor_domain_key: str | None = None
    unavailable_reason: str | None = None
    contract_revision: str = PAGE_AUDIT_CONTRACT_REVISION

    def __post_init__(self) -> None:
        if self.availability == "ready" and self.executor == "unavailable":
            raise ValueError(f"Ready page audit {self.page_key} requires an executor.")
        if self.availability == "unavailable" and not self.unavailable_reason:
            raise ValueError(f"Unavailable page audit {self.page_key} requires a reason.")
        if self.executor == "page_business" and not self.executor_domain_key:
            raise ValueError(f"Page business audit {self.page_key} requires executor_domain_key.")
        if len(self.external_evidence_keys) != len(set(self.external_evidence_keys)):
            raise ValueError(f"Page audit {self.page_key} has duplicate external evidence dependencies.")


def _ready(
    page_key: str,
    label: str,
    executor: PageAuditExecutor,
    read_model_keys: tuple[str, ...],
    *,
    relation_proof_required: bool = True,
    external_source_boundary: str,
    external_evidence_keys: tuple[ExternalEvidenceDomain, ...],
    executor_domain_key: str | None = None,
) -> PageAuditRegistration:
    return PageAuditRegistration(
        page_key=page_key,
        label=label,
        executor=executor,
        availability="ready",
        read_model_keys=read_model_keys,
        relation_proof_required=relation_proof_required,
        external_source_boundary=external_source_boundary,
        external_evidence_keys=external_evidence_keys,
        executor_domain_key=executor_domain_key,
    )


def _unavailable(
    page_key: str,
    label: str,
    read_model_keys: tuple[str, ...],
    *,
    relation_proof_required: bool,
    external_source_boundary: str,
    external_evidence_keys: tuple[ExternalEvidenceDomain, ...],
) -> PageAuditRegistration:
    return PageAuditRegistration(
        page_key=page_key,
        label=label,
        executor="unavailable",
        availability="unavailable",
        read_model_keys=read_model_keys,
        relation_proof_required=relation_proof_required,
        external_source_boundary=external_source_boundary,
        external_evidence_keys=external_evidence_keys,
        unavailable_reason="page proof contract is registered but its canonical/consumer proof is not implemented",
    )


PAGE_AUDIT_REGISTRY: dict[str, PageAuditRegistration] = {
    "reconciliation-workbench": _ready(
        "reconciliation-workbench",
        "关联台",
        "workbench",
        ("workbench", "workbench_relation"),
        external_source_boundary="bank, OA, invoice, and ETC source evidence before App registration",
        external_evidence_keys=("bank", "oa", "invoice", "etc"),
    ),
    "cost-statistics": _ready(
        "cost-statistics",
        "成本统计",
        "page_business",
        ("cost_statistics", "bank_detail", "workbench_relation"),
        external_source_boundary="OA, bank, and invoice completeness before App registration",
        external_evidence_keys=("bank", "oa", "invoice", "etc"),
        executor_domain_key="cost_statistics",
    ),
    "bank-details": _ready(
        "bank-details",
        "银行明细",
        "page_business",
        ("bank_detail", "bank_account_balance", "workbench_relation"),
        external_source_boundary="bank statement completeness before App import",
        external_evidence_keys=("bank",),
        executor_domain_key="bank_details",
    ),
    "oa-pending-payments": _ready(
        "oa-pending-payments",
        "OA待付款核对",
        "page_business",
        ("oa_pending_payment", "invoice_lifecycle", "workbench_relation"),
        external_source_boundary="OA source and admission completeness before App registration",
        external_evidence_keys=("oa", "bank", "invoice"),
        executor_domain_key="oa_pending_payments",
    ),
    "bank-flow-rule-batches": _ready(
        "bank-flow-rule-batches",
        "流水规则批量处理",
        "page_business",
        ("bank_flow_rule_batch", "workbench_relation"),
        external_source_boundary="bank statement completeness before App import",
        external_evidence_keys=("bank",),
        executor_domain_key="bank_flow_rule_batches",
    ),
    "batch-accounting": _ready(
        "batch-accounting",
        "批量账务",
        "page_business",
        ("workbench_relation",),
        external_source_boundary="OA and bank completeness before App registration",
        external_evidence_keys=("oa", "bank"),
        executor_domain_key="batch_accounting",
    ),
    "turnover-ledger": _ready(
        "turnover-ledger",
        "外部往来款管理",
        "page_business",
        ("turnover_ledger", "bank_detail", "workbench_relation"),
        external_source_boundary="bank statement completeness before App import",
        external_evidence_keys=("bank",),
        executor_domain_key="turnover_ledger",
    ),
    "etc-tickets": _ready(
        "etc-tickets",
        "ETC票据管理",
        "etc_tickets",
        (),
        relation_proof_required=True,
        external_source_boundary="ETC source archive bytes/object readability and real OA draft state",
        external_evidence_keys=("etc", "oa"),
    ),
    "tax-offset": _ready(
        "tax-offset",
        "税金抵扣",
        "tax_offset",
        ("tax_offset",),
        relation_proof_required=False,
        external_source_boundary="certified tax source plus invoice and ETC evidence",
        external_evidence_keys=("invoice", "etc"),
    ),
    "pending-invoices": _ready(
        "pending-invoices",
        "待找发票",
        "page_business",
        ("pending_invoice", "bank_detail", "workbench_relation", "invoice_lifecycle"),
        external_source_boundary="bank, invoice, and OA completeness before App registration",
        external_evidence_keys=("bank", "invoice", "oa"),
        executor_domain_key="pending_invoices",
    ),
    "input-invoice-usage": _ready(
        "input-invoice-usage",
        "进项发票使用情况",
        "input_invoice_usage",
        ("input_invoice_usage", "workbench_relation", "invoice_lifecycle"),
        external_source_boundary="invoice, OA, and bank completeness before App registration",
        external_evidence_keys=("invoice", "oa", "bank"),
    ),
    "output-invoice-collections": _ready(
        "output-invoice-collections",
        "销项发票收款情况",
        "output_invoice_collection",
        ("output_invoice_collection", "workbench_relation", "invoice_lifecycle"),
        external_source_boundary="invoice and bank completeness before App registration",
        external_evidence_keys=("invoice", "bank"),
    ),
    "settings": _ready(
        "settings",
        "设置",
        "settings",
        (),
        relation_proof_required=False,
        external_source_boundary="OA/project provider evidence where configured",
        external_evidence_keys=("oa",),
    ),
    "app-health-operations": _ready(
        "app-health-operations",
        "系统状态",
        "system",
        (),
        relation_proof_required=False,
        external_source_boundary="not_applicable; dependency availability is reported separately",
        external_evidence_keys=(),
    ),
    "imports.bank-transactions": _ready(
        "imports.bank-transactions",
        "银行流水导入",
        "bank_transaction_import",
        (),
        relation_proof_required=False,
        external_source_boundary="original bank file hash and control totals",
        external_evidence_keys=("bank",),
    ),
    "imports.invoices": _ready(
        "imports.invoices",
        "发票导入",
        "invoice_import",
        (),
        relation_proof_required=False,
        external_source_boundary="original invoice file hash and control totals",
        external_evidence_keys=("invoice",),
    ),
    "imports.etc-invoices": _ready(
        "imports.etc-invoices",
        "ETC发票导入",
        "etc_import",
        (),
        relation_proof_required=True,
        external_source_boundary="ETC archive hash and batch control totals",
        external_evidence_keys=("etc",),
    ),
}


def page_audit_registration(page_key: str) -> PageAuditRegistration:
    normalized_page_key = str(page_key or "").strip()
    registration = PAGE_AUDIT_REGISTRY.get(normalized_page_key)
    if registration is None:
        raise ValueError(f"Unsupported page audit page: {page_key}")
    return registration


def legacy_domain_page_key(domain_key: str) -> str | None:
    normalized_domain_key = str(domain_key or "").strip()
    for registration in PAGE_AUDIT_REGISTRY.values():
        if registration.executor_domain_key == normalized_domain_key:
            return registration.page_key
    return None
