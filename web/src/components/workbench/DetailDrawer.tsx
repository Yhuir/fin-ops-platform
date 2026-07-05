import { useEffect, type ReactNode } from "react";

import BankAccountValue from "../BankAccountValue";
import AppDrawer from "../common/AppDrawer";
import DirectionTag from "../DirectionTag";
import type { WorkbenchDetailField, WorkbenchRecord } from "../../features/workbench/types";
import { workbenchColumns } from "../../features/workbench/tableConfig";

type DetailDrawerProps = {
  row: WorkbenchRecord | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

const drawerTitles: Record<WorkbenchRecord["recordType"], string> = {
  oa: "OA详情",
  bank: "银行流水详情",
  invoice: "发票详情",
};

type DetailTableSection = {
  title: string;
  fields: Array<{
    label: string;
    value: ReactNode;
  }>;
};

export default function DetailDrawer({ row, loading, error, onClose }: DetailDrawerProps) {
  useEffect(() => {
    if (!row) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [row, onClose]);

  const open = Boolean(row);
  const title = row ? drawerTitles[row.recordType] : "详情";
  const sections = row ? detailTableSections(row, loading, error) : [];

  return (
    <AppDrawer
      className="workbench-detail-drawer"
      closeLabel="关闭详情抽屉"
      open={open}
      subtitle={row?.status}
      title={title}
      width="min(720px, 100vw)"
      onClose={onClose}
    >
      <div className="workbench-detail-drawer__body">
        {loading ? <div className="workbench-detail-state">正在加载详情...</div> : null}
        {error ? <div className="workbench-detail-state workbench-detail-state--error">{error}</div> : null}
        <DetailTable sections={sections} title={title} />
      </div>
    </AppDrawer>
  );
}

function detailTableSections(row: WorkbenchRecord, loading: boolean, error: string | null): DetailTableSection[] {
  const summaryFields = [
    { label: "记录类型", value: row.label },
    { label: "当前状态", value: row.status },
    ...workbenchColumns[row.recordType].map((column) => ({
      label: column.label,
      value: renderSummaryValue(row, column.key),
    })),
  ];
  const detailFields = visibleDetailFields(row.detailFields).map((field) => ({
    label: field.label,
    value: renderDetailFieldValue(field.label, field.value),
  }));

  return [
    { title: "主表字段", fields: summaryFields },
    {
      title: "详情字段",
      fields: detailFields.length > 0
        ? detailFields
        : [{ label: "详情状态", value: loading ? "详情加载中" : error ? "详情加载失败" : "暂无更多详情" }],
    },
  ];
}

function DetailTable({ sections, title }: { sections: DetailTableSection[]; title: string }) {
  return (
    <div className="workbench-detail-table-shell">
      <table aria-label={`${title}明细表`} className="workbench-detail-table">
        <tbody>
          {sections.map((section) => (
            <TableSection key={section.title} section={section} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TableSection({ section }: { section: DetailTableSection }) {
  return (
    <>
      <tr className="workbench-detail-table__section-row">
        <th colSpan={2} scope="colgroup">{section.title}</th>
      </tr>
      {section.fields.map((field) => (
        <tr key={`${section.title}-${field.label}`}>
          <th scope="row">{field.label}</th>
          <td>{field.value}</td>
        </tr>
      ))}
    </>
  );
}

function renderSummaryValue(row: WorkbenchRecord, key: string): ReactNode {
  const value = row.tableValues[key] ?? "--";
  if (row.recordType === "bank" && key === "amount") {
    const direction = resolveDirectionForMoneyCell(row.tableValues.direction ?? "", value);
    const hasValue = value !== "--" && value !== "—" && value !== "";
    const paymentAccount = row.tableValues.paymentAccount ?? "";
    const shouldShowAccount = hasValue && paymentAccount !== "--" && paymentAccount !== "—" && paymentAccount !== "";
    return (
      <span className="money-cell-stack money-detail-stack">
        <span className="money-detail-value">
          <span>{hasValue ? value : "--"}</span>
        </span>
        {(Boolean(hasValue && direction) || shouldShowAccount) ? (
          <span className="money-cell-meta-row">
            {hasValue && direction ? <DirectionTag direction={direction} /> : null}
            {shouldShowAccount ? (
              <span className="money-cell-account">
                <BankAccountValue value={paymentAccount} variant="tag" />
              </span>
            ) : null}
          </span>
        ) : null}
      </span>
    );
  }
  return value;
}

function visibleDetailFields(fields: WorkbenchDetailField[]) {
  return fields.filter((field) => isVisibleDetailField(field.label, field.value));
}

function isVisibleDetailField(label: string, value: string) {
  const trimmedLabel = label.trim();
  if (!trimmedLabel) {
    return false;
  }
  if (/[A-Za-z_]/.test(trimmedLabel)) {
    return false;
  }
  if (
    /Mongo|文档ID|流程.*ID|实例ID|请求ID|内部|UUID|Key|记录编号|付款项ID|附件.*识别情况|附件.*闭环状态|账户明细编号|企业流水号|交易流水号/.test(
      trimmedLabel,
    )
  ) {
    return false;
  }
  if (/^\s*(?:已解析\s*)?\d+\s*[-/]\s*\d+\s*$/.test(value)) {
    return false;
  }
  if (/付款(?:凭证)?金额与附件发票金额一致/.test(value)) {
    return false;
  }
  return !looksLikeInternalId(value);
}

function looksLikeInternalId(value: string) {
  const text = value.trim();
  if (!text || text === "--" || text === "—") {
    return false;
  }
  return /^[0-9a-f]{24}$/i.test(text)
    || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(text)
    || /^OA[A-Za-z]+\d+$/i.test(text)
    || /^(?:oa|bk|iv|case)-/i.test(text)
    || /^(?:det|corp|vch)-/i.test(text);
}

function renderDetailFieldValue(label: string, value: string): ReactNode {
  if (label === "支付账户" || label === "收款账户") {
    return <BankAccountValue value={value} variant="tag" />;
  }
  return formatDetailValue(value);
}

function formatDetailValue(value: string) {
  const text = value.trim();
  if (!text || text === "--" || text === "—") {
    return "-";
  }
  return text.replace(/\s*[（(][0-9a-f]{16,}\.(?:png|jpg|jpeg|pdf)[）)]/gi, "");
}

function resolveDirectionForMoneyCell(direction: string, value: string) {
  const hasValue = value !== "--" && value !== "—" && value !== "";
  if (!hasValue) {
    return null;
  }
  if (direction === "支出" || direction === "收入") {
    return direction;
  }
  return null;
}
