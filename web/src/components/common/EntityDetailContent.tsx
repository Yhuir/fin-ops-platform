import { Chip, Tabs } from "@heroui/react";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { formatDateTimeText } from "../../features/dateTime";
import StatePanel from "./StatePanel";

export type EntityDetailField = {
  label: string;
  value: string | number | boolean | null | undefined;
};

export type EntityDetailSection = {
  title: string;
  fields: EntityDetailField[];
  bank_transaction_id?: string;
  document_id?: string;
  document_title?: string;
  document_kind?: "oa" | "bank" | "invoice";
};

type EntityDetailContentProps = {
  detailAvailable?: boolean;
  emptyMessage?: string;
  error?: string | null;
  loading?: boolean;
  loadingLabel?: string;
  sections: EntityDetailSection[];
  unavailableReason?: string;
  initialDocumentKey?: string;
  beforeDocumentChange?: () => boolean;
  extraFields?: (section: EntityDetailSection, index: number) => Array<{ label: string; content: ReactNode }>;
};

const publicLabelAliases: Record<string, string> = {
  资金方向: "收支方向",
  account_name: "账户名称",
  account_no: "账号",
  account_number: "账号",
  account_last4: "账号后四位",
  account_detail_no: "账户明细编号-交易流水号",
  amount: "金额",
  application_date: "申请日期",
  application_time: "申请时间",
  application_type: "申请类型",
  applicant: "申请人",
  balance: "余额",
  bank_account: "银行账户",
  bank_account_no: "账号",
  bank_name: "银行",
  bank_short_name: "银行简称",
  bank_serial_no: "银行流水号",
  booked_date: "入账日期",
  buyer_name: "购买方名称",
  buyer_tax_no: "购买方识别号",
  counterparty_account_no: "对方账号",
  counterparty_bank_name: "对方开户机构",
  counterparty_name: "对方户名",
  credit_amount: "收入金额",
  debit_amount: "支出金额",
  digital_invoice_no: "数电发票号码",
  enterprise_serial_no: "企业流水号",
  form_no: "业务单号",
  invoice_code: "发票代码",
  invoice_date: "开票日期",
  invoice_kind: "发票票种",
  invoice_no: "发票号码",
  invoice_source: "发票来源",
  invoice_status: "发票状态",
  invoice_status_from_source: "发票状态",
  invoice_type: "发票种类",
  issue_date: "开票日期",
  completed_at: "审批完成时间",
  completion_time: "审批完成时间",
  expense_content: "费用内容",
  expense_date: "报销日期",
  expense_description: "费用说明",
  expense_type: "费用类型",
  payee_account_no: "收款账号",
  payee_bank_name: "收款开户行",
  payee_name: "收款方",
  payment_method: "支付方式",
  project_name: "项目名称",
  reason: "事由",
  remark: "备注",
  seller_name: "销方名称",
  seller_tax_no: "销方识别号",
  statement_serial_no: "银行流水号",
  status: "状态",
  summary: "摘要",
  tax_amount: "税额",
  tax_classification_code: "税收分类编码",
  tax_rate: "税率",
  taxable_item_name: "货物或应税劳务名称",
  total_amount: "金额",
  total_with_tax: "价税合计",
  trade_time: "交易时间",
  txn_date: "交易日期",
  voucher_no: "凭证号",
  voucher_type: "凭证类型",
  voucher_kind: "凭证种类",
  amount_without_tax: "不含税金额",
  is_positive_invoice: "是否正数发票",
  risk_level: "发票风险等级",
  specific_business_type: "特定业务类型",
  issuer: "开票人",
  workflow_no: "OA单号",
  workflow_status: "流程状态",
  open_url: "打开链接",
  url: "打开链接",
};

const publicLabels = new Set([
  ...Object.values(publicLabelAliases),
  "申请人",
  "OA申请人",
  "申请类型",
  "类型",
  "OA类型",
  "报销/支付",
  "OA单号",
  "流程状态",
  "状态",
  "项目名称",
  "项目",
  "申请时间",
  "申请日期",
  "完成时间",
  "金额",
  "事由",
  "申请事由",
  "往来方",
  "对方户名",
  "对方账号",
  "对方开户机构",
  "账户明细编号-交易流水号",
  "企业流水号",
  "凭证种类",
  "凭证类型",
  "凭证号",
  "支出银行",
  "支付银行",
  "银行",
  "银行简称",
  "开户行",
  "开户行账号",
  "银行账户",
  "账户名称",
  "账号",
  "账号后四位",
  "支付账号",
  "支付账号后四位",
  "付款方式",
  "交易时间",
  "交易日期",
  "入账日期",
  "记账日期",
  "借方发生额",
  "贷方发生额",
  "支出金额",
  "收入金额",
  "余额",
  "收支方向",
  "摘要",
  "备注",
  "发票号码",
  "发票代码",
  "发票方",
  "数电发票号码",
  "开票日期",
  "销方名称",
  "销方识别号",
  "进项发票方名称",
  "购买方",
  "购买方名称",
  "购买方识别号",
  "购方名称",
  "购方税号",
  "不含税金额",
  "税率",
  "税额",
  "价税合计",
  "税收分类编码",
  "特定业务类型",
  "货物或应税劳务名称",
  "货物或服务",
  "被冲红蓝字发票号码",
  "发票来源",
  "发票票种",
  "发票种类",
  "票据类型",
  "发票状态",
  "是否正数发票",
  "发票风险等级",
  "开票人",
  "规格型号",
  "单位",
  "数量",
  "单价",
  "业务单号",
  "支付方式",
  "支付状态",
  "收款账号",
  "收款开户行",
  "收款方",
  "银行流水号",
  "流水标签",
  "报销金额",
  "费用类型",
  "费用内容",
  "费用说明",
  "报销日期",
  "报销附件",
  "票据张数",
  "附件文件数",
  "审批完成时间",
  "明细摘要",
  "明细数量",
  "明细金额合计",
  "报销日期范围",
  "项目名称汇总",
  "费用类型汇总",
  "费用内容摘要",
  "附件发票摘要",
  "附件发票数量",
  "附件发票识别情况",
  "附件发票金额合计",
  "来源附件文件名",
  "付款凭证数量",
  "付款凭证金额合计",
  "金额差异",
  "OA归集合计",
  "关联付款流水合计",
  "差异",
  "本项净成本",
  "OA 原始金额",
  "OA 金额占比",
  "本笔支出流水原额",
  "OA 原始金额合计",
  "支出流水原额",
  "付错退款",
  "关系净支出",
  "净支出与 OA 差额",
  "净支出 / OA",
  "付错退款金额",
  "打开链接",
]);

const sectionAliases: Record<string, string> = {
  OA信息: "基本信息",
  OA主信息: "基本信息",
  详情字段: "基本信息",
  发票主信息: "基本信息",
  发票情况: "基本信息",
  凭证信息: "交易信息",
  流水信息: "交易信息",
  流水主信息: "交易信息",
  对方与摘要: "对方信息",
  摘要与备注: "附加信息",
  业务与票据: "业务信息",
};

const statusLabels: Record<string, string> = {
  active: "有效",
  completed: "已完成",
  done: "已完成",
  in_progress: "进行中",
  income: "收入",
  inflow: "收入",
  normal: "正常",
  outflow: "支出",
  expense: "支出",
  paired: "已配对",
  unpaired: "未配对",
};

export default function EntityDetailContent({
  detailAvailable = true,
  emptyMessage = "暂无更多详情。",
  error,
  loading = false,
  loadingLabel = "正在加载完整详情",
  sections,
  unavailableReason,
  extraFields,
  initialDocumentKey,
  beforeDocumentChange,
}: EntityDetailContentProps) {
  if (loading) {
    return (
      <div aria-label="正在加载详情">
        <StatePanel compact tone="loading" title={loadingLabel} />
      </div>
    );
  }

  if (error) {
    return <StatePanel compact tone="error">{error}</StatePanel>;
  }

  if (!detailAvailable) {
    return (
      <StatePanel compact tone="info" title="详情暂不可用">
        {unavailableReason ?? "后端未返回可展示的完整详情。"}
      </StatePanel>
    );
  }

  if (sections.length === 0) {
    return <StatePanel compact tone="info">{emptyMessage}</StatePanel>;
  }

  return <DetailDocuments key={`${initialDocumentKey ?? ''}|${sections.map(section => `${section.document_kind}:${section.document_id ?? section.title}`).join('|')}`}
    sections={sections} extraFields={extraFields} initialDocumentKey={initialDocumentKey} beforeDocumentChange={beforeDocumentChange} />;
}

function DetailDocuments({ sections, extraFields, initialDocumentKey, beforeDocumentChange }: Pick<EntityDetailContentProps,
  'sections' | 'extraFields' | 'initialDocumentKey' | 'beforeDocumentChange'>) {
  const root = useRef<HTMLDivElement>(null);
  const documents = new Map<string, { title: string; sections: Array<{ section: EntityDetailSection; index: number }> }>();
  sections.forEach((section, index) => {
    const key = section.document_id ? `${section.document_kind}:${section.document_id}` : 'single';
    if (!documents.has(key)) documents.set(key, { title: section.document_title ?? section.title, sections: [] });
    documents.get(key)!.sections.push({ section, index });
  });
  const entries = [...documents.entries()];
  const [selected, setSelected] = useState(initialDocumentKey ?? entries[0][0]);
  useLayoutEffect(() => {
    const nav = root.current?.querySelector<HTMLElement>('[role="tablist"]');
    if (!nav) return;
    const revealSelected = () => {
      const tab = nav.querySelector<HTMLElement>('[aria-selected="true"]');
      if (!tab) return;
      const bounds = nav.getBoundingClientRect(), item = tab.getBoundingClientRect();
      if (item.left < bounds.left) nav.scrollLeft += item.left - bounds.left;
      else if (item.right > bounds.right) nav.scrollLeft += item.right - bounds.right;
    };
    revealSelected();
    const observer = new ResizeObserver(revealSelected);
    observer.observe(nav);
    return () => observer.disconnect();
  }, [selected]);
  const active = documents.get(selected);
  if (!active) return <StatePanel compact tone="error">所选单据不在当前详情中。</StatePanel>;
  const content = active.sections.map(({section, index: sectionIndex}) => <section className="entity-detail-section" key={sectionIndex}>
    <h3 className="entity-detail-section__title">{section.title}</h3>
    <table className="entity-detail-table" aria-label={`${section.title}详情`}>
      <tbody>{section.fields.map((field, fieldIndex) => <tr key={`${field.label}-${fieldIndex}`}>
        <th scope="row">{field.label}</th><td className={amountLabels.has(field.label) ? 'entity-detail-row__amount' : undefined}>{renderValue(field)}</td>
      </tr>)}</tbody>
    </table>
    {(extraFields?.(section, sectionIndex) ?? []).map(field => <div className="entity-detail-actions" key={field.label}>
      <h4>{field.label}</h4>{field.content}
    </div>)}
  </section>);
  return <div className="entity-detail-content" ref={root}>
    {entries.length > 1 ? <Tabs className="entity-detail-tabs" keyboardActivation="manual" selectedKey={selected} onSelectionChange={key => {
      if (key === selected || beforeDocumentChange?.() === false) return;
      setSelected(String(key));
      const scroll = root.current?.closest('.finance-drawer__body');
      if (scroll) scroll.scrollTop = 0;
    }}>
      <Tabs.List className="entity-detail-index" aria-label="单据导航">
        {entries.map(([key, document], index) => <Tabs.Tab id={key} key={key} className="entity-detail-tab">
          <span className="entity-detail-tab__number">{index + 1}</span><span>{document.title}</span>
        </Tabs.Tab>)}
      </Tabs.List>
      <Tabs.Panel id={selected} key={selected} className="entity-detail-panel">{content}</Tabs.Panel>
    </Tabs> : content}
  </div>;
}

export function preparePublicDetailSections(sections: EntityDetailSection[]): EntityDetailSection[] {
  const prepared: EntityDetailSection[] = [];
  for (const section of sections) {
    const title = publicSectionTitle(section.title);
    if (!title) {
      continue;
    }
    const fields = section.fields
      .map(preparePublicField)
      .filter((field): field is EntityDetailField => field !== null);
    if (fields.length === 0) {
      continue;
    }
    prepared.push({ ...section, title, fields });
  }
  return prepared;
}

function preparePublicField(field: EntityDetailField): EntityDetailField | null {
  const normalized = normalizedLabel(field.label);
  const label = publicLabelAliases[normalized] ?? field.label.trim();
  if (!isPublicLabel(label, normalized) || looksLikeRawData(field.value) || isEmptyValue(field.value)) {
    return null;
  }
  return {
    label,
    value: localizedValue(label, field.value),
  };
}

function isPublicLabel(label: string, normalized: string) {
  if (!label || isInternalLabel(label, normalized)) {
    return false;
  }
  if (publicLabels.has(label) || /^OA\s*\d+$/i.test(label)) {
    return true;
  }
  return false;
}

function isInternalLabel(label: string, normalized: string) {
  return normalized === "id"
    || normalized.endsWith("_id")
    || normalized.startsWith("id_")
    || normalized.includes("relation_case")
    || normalized.includes("case_id")
    || normalized.includes("mongo")
    || normalized.includes("uuid")
    || normalized.includes("source_batch")
    || normalized.includes("raw")
    || /\bID\b/i.test(label)
    || /内部|原始字段|文档ID|实例ID|请求ID|记录编号|来源批次|来源链接|关系模式|关系来源|分组字段内容|分组\s*OA\s*信息|分组凭证信息/.test(label);
}

function publicSectionTitle(value: string) {
  const title = value.trim() || "详情";
  if (/原始字段|内部字段|来源链接|关联台证据|raw/i.test(title)) {
    return null;
  }
  return sectionAliases[title] ?? title;
}

function normalizedLabel(label: string) {
  return label
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[：:]/g, "")
    .replace(/[\s/-]+/g, "_")
    .replace(/_+/g, "_")
    .toLowerCase();
}

function localizedValue(label: string, value: EntityDetailField["value"]) {
  if (typeof value !== "string") {
    return value;
  }
  const text = value.trim();
  if (timeFieldLabels.has(label)) {
    const formatted = formatDateTimeText(text);
    if (/^\d{4}-?\d{2}-?\d{2}[T\s]\d{2}:\d{2}(?:Z|[+-]\d{1,2}(?::?\d{2})?)?$/.test(text)) {
      return formatted.replace(/:\d{2}$/, "");
    }
    return formatted;
  }
  return statusFieldLabels.has(label) ? statusLabels[text.toLowerCase()] ?? text : text;
}

function isEmptyValue(value: EntityDetailField["value"]) {
  return value === null || value === undefined || (typeof value === "string" && !value.trim());
}

function looksLikeRawData(value: EntityDetailField["value"]) {
  if (typeof value !== "string") {
    return false;
  }
  const text = value.trim();
  return (text.startsWith("{") || text.startsWith("[")) && (text.includes('\":') || text.includes('\",\"'));
}

const amountLabels = new Set([
  "金额",
  "不含税金额",
  "税额",
  "价税合计",
  "借方发生额",
  "贷方发生额",
  "支出金额",
  "收入金额",
  "余额",
  "单价",
  "明细金额合计",
  "金额差异",
  "OA归集合计",
  "关联付款流水合计",
  "差异",
  "本项净成本",
  "OA 原始金额",
  "本笔支出流水原额",
  "OA 原始金额合计",
  "支出流水原额",
  "付错退款",
  "关系净支出",
  "净支出与 OA 差额",
  "付错退款金额",
]);

function renderValue(field: EntityDetailField): ReactNode {
  const value = formatValue(field.value);
  if (field.label === "打开链接" && typeof field.value === "string" && /^https?:\/\//i.test(field.value)) {
    return <a className="entity-detail-link" href={field.value} rel="noreferrer" target="_blank">打开 OA 详情</a>;
  }
  if (statusFieldLabels.has(field.label) && value !== "—") {
    return (
      <Chip color={chipColor(value)} size="sm" variant="soft">
        <Chip.Label>{value}</Chip.Label>
      </Chip>
    );
  }
  return value;
}

const statusFieldLabels = new Set(["状态", "流程状态", "收支方向", "发票状态", "发票风险等级", "是否正数发票"]);
const timeFieldLabels = new Set([
  "申请时间",
  "完成时间",
  "审批完成时间",
  "交易时间",
  "交易日期",
  "入账日期",
  "记账日期",
  "申请日期",
  "开票日期",
  "报销日期",
]);

function chipColor(value: string) {
  if (/收入|正常|有效|已完成|已配对|金额一致|是/.test(value)) {
    return "success" as const;
  }
  if (/支出|异常|风险|未配对|金额不一致|否/.test(value)) {
    return "warning" as const;
  }
  return "default" as const;
}

function formatValue(value: EntityDetailField["value"]) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return String(value);
}
