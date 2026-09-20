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
      track: "minmax(112px, 0.8fr)",
      minWidth: 112,
    },
    {
      key: "projectName",
      label: "项目名称",
      className: "column-compact column-project-compact",
      track: "minmax(128px, 1.25fr)",
      minWidth: 128,
    },
    {
      key: "amount",
      label: "金额",
      kind: "money",
      className: "column-compact column-money-compact column-money-centered",
      filterable: false,
      track: "minmax(80px, 0.72fr)",
      minWidth: 80,
    },
    {
      key: "counterparty",
      label: "对方户名",
      className: "column-compact column-counterparty-compact",
      track: "minmax(112px, 1fr)",
      minWidth: 112,
    },
    {
      key: "reason",
      label: "申请事由",
      className: "column-compact column-note-compact",
      filterable: false,
      track: "minmax(128px, 1.1fr)",
      minWidth: 128,
    },
  ],
  bank: [
    {
      key: "counterparty",
      label: "对方户名",
      className: "column-compact column-counterparty-compact",
      track: "minmax(0, 1.45fr)",
      minWidth: 0,
    },
    {
      key: "amount",
      label: "金额",
      kind: "money",
      className: "column-compact column-money-compact column-money-centered",
      track: "minmax(0, 1fr)",
      minWidth: 0,
    },
    {
      key: "loanRepaymentDate",
      label: "还借款日期",
      className: "column-compact column-date-compact",
      track: "minmax(0, 1fr)",
      minWidth: 0,
    },
    {
      key: "note",
      label: "备注",
      className: "column-compact column-note-compact",
      filterable: false,
      track: "minmax(0, 1.35fr)",
      minWidth: 0,
    },
  ],
  invoice: [
    {
      key: "sellerName",
      label: "销方名称/识别号",
      headerLines: ["销方名称/", "识别号"],
      className: "column-compact column-name-compact",
      track: "minmax(0, 1.35fr)",
      minWidth: 0,
    },
    {
      key: "buyerName",
      label: "购方名称/识别号",
      headerLines: ["购方名称/", "识别号"],
      className: "column-compact column-name-compact",
      track: "minmax(0, 1.15fr)",
      minWidth: 0,
    },
    {
      key: "issueDate",
      label: "发票号码",
      headerLines: ["发票号码"],
      className: "column-compact column-invoice-identity-compact",
      filterable: false,
      track: "minmax(0, 1.05fr)",
      minWidth: 0,
    },
    {
      key: "grossAmount",
      label: "价税合计",
      headerLines: ["价税合计", "不含税价格 税率（税额）"],
      kind: "money",
      className: "column-compact column-invoice-gross-compact column-money-centered",
      filterable: false,
      track: "minmax(0, 1.05fr)",
      minWidth: 0,
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
  const columns = paneId === "bank"
    ? workbenchColumns[paneId].filter((column) => column.key !== "loanRepaymentDate")
    : workbenchColumns[paneId];
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

export function getWorkbenchPaneGridStyle(
  paneId: WorkbenchRecordType,
  layouts?: Partial<WorkbenchColumnLayouts> | null,
) {
  const columns = getWorkbenchColumns(paneId, layouts);

  return {
    gridTemplateColumns: columns.map((column) => column.track).join(" "),
    minWidth: `${columns.reduce((total, column) => total + column.minWidth, 0)}px`,
  };
}
