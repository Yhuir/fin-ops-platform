from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OperationSemantics:
    action_code: str
    action_label: str
    object_type: str
    object_label: str
    description: str

    def audit_metadata(self) -> dict[str, str]:
        return {
            "action_code": self.action_code,
            "action_label": self.action_label,
            "object_label": self.object_label,
            "description": self.description,
            "summary": self.action_label,
        }


@dataclass(frozen=True)
class _RouteRule:
    method: str
    prefix: str
    semantics: OperationSemantics
    suffix: str = ""

    def matches(self, method: str, route_path: str) -> bool:
        return (
            method == self.method
            and route_path.startswith(self.prefix)
            and (not self.suffix or route_path.endswith(self.suffix))
        )


def _semantic(
    action_code: str,
    action_label: str,
    object_type: str,
    object_label: str,
    description: str,
) -> OperationSemantics:
    return OperationSemantics(action_code, action_label, object_type, object_label, description)


_EXACT_ROUTES = {
    ("PUT", "/api/bank-details/auto-tag-rules"): _semantic(
        "bank.auto_tag_rules.update", "保存自动标签规则", "bank_tag_rule", "流水标签规则", "更新银行流水自动标签规则。"
    ),
    ("POST", "/api/bank-details/auto-tag-rules/reapply"): _semantic(
        "bank.auto_tag_rules.reapply",
        "重新应用标签规则",
        "bank_transaction",
        "银行流水",
        "对银行流水重新应用自动标签规则。",
    ),
    ("POST", "/api/bank-details/auto-tag-rules/file-replacement"): _semantic(
        "bank.auto_tag_rules.replace_file",
        "替换标签规则文件",
        "bank_tag_rule",
        "流水标签规则",
        "使用新文件替换银行流水标签规则。",
    ),
    ("PATCH", "/api/bank-details/transactions/categories"): _semantic(
        "bank.transactions.update_category", "更新流水分类", "bank_transaction", "银行流水", "批量更新银行流水分类。"
    ),
    ("PUT", "/api/cost-statistics/time-tag-rules"): _semantic(
        "cost_statistics.time_tag_rules.update",
        "保存按标签/按时间标签规则",
        "cost_time_tag_rule",
        "按标签/按时间标签规则",
        "更新按标签和按时间统计的银行流水标签范围。",
    ),
    ("PUT", "/api/cost-statistics/no-oa-rules"): _semantic(
        "cost_statistics.no_oa_rules.update",
        "保存无 OA 成本范围",
        "cost_no_oa_rule",
        "无 OA 成本范围",
        "更新无 OA 流水标签到虚拟项目的分配规则。",
    ),
    ("PUT", "/api/pending-invoices/rules"): _semantic(
        "pending_invoices.rules.update",
        "保存待找发票规则",
        "pending_invoice_rule",
        "待找发票规则",
        "更新待找发票页面的匹配规则。",
    ),
    ("PUT", "/api/pending-invoices/income-statuses"): _semantic(
        "pending_invoices.income_status.update_batch",
        "批量更新收入状态",
        "bank_transaction",
        "收入流水",
        "批量更新收入流水的开票状态。",
    ),
    ("POST", "/api/pending-invoices/attach-existing-invoices"): _semantic(
        "pending_invoices.attach_batch",
        "批量关联已有发票",
        "invoice_relation",
        "发票关联",
        "将所选收入流水批量关联到已有发票。",
    ),
    ("POST", "/api/pending-invoices/invoice-candidates/batch"): _semantic(
        "pending_invoices.candidates.find",
        "查找发票候选",
        "pending_invoice",
        "待找发票记录",
        "为所选记录查找可关联的发票候选。",
    ),
    ("POST", "/api/pending-invoices/attach-existing-invoices/preview"): _semantic(
        "pending_invoices.attach_batch.preview",
        "预览批量发票关联",
        "invoice_relation",
        "发票关联",
        "预览所选记录与已有发票的批量关联结果。",
    ),
    ("PUT", "/api/input-invoice-usage/payment-status-rules"): _semantic(
        "input_invoice.payment_rules.update",
        "保存付款状态规则",
        "payment_status_rule",
        "付款状态规则",
        "更新进项发票付款状态规则。",
    ),
    ("POST", "/api/input-invoice-usage/oa-reverse/batches"): _semantic(
        "input_invoice.oa_reverse.create",
        "创建反提 OA 批次",
        "oa_reverse_batch",
        "反提 OA 批次",
        "根据所选发票创建反提 OA 批次。",
    ),
    ("POST", "/api/input-invoice-usage/oa-reverse/preview"): _semantic(
        "input_invoice.oa_reverse.preview",
        "预览反提 OA",
        "oa_reverse_batch",
        "反提 OA 批次",
        "预览所选发票生成反提 OA 的结果。",
    ),
    ("POST", "/api/input-invoice-usage/oa-reverse/oa-draft"): _semantic(
        "input_invoice.oa_draft.create", "创建 OA 草稿", "oa_draft", "OA 草稿", "为反提批次创建 OA 草稿。"
    ),
    ("POST", "/api/oa-pending-payments/writeback-paid"): _semantic(
        "oa_pending.writeback_paid", "确认已支付", "oa_payment", "OA 付款项", "将所选 OA 付款项写回为已支付。"
    ),
    ("POST", "/api/oa-pending-payments/link-bank-transactions"): _semantic(
        "oa_pending.link_bank", "关联支出流水", "oa_bank_relation", "OA 与流水关联", "将 OA 付款项与所选支出流水关联。"
    ),
    ("PUT", "/api/no-oa-bank-batches/tag-selection"): _semantic(
        "no_oa_batch.tags.update", "更新免 OA 标签", "bank_tag_rule", "免 OA 标签", "更新免 OA 流水批量处理的标签选择。"
    ),
    ("POST", "/api/no-oa-bank-batches/submit"): _semantic(
        "no_oa_batch.create", "新建免 OA 批次", "bank_batch", "免 OA 流水批次", "按当前选择新建免 OA 流水批次。"
    ),
    ("POST", "/api/no-oa-bank-batches/submit-selection"): _semantic(
        "no_oa_batch.submit_selection",
        "提交免 OA 流水",
        "bank_batch",
        "免 OA 流水批次",
        "提交所选免 OA 流水进入批量处理。",
    ),
    ("PUT", "/api/bank-flow-rule-batches/tag-rules"): _semantic(
        "bank_flow_batch.rules.update",
        "保存流水批量规则",
        "bank_tag_rule",
        "流水批量规则",
        "更新流水规则批量处理的标签规则。",
    ),
    ("POST", "/api/bank-flow-rule-batches/submit-selection"): _semantic(
        "bank_flow_batch.submit_selection", "提交规则批次", "bank_batch", "流水规则批次", "提交所选流水进入规则批次。"
    ),
    ("PUT", "/api/batch-accounting/tag-rules"): _semantic(
        "batch_accounting.rules.update",
        "保存批量账务规则",
        "accounting_rule",
        "批量账务规则",
        "更新日常报销批量账务规则。",
    ),
    ("POST", "/api/batch-accounting/submit"): _semantic(
        "batch_accounting.submit",
        "提交批量账务",
        "accounting_relation",
        "批量账务关系",
        "提交所选 OA 与流水的批量账务关系。",
    ),
    ("PUT", "/api/turnover-ledger/tag-selection"): _semantic(
        "turnover.tags.update", "更新往来款标签", "turnover_tag_rule", "往来款标签", "更新外部往来款管理的标签选择。"
    ),
    ("POST", "/api/turnover-ledger/bank-row-tags/batch"): _semantic(
        "turnover.bank_tags.update", "批量标记往来流水", "bank_transaction", "往来流水", "批量更新外部往来流水标签。"
    ),
    ("POST", "/api/turnover-ledger/relations/confirm"): _semantic(
        "turnover.relation.confirm", "确认往来关系", "turnover_relation", "往来关系", "确认所选外部往来款关系。"
    ),
    ("POST", "/api/turnover-ledger/closures/confirm"): _semantic(
        "turnover.closure.confirm", "确认往来闭环", "turnover_closure", "往来闭环", "确认所选外部往来款已形成闭环。"
    ),
    ("POST", "/api/turnover-ledger/closures/withdraw"): _semantic(
        "turnover.closure.withdraw", "撤回往来闭环", "turnover_closure", "往来闭环", "撤回所选外部往来款闭环。"
    ),
    ("POST", "/api/workbench/settings"): _semantic(
        "settings.update", "保存关联台设置", "application_setting", "关联台设置", "更新关联台显示与匹配设置。"
    ),
    ("PUT", "/api/workbench/settings/access-control"): _semantic(
        "settings.access_control.update", "保存访问账户", "access_control", "访问账户", "更新 App 访问账户与权限。"
    ),
    ("POST", "/api/workbench/settings/oa/manual-search/refresh-attachments"): _semantic(
        "settings.oa.refresh_attachments", "刷新 OA 附件", "oa_attachment", "OA 附件", "刷新指定 OA 的附件解析结果。"
    ),
    ("POST", "/api/workbench/settings/oa/manual-imports"): _semantic(
        "settings.oa.manual_import", "导入 OA 数据", "oa_record", "OA 数据", "手工导入所选 OA 数据。"
    ),
    ("POST", "/api/workbench/settings/projects/sync"): _semantic(
        "settings.projects.sync", "同步项目", "project", "项目", "从 OA 同步项目数据。"
    ),
    ("POST", "/api/workbench/settings/projects"): _semantic(
        "settings.projects.create", "新增项目", "project", "项目", "新增一个项目。"
    ),
    ("POST", "/api/workbench/oa-invoice-supplements/manual"): _semantic(
        "workbench.oa_invoice.manual_attach",
        "录入并关联 OA 发票",
        "workbench_relation",
        "OA 发票关联",
        "将手工录入的整批发票写入统一发票池并关联到指定 OA 子付款项。",
    ),
    ("POST", "/api/workbench/oa-invoice-supplements/documents"): _semantic(
        "workbench.oa_invoice.document_upload",
        "上传 OA 补充凭证",
        "oa_supporting_document",
        "OA 补充凭证",
        "上传不进入统一发票池的补充凭证并关联到指定 OA 子付款项。",
    ),
    ("POST", "/api/workbench/settings/data-reset/jobs"): _semantic(
        "settings.data_reset.create", "提交数据重置", "data_reset_job", "数据重置任务", "提交受控的数据重置任务。"
    ),
    ("POST", "/api/tax-offset/plans"): _semantic(
        "tax_offset.plan.save", "保存抵扣计划", "tax_offset_plan", "税金抵扣计划", "保存税金抵扣计划。"
    ),
    ("POST", "/api/tax-offset/calculate"): _semantic(
        "tax_offset.plan.calculate",
        "计算抵扣方案",
        "tax_offset_plan",
        "税金抵扣计划",
        "按当前发票与目标金额计算抵扣方案。",
    ),
    ("POST", "/api/tax-offset/certified-import/preview"): _semantic(
        "tax_offset.certified_import.preview",
        "预览已认证发票导入",
        "certified_invoice_import",
        "已认证发票导入",
        "解析并预览已认证发票数据。",
    ),
    ("POST", "/api/tax-offset/certified-import/confirm"): _semantic(
        "tax_offset.certified_import.confirm",
        "确认已认证发票导入",
        "certified_invoice_import",
        "已认证发票导入",
        "确认导入已认证发票数据。",
    ),
    ("POST", "/api/etc/import/confirm"): _semantic(
        "etc.import.confirm", "确认 ETC 发票导入", "etc_import", "ETC 发票导入", "确认导入 ETC 发票数据。"
    ),
    ("POST", "/api/etc/import/preview"): _semantic(
        "etc.import.preview",
        "预览 ETC 发票导入",
        "etc_import",
        "ETC 发票导入",
        "解析并预览 ETC 发票数据。",
    ),
    ("POST", "/api/etc/business-batches"): _semantic(
        "etc.business_batch.create",
        "新建 ETC 业务批次",
        "etc_business_batch",
        "ETC 业务批次",
        "新建一个 ETC 业务批次。",
    ),
    ("POST", "/api/etc/reconciliation-tasks"): _semantic(
        "etc.task.create", "新建 ETC 对账任务", "etc_reconciliation_task", "ETC 对账任务", "新建 ETC 票据对账任务。"
    ),
    ("POST", "/imports/invoices/manual/preview"): _semantic(
        "imports.invoice.preview", "预览发票录入", "invoice_import", "发票录入", "解析并预览待录入的发票。"
    ),
    ("POST", "/imports/invoices/manual/recognize"): _semantic(
        "imports.invoice.recognize", "识别发票", "invoice_import", "发票录入", "识别待录入发票的业务字段。"
    ),
    ("POST", "/imports/files/preview"): _semantic(
        "imports.files.preview", "预览文件导入", "file_import", "文件导入", "解析并预览待导入的文件。"
    ),
    ("POST", "/imports/files/confirm"): _semantic(
        "imports.files.confirm", "确认文件导入", "file_import", "文件导入", "确认导入预览中的文件数据。"
    ),
    ("POST", "/imports/files/retry"): _semantic(
        "imports.files.retry", "重试文件导入", "file_import", "文件导入", "重试处理导入失败的文件。"
    ),
    ("POST", "/imports/files/discard"): _semantic(
        "imports.files.discard", "放弃文件导入", "file_import", "文件导入", "放弃当前文件导入会话。"
    ),
}


_WORKBENCH_ACTIONS = {
    "confirm-link": _semantic(
        "workbench.relation.confirm", "确认关联", "workbench_relation", "关联关系", "将所选 OA、流水和发票确认关联。"
    ),
    "cancel-link": _semantic(
        "workbench.relation.cancel", "取消关联", "workbench_relation", "关联关系", "取消所选记录的关联。"
    ),
    "withdraw-link": _semantic(
        "workbench.relation.withdraw", "撤回关联", "workbench_relation", "关联关系", "撤回已确认的关联关系。"
    ),
    "confirm-link/preview": _semantic(
        "workbench.relation.confirm_preview",
        "预览确认关联",
        "workbench_relation",
        "关联关系",
        "预览所选 OA、流水和发票的关联结果。",
    ),
    "withdraw-link/preview": _semantic(
        "workbench.relation.withdraw_preview",
        "预览撤回关联",
        "workbench_relation",
        "关联关系",
        "预览撤回已确认关联的影响。",
    ),
    "mark-exception": _semantic(
        "workbench.exception.mark", "标记异常", "workbench_exception", "关联异常", "将所选记录标记为异常。"
    ),
    "update-bank-exception": _semantic(
        "workbench.exception.update_bank", "更新流水异常", "workbench_exception", "关联异常", "更新银行流水的异常分类。"
    ),
    "oa-bank-exception": _semantic(
        "workbench.exception.review",
        "审阅金额异常",
        "workbench_exception",
        "关联异常",
        "审阅 OA 与流水金额异常并记录人工判断。",
    ),
    "confirm-personal-advance-repayment": _semantic(
        "workbench.advance.confirm",
        "确认个人垫款还款",
        "workbench_relation",
        "关联关系",
        "确认个人垫款与还款流水的关联。",
    ),
    "cancel-exception": _semantic(
        "workbench.exception.cancel", "取消异常处理", "workbench_exception", "关联异常", "取消所选记录的异常处理结果。"
    ),
    "ignore-row": _semantic(
        "workbench.row.ignore", "忽略记录", "workbench_record", "关联台记录", "将所选记录从当前匹配范围中忽略。"
    ),
    "unignore-row": _semantic(
        "workbench.row.unignore", "恢复记录", "workbench_record", "关联台记录", "将已忽略记录恢复到匹配范围。"
    ),
    "confirm-cash-pass-through": _semantic(
        "workbench.cash.confirm_pass_through", "确认现金过账", "workbench_relation", "现金处理", "确认现金过账关系。"
    ),
    "confirm-cash-ticket-purchase": _semantic(
        "workbench.cash.confirm_ticket", "确认现金买票", "workbench_relation", "现金处理", "确认现金买票关系与成本。"
    ),
    "cancel-cash-special": _semantic(
        "workbench.cash.cancel", "取消现金处理", "workbench_relation", "现金处理", "取消已确认的现金特殊处理。"
    ),
}


_DYNAMIC_RULES = (
    _RouteRule(
        "DELETE",
        "/api/workbench/oa-invoice-supplements/documents/",
        _semantic(
            "workbench.oa_invoice.document_delete",
            "删除 OA 补充凭证",
            "oa_supporting_document",
            "OA 补充凭证",
            "删除指定 OA 子付款项的补充凭证。",
        ),
    ),
    _RouteRule(
        "POST",
        "/api/bank-details/transactions/",
        _semantic(
            "bank.transactions.assign_category",
            "标记流水分类",
            "bank_transaction",
            "银行流水",
            "为一条银行流水设置人工分类。",
        ),
        "/category-assignment",
    ),
    _RouteRule(
        "DELETE",
        "/api/bank-details/transactions/",
        _semantic(
            "bank.transactions.clear_category",
            "撤销流水分类",
            "bank_transaction",
            "银行流水",
            "撤销一条银行流水的人工分类。",
        ),
        "/category-assignment",
    ),
    _RouteRule(
        "POST",
        "/api/bank-details/transactions/",
        _semantic(
            "bank.transactions.confirm_category",
            "确认流水分类",
            "bank_transaction",
            "银行流水",
            "确认一条银行流水的分类结果。",
        ),
        "/category-confirmation",
    ),
    _RouteRule(
        "DELETE",
        "/api/bank-details/transactions/",
        _semantic(
            "bank.transactions.revoke_category",
            "撤销分类确认",
            "bank_transaction",
            "银行流水",
            "撤销一条银行流水的分类确认。",
        ),
        "/category-confirmation",
    ),
    _RouteRule(
        "PUT",
        "/api/pending-invoices/rows/",
        _semantic(
            "pending_invoices.income_status.update",
            "更新收入状态",
            "bank_transaction",
            "收入流水",
            "更新一条收入流水的开票状态。",
        ),
        "/income-status",
    ),
    _RouteRule(
        "POST",
        "/api/pending-invoices/rows/",
        _semantic(
            "pending_invoices.attach.preview",
            "预览发票关联",
            "invoice_relation",
            "发票关联",
            "预览一条记录与已有发票的关联结果。",
        ),
        "/attach-existing-invoice/preview",
    ),
    _RouteRule(
        "POST",
        "/api/pending-invoices/rows/",
        _semantic(
            "pending_invoices.attach", "关联已有发票", "invoice_relation", "发票关联", "将收入流水关联到已有发票。"
        ),
        "/attach-existing-invoice",
    ),
    _RouteRule(
        "POST",
        "/api/input-invoice-usage/oa-reverse/batches/",
        _semantic(
            "input_invoice.oa_draft.revoke",
            "撤销 OA 草稿",
            "oa_draft",
            "OA 草稿",
            "撤销反提批次的 OA 草稿。",
        ),
        "/oa-draft/revoke",
    ),
    _RouteRule(
        "POST",
        "/api/input-invoice-usage/oa-reverse/batches/",
        _semantic(
            "input_invoice.oa_status.refresh",
            "刷新 OA 状态",
            "oa_draft",
            "OA 草稿",
            "刷新反提批次的 OA 流程状态。",
        ),
        "/oa-status/refresh",
    ),
    _RouteRule(
        "POST",
        "/api/input-invoice-usage/oa-reverse/batches/",
        _semantic(
            "input_invoice.oa_status.update",
            "更新 OA 状态",
            "oa_draft",
            "OA 草稿",
            "人工更新反提批次的 OA 流程状态。",
        ),
        "/manual-oa-status",
    ),
    _RouteRule(
        "POST",
        "/api/input-invoice-usage/oa-reverse/batches/",
        _semantic(
            "input_invoice.oa_draft.update",
            "更新 OA 草稿",
            "oa_draft",
            "OA 草稿",
            "更新反提批次的 OA 草稿。",
        ),
        "/oa-draft",
    ),
    _RouteRule(
        "POST",
        "/api/no-oa-bank-batches/",
        _semantic("no_oa_batch.submit", "提交免 OA 批次", "bank_batch", "免 OA 流水批次", "提交免 OA 流水批次。"),
        "/submit",
    ),
    _RouteRule(
        "POST",
        "/api/no-oa-bank-batches/",
        _semantic(
            "no_oa_batch.withdraw", "撤回免 OA 批次", "bank_batch", "免 OA 流水批次", "撤回已提交的免 OA 流水批次。"
        ),
        "/withdraw",
    ),
    _RouteRule(
        "POST",
        "/api/bank-flow-rule-batches/",
        _semantic("bank_flow_batch.submit", "提交流水规则批次", "bank_batch", "流水规则批次", "提交银行流水规则批次。"),
        "/submit",
    ),
    _RouteRule(
        "POST",
        "/api/bank-flow-rule-batches/",
        _semantic(
            "bank_flow_batch.withdraw",
            "撤回流水规则批次",
            "bank_batch",
            "流水规则批次",
            "撤回已提交的银行流水规则批次。",
        ),
        "/withdraw",
    ),
    _RouteRule(
        "POST",
        "/api/batch-accounting/",
        _semantic(
            "batch_accounting.withdraw",
            "撤回批量账务",
            "accounting_relation",
            "批量账务关系",
            "撤回已提交的批量账务关系。",
        ),
        "/withdraw",
    ),
    _RouteRule(
        "PUT",
        "/api/turnover-ledger/relations/",
        _semantic(
            "turnover.relation.update",
            "更新往来关系",
            "turnover_relation",
            "往来关系",
            "更新外部往来款关系的补充信息。",
        ),
        "/extra",
    ),
    _RouteRule(
        "POST",
        "/api/turnover-ledger/relations/",
        _semantic(
            "turnover.relation.withdraw",
            "撤回往来关系",
            "turnover_relation",
            "往来关系",
            "撤回已确认的外部往来款关系。",
        ),
        "/withdraw",
    ),
    _RouteRule(
        "POST",
        "/api/background-jobs/",
        _semantic(
            "background_job.acknowledge", "确认后台任务结果", "background_job", "后台任务", "确认后台任务的处理结果。"
        ),
        "/acknowledge",
    ),
    _RouteRule(
        "POST",
        "/api/background-jobs/",
        _semantic("background_job.retry", "重试后台任务", "background_job", "后台任务", "重新执行失败的后台任务。"),
        "/retry",
    ),
    _RouteRule(
        "DELETE",
        "/api/workbench/settings/oa/manual-imports/",
        _semantic(
            "settings.oa.manual_import.delete",
            "删除 OA 手工导入",
            "oa_record",
            "OA 手工导入",
            "删除一条 OA 手工导入记录。",
        ),
    ),
    _RouteRule(
        "PUT",
        "/api/workbench/settings/oa-draft-prefill/",
        _semantic(
            "settings.oa_prefill.update",
            "保存 OA 预填规则",
            "application_setting",
            "OA 预填规则",
            "更新 OA 草稿预填规则。",
        ),
    ),
    _RouteRule(
        "PUT",
        "/api/workbench/settings/oa-applicant-credentials/",
        _semantic(
            "settings.oa_credential.save",
            "保存 OA 申请人凭据",
            "oa_credential",
            "OA 申请人凭据",
            "保存一名 OA 申请人的访问凭据。",
        ),
    ),
    _RouteRule(
        "DELETE",
        "/api/workbench/settings/oa-applicant-credentials/",
        _semantic(
            "settings.oa_credential.delete",
            "删除 OA 申请人凭据",
            "oa_credential",
            "OA 申请人凭据",
            "删除一名 OA 申请人的访问凭据。",
        ),
    ),
    _RouteRule(
        "DELETE",
        "/api/workbench/settings/projects/",
        _semantic(
            "settings.projects.delete",
            "删除项目",
            "project",
            "项目",
            "删除一个项目。",
        ),
    ),
    _RouteRule(
        "POST",
        "/api/etc/reconciliation-tasks/",
        _semantic(
            "etc.task.confirm",
            "确认 ETC 对账",
            "etc_reconciliation_task",
            "ETC 对账任务",
            "确认 ETC 对账任务。",
        ),
        "/confirm",
    ),
    _RouteRule(
        "POST",
        "/api/etc/reconciliation-tasks/",
        _semantic(
            "etc.task.reopen",
            "重新打开 ETC 对账",
            "etc_reconciliation_task",
            "ETC 对账任务",
            "重新打开 ETC 对账任务。",
        ),
        "/reopen",
    ),
    _RouteRule(
        "POST",
        "/api/etc/reconciliation-tasks/",
        _semantic(
            "etc.task.refresh_matches",
            "刷新 ETC 匹配",
            "etc_reconciliation_task",
            "ETC 对账任务",
            "重新计算 ETC 对账匹配结果。",
        ),
        "/refresh-matches",
    ),
    _RouteRule(
        "POST",
        "/api/etc/reconciliation-tasks/",
        _semantic(
            "etc.task.update",
            "更新 ETC 对账任务",
            "etc_reconciliation_task",
            "ETC 对账任务",
            "更新 ETC 票据对账任务及其凭证。",
        ),
    ),
    _RouteRule(
        "PATCH",
        "/api/etc/reconciliation-tasks/",
        _semantic(
            "etc.task.review_item",
            "审阅 ETC 对账项",
            "etc_reconciliation_item",
            "ETC 对账项",
            "更新 ETC 对账项的人工审阅结果。",
        ),
    ),
    _RouteRule(
        "DELETE",
        "/api/etc/reconciliation-tasks/",
        _semantic(
            "etc.task.delete",
            "删除 ETC 对账数据",
            "etc_reconciliation_task",
            "ETC 对账任务",
            "删除 ETC 对账任务中的指定数据。",
        ),
    ),
    _RouteRule(
        "PATCH",
        "/api/etc/business-batches/",
        _semantic(
            "etc.business_batch.update",
            "更新 ETC 业务批次",
            "etc_business_batch",
            "ETC 业务批次",
            "更新 ETC 业务批次信息。",
        ),
    ),
    _RouteRule(
        "DELETE",
        "/api/etc/business-batches/",
        _semantic(
            "etc.business_batch.delete",
            "删除 ETC 业务批次",
            "etc_business_batch",
            "ETC 业务批次",
            "删除一个 ETC 业务批次。",
        ),
    ),
    _RouteRule(
        "POST",
        "/api/etc/business-batches/",
        _semantic(
            "etc.business_batch.update",
            "更新 ETC 业务批次",
            "etc_business_batch",
            "ETC 业务批次",
            "更新 ETC 业务批次的文件、发票或 OA 状态。",
        ),
    ),
)


_PAGE_FALLBACKS = {
    "reconciliation-workbench": ("workbench_record", "关联台记录", "关联台"),
    "bank-details": ("bank_transaction", "银行流水", "银行明细"),
    "pending-invoices": ("pending_invoice", "待找发票记录", "待找发票"),
    "input-invoice-usage": ("input_invoice", "进项发票", "进项发票使用情况"),
    "oa-pending-payments": ("oa_payment", "OA 付款项", "OA 待付款核对"),
    "turnover-ledger": ("turnover_relation", "往来关系", "外部往来款管理"),
    "etc-tickets": ("etc_reconciliation_task", "ETC 对账任务", "ETC 票据管理"),
    "settings": ("application_setting", "App 设置", "设置"),
    "imports.bank-transactions": ("bank_import", "流水导入", "银行流水导入"),
    "imports.invoices": ("invoice_import", "发票导入", "发票导入"),
    "imports.etc-invoices": ("etc_import", "ETC 发票导入", "ETC 发票导入"),
}


def operation_semantics(method: str, route_path: str, *, page_key: str = "") -> OperationSemantics:
    normalized_method = str(method or "").upper()
    normalized_path = str(route_path or "").strip()
    exact = _EXACT_ROUTES.get((normalized_method, normalized_path))
    if exact is not None:
        return exact
    action_prefix = "/api/workbench/actions/"
    if normalized_method == "POST" and normalized_path.startswith(action_prefix):
        action_name = normalized_path.removeprefix(action_prefix)
        matched = _WORKBENCH_ACTIONS.get(action_name)
        if matched is not None:
            return matched
    if normalized_method == "POST" and normalized_path == "/api/workbench/exception/apply":
        return _semantic(
            "workbench.exception.apply", "提交异常处理", "workbench_exception", "关联异常", "提交关联台异常处理结果。"
        )
    if normalized_method == "POST" and normalized_path == "/api/workbench/exception/preview":
        return _semantic(
            "workbench.exception.preview",
            "预览异常处理",
            "workbench_exception",
            "关联异常",
            "预览所选记录的异常处理结果。",
        )
    if normalized_method == "POST" and normalized_path == "/api/workbench/exceptions/review":
        return _semantic(
            "workbench.exception.review",
            "审阅关联异常",
            "workbench_exception",
            "关联异常",
            "记录系统识别关联异常的审阅与分区决定。",
        )
    for rule in _DYNAMIC_RULES:
        if rule.matches(normalized_method, normalized_path):
            return rule.semantics
    object_type, object_label, page_label = _PAGE_FALLBACKS.get(
        page_key,
        ("business_record", "业务记录", "当前页面"),
    )
    verb = "删除" if normalized_method == "DELETE" else "更新"
    return _semantic(
        f"{page_key or 'application'}.operation",
        f"{verb}{object_label}",
        object_type,
        object_label,
        f"在{page_label}中提交了一项数据变更。历史记录未保存更细的业务明细。",
    )


def semantics_from_audit_row(row: dict[str, Any]) -> OperationSemantics:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    stored_code = str(metadata.get("action_code") or "").strip()
    stored_label = str(metadata.get("action_label") or "").strip()
    stored_object_label = str(metadata.get("object_label") or "").strip()
    stored_description = str(metadata.get("description") or "").strip()
    if stored_code and stored_label and stored_object_label:
        return OperationSemantics(
            stored_code,
            stored_label,
            str(row.get("object_type") or "business_record"),
            stored_object_label,
            stored_description or stored_label,
        )
    action = str(row.get("action") or "").strip()
    method, separator, route_path = action.partition(" ")
    if separator and method in {"POST", "PUT", "PATCH", "DELETE"} and route_path.startswith("/"):
        return operation_semantics(method, route_path, page_key=str(row.get("page_key") or ""))
    summary = str(payload.get("summary") or "").strip()
    fallback = operation_semantics("POST", "", page_key=str(row.get("page_key") or ""))
    if (
        summary
        and not summary.startswith(("GET /", "POST /", "PUT /", "PATCH /", "DELETE /"))
        and summary != "业务操作"
    ):
        return OperationSemantics(
            action or fallback.action_code,
            summary,
            str(row.get("object_type") or fallback.object_type),
            stored_object_label or fallback.object_label,
            stored_description or summary,
        )
    return fallback
