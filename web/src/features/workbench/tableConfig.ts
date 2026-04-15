import type { WorkbenchColumnLayouts, WorkbenchRecordType } from "./types";

export type WorkbenchColumnKind = "text" | "money" | "status";

export type WorkbenchColumn = {
  key: string;
  label: string;
  headerLines?: string[];
  kind?: WorkbenchColumnKind;
  className?: string;
  filterable?: boolean;
  track: string;
  minWidth: number;
};

export const workbenchColumns: Record<WorkbenchRecordType, WorkbenchColumn[]> = {
  oa: [
    {
      key: "applicant",
      label: "申请人",
      className: "column-compact column-applicant-compact column-content-centered",
      track: "minmax(112px, 112fr)",
      minWidth: 112,
    },
    {
      key: "projectName",
      label: "项目名称",
      className: "column-compact column-project-compact",
      track: "minmax(192px, 192fr)",
      minWidth: 192,
    },
    {
      key: "amount",
      label: "金额",
      kind: "money",
      className: "column-compact column-money-compact column-money-centered",
      filterable: false,
      track: "minmax(92px, 92fr)",
      minWidth: 92,
    },
    {
      key: "counterparty",
      label: "对方户名",
      className: "column-compact column-counterparty-compact",
      track: "minmax(160px, 160fr)",
      minWidth: 160,
    },
    {
      key: "reason",
      label: "申请事由",
      className: "column-compact column-note-compact",
      filterable: false,
      track: "minmax(168px, 168fr)",
      minWidth: 168,
    },
  ],
  bank: [
    {
      key: "counterparty",
      label: "对方户名",
      className: "column-compact column-counterparty-compact",
      track: "minmax(176px, 176fr)",
      minWidth: 176,
    },
    {
      key: "amount",
      label: "金额",
      kind: "money",
      className: "column-compact column-money-compact column-money-centered",
      track: "minmax(144px, 144fr)",
      minWidth: 144,
    },
    {
      key: "loanRepaymentDate",
      label: "还借款日期",
      className: "column-compact column-date-compact",
      track: "minmax(108px, 108fr)",
      minWidth: 108,
    },
    {
      key: "note",
      label: "备注",
      className: "column-compact column-note-compact",
      filterable: false,
      track: "minmax(168px, 168fr)",
      minWidth: 168,
    },
  ],
  invoice: [
    {
      key: "sellerName",
      label: "销方名称/识别号",
      headerLines: ["销方名称/", "识别号"],
      className: "column-compact column-name-compact",
      track: "minmax(156px, 156fr)",
      minWidth: 156,
    },
    {
      key: "buyerName",
      label: "购方名称/识别号",
      headerLines: ["购方名称/", "识别号"],
      className: "column-compact column-name-compact",
      track: "minmax(156px, 156fr)",
      minWidth: 156,
    },
    {
      key: "issueDate",
      label: "发票代码/发票号码",
      headerLines: ["发票代码 /", "发票号码"],
      className: "column-compact column-invoice-identity-compact",
      filterable: false,
      track: "minmax(124px, 124fr)",
      minWidth: 124,
    },
    {
      key: "amount",
      label: "不含税价格/税率（税额）",
      headerLines: ["不含税价格", "税率（税额）"],
      kind: "money",
      className: "column-compact column-invoice-amount-compact column-money-centered",
      filterable: false,
      track: "minmax(108px, 108fr)",
      minWidth: 108,
    },
    {
      key: "grossAmount",
      label: "价税合计",
      kind: "money",
      className: "column-compact column-invoice-gross-compact column-money-centered",
      filterable: false,
      track: "minmax(84px, 84fr)",
      minWidth: 84,
    },
  ],
};

export const defaultWorkbenchColumnLayouts: WorkbenchColumnLayouts = {
  oa: workbenchColumns.oa.map((column) => column.key),
  bank: workbenchColumns.bank.map((column) => column.key),
  invoice: workbenchColumns.invoice.map((column) => column.key),
};

export function getWorkbenchColumns(
  paneId: WorkbenchRecordType,
  layouts?: Partial<WorkbenchColumnLayouts> | null,
) {
  const columns = workbenchColumns[paneId];
  const requestedOrder = layouts?.[paneId];

  if (!requestedOrder?.length) {
    return columns;
  }

  const columnByKey = new Map(columns.map((column) => [column.key, column]));
  const ordered: WorkbenchColumn[] = [];
  const seen = new Set<string>();

  requestedOrder.forEach((key) => {
    const column = columnByKey.get(key);
    if (!column || seen.has(key)) {
      return;
    }
    ordered.push(column);
    seen.add(key);
  });

  columns.forEach((column) => {
    if (!seen.has(column.key)) {
      ordered.push(column);
    }
  });

  return ordered;
}

const ACTION_COLUMN_WIDTHS: Record<WorkbenchRecordType, { track: string; minWidth: number }> = {
  oa: { track: "minmax(168px, 168fr)", minWidth: 168 },
  bank: { track: "minmax(168px, 168fr)", minWidth: 168 },
  invoice: { track: "minmax(92px, 92fr)", minWidth: 92 },
};

export function getWorkbenchPaneGridStyle(
  paneId: WorkbenchRecordType,
  layouts?: Partial<WorkbenchColumnLayouts> | null,
  includeActionColumn = false,
) {
  const columns = getWorkbenchColumns(paneId, layouts);
  const tracks = columns.map((column) => column.track);
  let minWidth = columns.reduce((sum, column) => sum + column.minWidth, 0);

  if (includeActionColumn) {
    tracks.push(ACTION_COLUMN_WIDTHS[paneId].track);
    minWidth += ACTION_COLUMN_WIDTHS[paneId].minWidth;
  }

  return {
    gridTemplateColumns: tracks.join(" "),
    minWidth: `${minWidth}px`,
  };
}
