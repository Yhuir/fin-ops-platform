import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { GlobalOperationOverlayProvider } from "../contexts/GlobalOperationOverlayContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";
import TurnoverLedgerPage from "../pages/TurnoverLedgerPage";

const turnoverLedgerSourceFiles = [
  "src/pages/TurnoverLedgerPage.tsx",
  "src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx",
  "src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx",
  "src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx",
] as const;

const fullSession: SessionPayload = {
  allowed: true,
  user: {
    userId: "1",
    username: "TESTFULL001",
    nickname: "测试全权限",
    displayName: "测试全权限",
    deptId: null,
    deptName: null,
    avatar: null,
  },
  roles: ["fin_ops_user"],
  permissions: ["finops:app:view"],
  accessTier: "full_access",
  canAccessApp: true,
  canMutateData: true,
  canAdminAccess: false,
};

function renderTurnoverLedgerPage(session: SessionPayload = fullSession) {
  const value: SessionContextValue = {
    status: "authenticated",
    session,
    refresh: () => undefined,
  };
  return render(
    <GlobalOperationOverlayProvider>
      <SessionContext.Provider value={value}>
        <PageSessionStateProvider>
          <TurnoverLedgerPage />
        </PageSessionStateProvider>
      </SessionContext.Provider>
    </GlobalOperationOverlayProvider>,
  );
}

function readWebSource(path: string) {
  return readFileSync(resolve(path), "utf8");
}

function cssRule(styles: string, selector: string, containing?: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matches = Array.from(styles.matchAll(new RegExp(`${escapedSelector}\\s*\\{([\\s\\S]*?)\\n\\}`, "gm")));
  const match = containing ? matches.find((candidate) => candidate[1].includes(containing)) : matches.at(-1);
  if (!match) {
    throw new Error(`Missing CSS rule for ${selector}`);
  }
  return match[1];
}

function requestUrls(fetchMock: ReturnType<typeof installTurnoverLedgerFetch>, pathname: string) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === pathname);
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function deferredResponse() {
  let resolve!: (response: Response) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Response>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, reject, resolve };
}

function groupedPayload(family: string, overrides: Record<string, unknown> = {}) {
  const allGroups = [
    {
      group_id: "counterparty:personal:zhangsan",
      counterparty_name: "张三",
      family: "personal",
      family_label: "个人往来",
      pending_direction: "repayment",
      pending_direction_label: "待还款",
      pending_amount: "800.00",
      row_span: 3,
      group_tone: "warning",
      rows: [
        {
          relation_id: "rel-personal-1",
          status: "suggested",
          status_label: "待人工确认",
          row_tone: "warning",
          borrow_amount: "1000.00",
          borrow_date: "2026-05-01",
          borrow_direction: "income",
          repayment_amount: "200.00",
          repayment_date: "2026-05-03",
          repayment_direction: "expense",
          counterparty_bank_name: "建设银行昆明分行",
          repayment_remark: "归还暂借款",
          interest_rate_type: "annual",
          interest_rate_value: "0.060000",
          interest_paid_amount: "10.00",
          loan_days: 2,
          accrued_interest: "0.33",
          interest_paid_date: "2026-05-05",
          interest_payment_method: "转账",
          note: "页面内维护备注",
          bank_row_ids: ["bank-personal-001", "bank-personal-002"],
        },
        {
          relation_id: "rel-personal-1",
          status: "confirmed",
          status_label: "批次明细",
          row_tone: "info",
          borrow_amount: "600.00",
          borrow_date: "2026-05-06",
          borrow_direction: "income",
          repayment_amount: "100.00",
          repayment_date: "2026-05-07",
          repayment_direction: "expense",
          counterparty_bank_name: "招商银行批次账户",
          repayment_remark: "归还借款批次一",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: 1,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "批次一待还",
          bank_row_ids: ["bank-personal-003"],
        },
        {
          relation_id: "rel-personal-1",
          status: "confirmed",
          status_label: "批次明细",
          row_tone: "info",
          borrow_amount: "400.00",
          borrow_date: "2026-05-08",
          borrow_direction: "income",
          repayment_amount: "100.00",
          repayment_date: "2026-05-09",
          repayment_direction: "expense",
          counterparty_bank_name: "工商银行批次账户",
          repayment_remark: "归还借款批次二",
          interest_rate_type: "annual",
          interest_rate_value: "0.060000",
          interest_paid_amount: "0.00",
          loan_days: 1,
          accrued_interest: "0.07",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "批次二待还",
          bank_row_ids: ["bank-personal-004"],
        },
      ],
    },
    {
      group_id: "counterparty:personal:jiaxiaohua",
      counterparty_name: "贾小花",
      family: "personal",
      family_label: "个人往来",
      pending_direction: "closed",
      pending_direction_label: "已闭合",
      pending_amount: "0.00",
      closed_amount: "0.00",
      row_span: 4,
      group_tone: "success",
      summary_row: {
        row_kind: "summary",
        relation_id: "rel-jiaxiaohua",
        status: "confirmed",
        status_label: "已闭合",
        row_tone: "success",
        borrow_amount: "300000.00",
        borrow_date: "2026-02-04",
        borrow_direction: "income",
        repayment_amount: "300000.00",
        repayment_date: "2026-03-04",
        repayment_direction: "expense",
        counterparty_bank_name: "建行通海支行",
        repayment_remark: "总览不应展示的还款备注",
        interest_rate_type: "none",
        interest_rate_value: "0.000000",
        interest_paid_amount: "0.00",
        loan_days: null,
        accrued_interest: "0.00",
        interest_paid_date: null,
        interest_payment_method: "",
        note: "贾小花合计",
        bank_row_ids: ["bank-jia-income-200000", "bank-jia-income-100000", "bank-jia-expense-300000"],
      },
      rows: [
        {
          row_kind: "summary",
          relation_id: "rel-jiaxiaohua",
          status: "confirmed",
          status_label: "已闭合",
          row_tone: "success",
          borrow_amount: "300000.00",
          borrow_date: "2026-02-04",
          borrow_direction: "income",
          repayment_amount: "300000.00",
          repayment_date: "2026-03-04",
          repayment_direction: "expense",
          counterparty_bank_name: "建行通海支行",
          repayment_remark: "总览不应展示的还款备注",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: null,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "贾小花合计",
          bank_row_ids: ["bank-jia-income-200000", "bank-jia-income-100000", "bank-jia-expense-300000"],
        },
      ],
      flow_rows: [
        {
          row_kind: "flow",
          flow_id: "bank:bank-jia-income-200000",
          source_bank_row_id: "bank-jia-income-200000",
          relation_id: "rel-jiaxiaohua",
          status: "confirmed",
          status_label: "流水",
          row_tone: "success",
          category_label: "外部往来款收款 / 借入款 / 个人往来",
          category_label_path: ["外部往来款收款", "借入款", "个人往来"],
          flow_direction: "income",
          flow_amount: "200000.00",
          borrow_amount: "200000.00",
          borrow_date: "2026-02-04 13:20:48",
          borrow_direction: "income",
          repayment_amount: "0.00",
          repayment_date: null,
          repayment_direction: "expense",
          counterparty_bank_name: "建行通海支行",
          bank_account_labels: ["建行 8106"],
          repayment_remark: "个人暂借款：待还款",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: null,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "收入 200000",
          bank_row_ids: ["bank-jia-income-200000"],
        },
        {
          row_kind: "flow",
          flow_id: "bank:bank-jia-income-100000",
          source_bank_row_id: "bank-jia-income-100000",
          relation_id: "rel-jiaxiaohua",
          status: "confirmed",
          status_label: "流水",
          row_tone: "success",
          category_label: "外部往来款收款 / 借入款 / 个人往来",
          category_label_path: ["外部往来款收款", "借入款", "个人往来"],
          flow_direction: "income",
          flow_amount: "100000.00",
          borrow_amount: "100000.00",
          borrow_date: "2026-02-04 17:07:45",
          borrow_direction: "income",
          repayment_amount: "0.00",
          repayment_date: null,
          repayment_direction: "expense",
          counterparty_bank_name: "建行通海支行",
          bank_account_labels: ["建行 8106"],
          repayment_remark: "个人暂借款：待还款",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: null,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "收入 100000",
          bank_row_ids: ["bank-jia-income-100000"],
        },
        {
          row_kind: "flow",
          flow_id: "bank:bank-jia-expense-300000",
          source_bank_row_id: "bank-jia-expense-300000",
          relation_id: "rel-jiaxiaohua",
          status: "confirmed",
          status_label: "流水",
          row_tone: "warning",
          category_label: "外部往来款付款 / 归还借款 / 个人往来",
          category_label_path: ["外部往来款付款", "归还借款", "个人往来"],
          flow_direction: "expense",
          flow_amount: "300000.00",
          borrow_amount: "0.00",
          borrow_date: null,
          borrow_direction: "income",
          repayment_amount: "300000.00",
          repayment_date: "2026-03-04 15:24:58",
          repayment_direction: "expense",
          counterparty_bank_name: "建行通海支行",
          bank_account_labels: ["建行 8106"],
          repayment_remark: "个人暂借款：已还款",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: null,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "支出 300000",
          bank_row_ids: ["bank-jia-expense-300000"],
        },
      ],
      lot_rows: [
        {
          row_kind: "lot",
          relation_id: "rel-jiaxiaohua",
          lot_id: "lot-jia-200000",
          status: "confirmed",
          status_label: "批次明细",
          row_tone: "info",
          borrow_amount: "200000.00",
          borrow_date: "2026-02-04",
          borrow_direction: "income",
          repayment_amount: "200000.00",
          repayment_date: "2026-03-04",
          repayment_direction: "expense",
          counterparty_bank_name: "分摊批次一",
          repayment_remark: "错误展示时会复制还款",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: 28,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "批次 200000",
          bank_row_ids: ["bank-jia-income-200000", "bank-jia-expense-300000"],
        },
        {
          row_kind: "lot",
          relation_id: "rel-jiaxiaohua",
          lot_id: "lot-jia-100000",
          status: "confirmed",
          status_label: "批次明细",
          row_tone: "info",
          borrow_amount: "100000.00",
          borrow_date: "2026-02-04",
          borrow_direction: "income",
          repayment_amount: "100000.00",
          repayment_date: "2026-03-04",
          repayment_direction: "expense",
          counterparty_bank_name: "分摊批次二",
          repayment_remark: "错误展示时会复制还款",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: 28,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "批次 100000",
          bank_row_ids: ["bank-jia-income-100000", "bank-jia-expense-300000"],
        },
      ],
    },
    {
      group_id: "counterparty:company:yunnan",
      counterparty_name: "云南建设有限公司",
      family: "company",
      family_label: "公司往来",
      pending_direction: "collection",
      pending_direction_label: "待收款",
      pending_amount: "2000.00",
      row_span: 5,
      group_tone: "success",
      rows: [
        {
          relation_id: "rel-company-1",
          status: "confirmed",
          status_label: "人工确认",
          row_tone: "success",
          borrow_amount: "3000.00",
          borrow_date: "2026-05-02",
          borrow_direction: "expense",
          repayment_amount: "1000.00",
          repayment_date: "2026-05-04",
          repayment_direction: "income",
          counterparty_bank_name: "中国银行",
          repayment_remark: "回款",
          interest_rate_type: "monthly",
          interest_rate_value: "0.005000",
          interest_paid_amount: "0.00",
          loan_days: 2,
          accrued_interest: "1.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "项目保证金",
          bank_row_ids: ["bank-company-001", "bank-company-002"],
        },
      ],
      flow_rows: [
        {
          row_kind: "flow",
          flow_id: "bank:bank-company-expense-1000",
          source_bank_row_id: "bank-company-expense-1000",
          relation_id: "rel-company-1",
          status: "suggested",
          status_label: "流水",
          row_tone: "warning",
          category_label: "外部往来款付款 / 借出款 / 公司往来",
          category_label_path: ["外部往来款付款", "借出款", "公司往来"],
          flow_direction: "expense",
          flow_amount: "1000.00",
          borrow_amount: "0.00",
          borrow_date: null,
          borrow_direction: "income",
          repayment_amount: "1000.00",
          repayment_date: "2026-05-02 10:00:00",
          repayment_direction: "expense",
          counterparty_bank_name: "中国银行",
          bank_account_labels: ["中行 0001"],
          repayment_remark: "借出保证金",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: null,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "",
          bank_row_ids: ["bank-company-expense-1000"],
        },
        {
          row_kind: "flow",
          flow_id: "bank:bank-company-income-1000",
          source_bank_row_id: "bank-company-income-1000",
          relation_id: "rel-company-1",
          status: "suggested",
          status_label: "流水",
          row_tone: "success",
          category_label: "外部往来款收款 / 收回借款 / 公司往来",
          category_label_path: ["外部往来款收款", "收回借款", "公司往来"],
          flow_direction: "income",
          flow_amount: "1000.00",
          borrow_amount: "1000.00",
          borrow_date: "2026-05-04 10:00:00",
          borrow_direction: "income",
          repayment_amount: "0.00",
          repayment_date: null,
          repayment_direction: "expense",
          counterparty_bank_name: "中国银行",
          bank_account_labels: ["中行 0001"],
          repayment_remark: "收回保证金",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: null,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "",
          bank_row_ids: ["bank-company-income-1000"],
        },
        {
          row_kind: "flow",
          flow_id: "bank:bank-company-borrow-expense-40000",
          source_bank_row_id: "bank-company-borrow-expense-40000",
          relation_id: "rel-company-1",
          status: "suggested",
          status_label: "流水",
          row_tone: "warning",
          category_label: "外部往来款付款 / 保证金 / 业务往来",
          category_label_path: ["外部往来款付款", "保证金", "业务往来"],
          flow_direction: "expense",
          flow_amount: "40000.00",
          borrow_amount: "40000.00",
          borrow_date: "2026-03-11 16:07:35",
          borrow_direction: "expense",
          repayment_amount: "0.00",
          repayment_date: null,
          repayment_direction: "income",
          counterparty_bank_name: "建设银行 8106",
          bank_account_labels: ["建设银行 8106"],
          repayment_remark: "电子转账 / 投标保证金",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: null,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "",
          bank_row_ids: ["bank-company-borrow-expense-40000"],
        },
        {
          row_kind: "flow",
          flow_id: "bank:bank-company-repayment-income-40000",
          source_bank_row_id: "bank-company-repayment-income-40000",
          relation_id: "rel-company-1",
          status: "suggested",
          status_label: "流水",
          row_tone: "success",
          category_label: "外部往来款收款 / 退保证金 / 业务往来",
          category_label_path: ["外部往来款收款", "退保证金", "业务往来"],
          flow_direction: "income",
          flow_amount: "40000.00",
          borrow_amount: "0.00",
          borrow_date: null,
          borrow_direction: "expense",
          repayment_amount: "40000.00",
          repayment_date: "2026-04-03 18:00:16",
          repayment_direction: "income",
          counterparty_bank_name: "建设银行 8106",
          bank_account_labels: ["建设银行 8106"],
          repayment_remark: "电子汇入 / 退保证金",
          interest_rate_type: "none",
          interest_rate_value: "0.000000",
          interest_paid_amount: "0.00",
          loan_days: null,
          accrued_interest: "0.00",
          interest_paid_date: null,
          interest_payment_method: "",
          note: "",
          bank_row_ids: ["bank-company-repayment-income-40000"],
        },
      ],
    },
  ];
  const groups = (family === "all" ? allGroups : allGroups.filter((group) => group.family === family))
    .map((group) => ({
      ...group,
      flow_rows: (group.flow_rows ?? []).map((row) => ({
        ...row,
        selection_version: row.selection_version
          ?? `selection:${String(row.source_bank_row_id ?? row.flow_id ?? "unknown")}:current`,
      })),
    }));
  return {
    summary: {
      pending_repayment_amount: "800.00",
      repaid_amount: "500.00",
      pending_collection_amount: "2000.00",
      collected_amount: "1000.00",
      closed_amount: "300.00",
      suggested_count: groups.filter((group) => group.rows[0]?.status === "suggested").length,
      conflict_count: 0,
      row_count: groups.length,
    },
    family_summaries: [
      {
        family: "personal",
        label: "个人往来",
        pending_repayment_amount: "800.00",
        repaid_amount: "500.00",
        pending_collection_amount: "0.00",
        collected_amount: "0.00",
        pending_amount: "800.00",
        closed_amount: "300.00",
        row_count: 2,
      },
      {
        family: "company",
        label: "公司往来",
        pending_repayment_amount: "0.00",
        repaid_amount: "0.00",
        pending_collection_amount: "2000.00",
        collected_amount: "1000.00",
        pending_amount: "2000.00",
        closed_amount: "0.00",
        row_count: 1,
      },
      {
        family: "bank",
        label: "银行往来",
        pending_repayment_amount: "0.00",
        repaid_amount: "0.00",
        pending_collection_amount: "0.00",
        collected_amount: "0.00",
        pending_amount: "0.00",
        closed_amount: "0.00",
        row_count: 0,
      },
      {
        family: "business",
        label: "业务往来",
        pending_repayment_amount: "0.00",
        repaid_amount: "0.00",
        pending_collection_amount: "0.00",
        collected_amount: "0.00",
        pending_amount: "0.00",
        closed_amount: "0.00",
        row_count: 0,
      },
    ],
    groups,
    pagination: {
      page: 1,
      page_size: 50,
      total: groups.length,
    },
    ...overrides,
  };
}

function groupedPayloadWithFlowCategoryVersions(
  family: string,
  versionsByBankRowId: Record<string, number>,
  overrides: Record<string, unknown> = {},
) {
  const payload = cloneJson(groupedPayload(family, overrides));
  for (const group of payload.groups) {
    group.flow_rows = (group.flow_rows ?? []).map((row: Record<string, unknown>) => {
      const bankRowId = String(row.source_bank_row_id ?? "");
      if (!Object.prototype.hasOwnProperty.call(versionsByBankRowId, bankRowId)) {
        return row;
      }
      return {
        ...row,
        category_version: versionsByBankRowId[bankRowId],
        selection_version: `selection:${bankRowId}:${versionsByBankRowId[bankRowId]}`,
      };
    });
  }
  return payload;
}

function paginatedGroupedPayload(page: number, pageSize: number, total = 121) {
  const template = cloneJson(groupedPayload("personal").groups[0]);
  const groups = Array.from({ length: total }, (_, index) => {
    const sequence = String(index + 1).padStart(3, "0");
    return {
      ...cloneJson(template),
      group_id: `counterparty:personal:page-${sequence}`,
      counterparty_name: `分页往来方 ${sequence}`,
      rows: template.rows.map((row: Record<string, unknown>, rowIndex: number) => ({
        ...cloneJson(row),
        relation_id: `rel-page-${sequence}-${rowIndex + 1}`,
        bank_row_ids: [`bank-page-${sequence}-${rowIndex + 1}`],
      })),
    };
  });
  return groupedPayload("all", {
    groups: groups.slice((page - 1) * pageSize, page * pageSize),
    pagination: { page, page_size: pageSize, total },
  });
}

function groupedPayloadWithWorkbenchRelation(family: string, bankRowId: string, relation: Record<string, unknown>) {
  const payload = cloneJson(groupedPayload(family));
  const relationRowIds = new Set(
    (Array.isArray(relation.workbench_relation_row_ids)
      ? relation.workbench_relation_row_ids
      : [bankRowId]).map(String),
  );
  for (const group of payload.groups) {
    group.flow_rows = (group.flow_rows ?? []).map((row: Record<string, unknown>) => (
      relationRowIds.has(String(row.source_bank_row_id ?? ""))
        ? { ...row, ...relation }
        : row
    ));
    const groupFlowIds = (group.flow_rows ?? []).map((row: Record<string, unknown>) => String(row.source_bank_row_id ?? ""));
    if (groupFlowIds.length > 0 && groupFlowIds.every((rowId: string) => relationRowIds.has(rowId))) {
      group.cash_pair_linked = Boolean(relation.cash_pair_linked ?? relation.cash_closure_linked);
      group.paired_unsettled = Boolean(relation.cash_pair_linked) && !Boolean(relation.cash_closure_linked);
      group.cash_closure_linked = Boolean(relation.cash_closure_linked);
      group.pending_direction = relation.cash_closure_linked ? "none" : group.pending_direction;
      group.pending_direction_label = relation.cash_closure_linked ? "" : group.pending_direction_label;
      group.pending_amount = relation.cash_closure_linked ? "0.00" : group.pending_amount;
      group.closed_amount = "0.00";
    }
  }
  return payload;
}

function groupedPayloadWithFlowRelation(family: string, bankRowId: string, relationId: string) {
  const payload = cloneJson(groupedPayload(family));
  for (const group of payload.groups) {
    group.flow_rows = (group.flow_rows ?? []).map((row: Record<string, unknown>) => (
      row.source_bank_row_id === bankRowId ? { ...row, relation_id: relationId } : row
    ));
  }
  return payload;
}

function installTurnoverLedgerFetch(options: {
  groupedOverrides?: Record<string, unknown>;
  groupedPayloads?: Array<Record<string, unknown>>;
  groupedResponse?: (url: URL) => Promise<Response> | Response;
  groupedFailuresBeforeSuccess?: number;
  missingDetailForRelationId?: string;
  exportDownloadResponse?: (url: URL) => Response;
  closureConfirmResponse?: () => Promise<Response> | Response;
} = {}) {
  let groupedRequestCount = 0;
  let groupedFailuresRemaining = options.groupedFailuresBeforeSuccess ?? 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();

    if (url.pathname === "/api/turnover-ledger/tag-selection" && method === "GET") {
      return Response.json({
        version: 2,
        selected_tag_codes: ["external_rule_borrow_out", "external_rule_repaid"],
        inactive_selected_tag_codes: [],
        active_tags: [
          {
            code: "external_rule_borrow_out",
            label: "借出款",
            path: ["银行明细自动标签规则", "外部往来款付款", "借出款"],
            source: "custom",
            status: "active",
            output_primary_label: "外部往来款付款",
            output_sub_label: "借出款",
            turnover_role: "external_turnover",
            turnover_action_type: "pending_collection",
          },
          {
            code: "external_rule_repaid",
            label: "归还借款",
            path: ["银行明细自动标签规则", "外部往来款付款", "归还借款"],
            source: "custom",
            status: "active",
            output_primary_label: "外部往来款付款",
            output_sub_label: "归还借款",
            turnover_role: "external_turnover",
            turnover_action_type: "repaid",
          },
          {
            code: "external_rule_borrow_in",
            label: "借入款",
            path: ["银行明细自动标签规则", "外部往来款收款", "借入款"],
            source: "custom",
            status: "active",
            output_primary_label: "外部往来款收款",
            output_sub_label: "借入款",
            turnover_role: "external_turnover",
            turnover_action_type: "pending_repayment",
          },
        ],
      });
    }
    if (url.pathname === "/api/turnover-ledger/tag-selection" && method === "PUT") {
      const body = JSON.parse(String(init?.body));
      return Response.json({
        version: 3,
        selected_tag_codes: body.selected_tag_codes,
        inactive_selected_tag_codes: [],
        active_tags: [
          {
            code: "external_rule_borrow_out",
            label: "借出款",
            path: ["银行明细自动标签规则", "外部往来款付款", "借出款"],
            source: "custom",
            status: "active",
            output_primary_label: "外部往来款付款",
            output_sub_label: "借出款",
            turnover_role: "external_turnover",
            turnover_action_type: "pending_collection",
          },
          {
            code: "external_rule_repaid",
            label: "归还借款",
            path: ["银行明细自动标签规则", "外部往来款付款", "归还借款"],
            source: "custom",
            status: "active",
            output_primary_label: "外部往来款付款",
            output_sub_label: "归还借款",
            turnover_role: "external_turnover",
            turnover_action_type: "repaid",
          },
          {
            code: "external_rule_borrow_in",
            label: "借入款",
            path: ["银行明细自动标签规则", "外部往来款收款", "借入款"],
            source: "custom",
            status: "active",
            output_primary_label: "外部往来款收款",
            output_sub_label: "借入款",
            turnover_role: "external_turnover",
            turnover_action_type: "pending_repayment",
          },
        ],
      });
    }
    if (url.pathname === "/api/turnover-ledger" && method === "GET") {
      expect(url.searchParams.get("view")).toBe("grouped");
      if (options.groupedResponse) {
        return options.groupedResponse(url);
      }
      if (groupedFailuresRemaining > 0) {
        groupedFailuresRemaining -= 1;
        return Response.json({
          error: "turnover_ledger_temporarily_unavailable",
          message: "往来款台账加载暂时失败，请刷新后重试。",
        }, { status: 503 });
      }
      if (options.groupedPayloads?.length) {
        const payload = options.groupedPayloads[Math.min(groupedRequestCount, options.groupedPayloads.length - 1)];
        groupedRequestCount += 1;
        return Response.json(payload);
      }
      groupedRequestCount += 1;
      return Response.json(groupedPayload(url.searchParams.get("family") ?? "all", options.groupedOverrides));
    }
    if (url.pathname === "/api/turnover-ledger/bank-row-tags/batch" && method === "POST") {
      return Response.json({
        updated_categories: [
          {
            transaction_id: "bank-jia-income-200000",
            category_code: "borrow_in_company_pending_repayment",
            category_label: "公司暂借款：待还款",
            category_path: ["借入", "公司往来款", "待还款"],
            version: 1,
          },
        ],
        affected_months: ["2026-02"],
        turnover_ledger_invalidated: true,
        workbench_invalidated: true,
      });
    }
    if (url.pathname === "/api/turnover-ledger/relations/rel-personal-1" && method === "GET") {
      if (options.missingDetailForRelationId === "rel-personal-1") {
        return Response.json(
          { error: "unknown_relation_id", message: "往来款关系不存在。" },
          { status: 404 },
        );
      }
      return Response.json({
        relation: groupedPayload("personal").groups[0].rows[0],
        bank_rows: [
          {
            id: "bank-personal-001",
            trade_time: "2026-05-01 10:00:00",
            counterparty_name: "张三",
            direction_label: "收",
            amount: "1000.00",
            bank_account_label: "建行 8106",
            summary: "暂借款",
          },
        ],
        audit_history: [],
      });
    }
    if (url.pathname === "/api/turnover-ledger/relations/rel-personal-1/extra" && method === "GET") {
      return Response.json({
        relation_id: "rel-personal-1",
        interest_rate_type: "annual",
        interest_rate_value: "0.060000",
        interest_paid_amount: "10.00",
        interest_paid_date: "2026-05-05",
        interest_payment_method: "转账",
        note: "页面内维护备注",
        updated_at: "2026-05-11T10:00:00+08:00",
      });
    }
    if (url.pathname === "/api/turnover-ledger/relations/rel-personal-1/extra" && method === "PUT") {
      return Response.json({
        relation_id: "rel-personal-1",
        extra: JSON.parse(String(init?.body)),
      });
    }
    if (url.pathname === "/api/turnover-ledger/relations/rel-jiaxiaohua" && method === "GET") {
      if (options.missingDetailForRelationId === "rel-jiaxiaohua") {
        return Response.json(
          { error: "unknown_relation_id", message: "往来款关系不存在。" },
          { status: 404 },
        );
      }
      return Response.json({
        relation: groupedPayload("personal").groups[1].summary_row,
        bank_rows: [
          {
            id: "bank-jia-income-200000",
            trade_time: "2026-02-04 13:20:48",
            counterparty_name: "贾小花",
            direction_label: "收",
            amount: "200000.00",
            bank_account_label: "建行 8106",
            summary: "个人暂借款：待还款",
          },
        ],
        audit_history: [],
      });
    }
    if (url.pathname === "/api/turnover-ledger/relations/rel-jiaxiaohua/extra" && method === "GET") {
      return Response.json({
        relation_id: "rel-jiaxiaohua",
        interest_rate_type: "annual",
        interest_rate_value: "0.060000",
        interest_paid_amount: "10.00",
        interest_paid_date: "2026-05-05",
        interest_payment_method: "转账",
        note: "页面内维护备注",
        updated_at: "2026-05-12T10:00:00+08:00",
      });
    }
    if (url.pathname === "/api/turnover-ledger/relations/rel-jiaxiaohua/extra" && method === "PUT") {
      return Response.json({
        relation_id: "rel-jiaxiaohua",
        extra: JSON.parse(String(init?.body)),
      });
    }
    if (url.pathname === "/api/turnover-ledger/export-preview" && method === "GET") {
      return Response.json({
        rows: [
          {
            sequence_no: 1,
            row_type: "summary",
            lot_id: "",
            family_label: url.searchParams.get("family") === "company" ? "公司往来" : "个人往来",
            counterparty_name: url.searchParams.get("family") === "company" ? "云南建设有限公司" : "张三",
            pending_repayment_amount: "0.00",
            pending_collection_amount: "2000.00",
            balance_amount: "2000.00",
            borrow_amount: "3000.00",
            borrow_date: "2026-05-02",
            repayment_amount: "1000.00",
            repayment_date: "2026-05-04",
            counterparty_bank_name: "中国银行",
            repayment_remark: "回款",
            interest_rate_type_label: "月息",
            interest_rate_value: "0.005000",
            interest_paid_amount: "0.00",
            loan_days: 2,
            accrued_interest: "1.00",
            interest_paid_date: "",
            interest_payment_method: "",
            note: "项目保证金",
            status_label: "人工确认",
          },
        ],
        totals: {
          pending_repayment_amount: "0.00",
          pending_collection_amount: "2000.00",
          accrued_interest: "1.00",
        },
      });
    }
    if (url.pathname === "/api/turnover-ledger/export" && method === "GET") {
      if (options.exportDownloadResponse) {
        return options.exportDownloadResponse(url);
      }
      return new Response(new Blob(["mock xlsx"], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }));
    }
    if (url.pathname === "/api/turnover-ledger/relations/confirm" && method === "POST") {
      return Response.json({ relation_id: "rel-personal-1", status: "confirmed" });
    }
    if (url.pathname === "/api/turnover-ledger/closures/confirm" && method === "POST") {
      if (options.closureConfirmResponse) {
        return options.closureConfirmResponse();
      }
      return Response.json({
        status: "confirmed",
        workbench_pair_relation: {
          case_id: "turnover:turnover_rel_company_closure",
          relation_mode: "turnover_manual_closure",
        },
        affected_months: ["2026-05"],
      });
    }
    if (url.pathname === "/api/turnover-ledger/closures/withdraw" && method === "POST") {
      return Response.json({
        status: "withdrawn",
        workbench_pair_relation: {
          case_id: "case-workbench-cash-1",
          relation_mode: "manual_confirmed",
        },
        affected_months: ["2026-05"],
      });
    }
    const withdrawMatch = url.pathname.match(/^\/api\/turnover-ledger\/relations\/([^/]+)\/withdraw$/);
    if (withdrawMatch && method === "POST") {
      const relationId = decodeURIComponent(withdrawMatch[1]);
      return Response.json({
        relation_id: relationId,
        status: "withdrawn",
        affected_months: ["2026-05"],
      });
    }
    throw new Error(`Unexpected request ${method} ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:turnover-ledger"),
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: vi.fn(),
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Turnover ledger page", () => {
  test("targets project primitives for shell, grouped table, right drawers, export dialog, and feedback", () => {
    const sourceByPath = Object.fromEntries(turnoverLedgerSourceFiles.map((path) => [path, readWebSource(path)]));
    const forbiddenMuiImports = turnoverLedgerSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /from ["']@mui\/|import\s+[^;]*@mui\//.test(source) ? [path] : [];
    });
    const forbiddenMuiSelectors = turnoverLedgerSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /\.Mui[A-Z][A-Za-z-]*/.test(source) ? [path] : [];
    });
    const forbiddenLegacySurfaces = turnoverLedgerSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /DownloadOutlinedIcon|KeyboardArrowDownIcon|KeyboardArrowRightIcon|CloseIcon|Snackbar|<(?:TextField|TableCell|TableRow|TableHead|TableBody|TableContainer|Dialog|DialogTitle|DialogContent|DialogActions|Drawer|Chip|IconButton|Tooltip|Tabs|Tab|FormControlLabel|MenuItem)\b/.test(source)
        ? [path]
        : [];
    });
    const pageSource = sourceByPath["src/pages/TurnoverLedgerPage.tsx"];
    const tableSource = sourceByPath["src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx"];
    const extraDrawerSource = sourceByPath["src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx"];
    const exportDialogSource = sourceByPath["src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx"];
    const missingPrimitiveTargets = [
      pageSource.includes("PageScaffold") ? null : "TurnoverLedgerPage.tsx should keep PageScaffold",
      pageSource.includes("StatePanel") ? null : "TurnoverLedgerPage.tsx should keep StatePanel for loading/empty/error states",
      /FinanceTable|finance-table|turnover.*table/.test(tableSource)
        ? null
        : "Grouped rows should use FinanceTable or project/native table classes",
      /AppDrawer|turnover.*drawer/.test(pageSource) && /AppDrawer|turnover.*drawer/.test(extraDrawerSource)
        ? null
        : "Tag, closure and extra info surfaces should use AppDrawer or project drawer classes",
      /AppDialog|turnover.*dialog/.test(exportDialogSource)
        ? null
        : "Export confirmation should use AppDialog or project dialog classes",
      /turnover.*toast|turnover.*feedback|turnover.*notice/.test(pageSource)
        ? null
        : "Mutation feedback should use a project feedback/toast class",
    ].filter(Boolean);

    expect({
      forbiddenMuiImports,
      forbiddenMuiSelectors,
      forbiddenLegacySurfaces,
      missingPrimitiveTargets,
    }).toEqual({
      forbiddenMuiImports: [],
      forbiddenMuiSelectors: [],
      forbiddenLegacySurfaces: [],
      missingPrimitiveTargets: [],
    });
  });

  test("keeps premium compact summary, grouped table, drawers, export dialog, and interaction CSS contracts", () => {
    const styles = readWebSource("src/app/styles.css");
    const pageSource = readWebSource("src/pages/TurnoverLedgerPage.tsx");
    const buttonRule = cssRule(styles, ".turnover-ledger-button", "transition");
    const summaryBandRule = cssRule(styles, ".turnover-ledger-summary-band", "border: 1px solid var(--fp-border)");
    const summaryMetricRule = cssRule(styles, ".turnover-ledger-summary-metric", "min-height: 84px");
    const panelRule = cssRule(styles, ".turnover-ledger-table-panel__inner");
    const tableWrapRule = cssRule(styles, ".turnover-ledger-table-wrap");
    const tableCellRule = cssRule(styles, ".turnover-ledger-table th,\n.turnover-ledger-table td");
    const tableHeaderRule = cssRule(styles, ".turnover-ledger-table th");
    const stickyCellRule = cssRule(styles, ".turnover-sticky-left-cell");
    const groupStartRule = cssRule(styles, ".turnover-group-start-row > td");
    const flowDividerRule = cssRule(styles, ".turnover-flow-row + .turnover-flow-row > td");
    const summaryRowRule = cssRule(styles, ".turnover-summary-row > td");
    const expandButtonRule = cssRule(styles, ".turnover-ledger-expand-button");
    const chipRule = cssRule(styles, ".turnover-ledger-chip");
    const amountRule = cssRule(
      styles,
      ".turnover-amount-income,\n.turnover-amount-expense,\n.turnover-amount-neutral,\n.turnover-amount-empty",
    );
    const tableButtonRule = cssRule(styles, ".turnover-ledger-table-button");
    const checkboxRule = cssRule(styles, ".turnover-ledger-checkbox");
    const checkboxRowRule = cssRule(styles, ".turnover-ledger-checkbox-row");
    const closureCardRule = cssRule(styles, ".turnover-ledger-closure-card");
    const extraControlRule = cssRule(
      styles,
      ".turnover-ledger-extra-control input,\n.turnover-ledger-extra-control textarea",
    );
    const exportWrapRule = cssRule(styles, ".turnover-ledger-export-dialog__table-wrap");
    const exportCellRule = cssRule(
      styles,
      ".turnover-ledger-export-dialog__table th,\n.turnover-ledger-export-dialog__table td",
    );
    const exportHeaderRule = cssRule(styles, ".turnover-ledger-export-dialog__table th");
    const exportMoneyRule = cssRule(styles, ".turnover-ledger-export-dialog__money-cell");
    const toastRule = cssRule(styles, ".turnover-ledger-toast", "box-shadow");
    const toastButtonRule = cssRule(styles, ".turnover-ledger-toast button");

    expect(buttonRule).toContain("--motion-fast");
    expect(buttonRule).toContain("--ease-out-quart");
    expect(pageSource).toContain("<ToggleButtonGroup");
    expect(pageSource).not.toContain("turnover-ledger-tabs__tab");
    expect(summaryBandRule).toContain("border: 1px solid var(--fp-border)");
    expect(summaryMetricRule).toContain("min-height: 84px");
    expect(summaryMetricRule).toContain("var(--fp-space-2) var(--fp-space-3)");
    expect(panelRule).toContain("var(--fp-space-2)");
    expect(tableWrapRule).toContain("height: clamp(520px, calc(100dvh - 244px), 720px)");
    expect(tableCellRule).toContain("--motion-fast");
    expect(tableHeaderRule).toContain("color-mix(in srgb, var(--fp-surface-muted)");
    expect(stickyCellRule).toContain("color-mix(in srgb, var(--fp-primary-soft)");
    expect(groupStartRule).toContain("color-mix(in srgb, var(--fp-primary)");
    expect(flowDividerRule).toContain("border-top: 1px solid var(--fp-border)");
    expect(summaryRowRule).toContain("color-mix(in srgb, var(--fp-primary-soft)");
    expect(expandButtonRule).toContain("--motion-fast");
    expect(chipRule).toContain("min-height: var(--fp-tag-height-table)");
    expect(chipRule).toContain("border-radius: var(--fp-tag-radius-table)");
    expect(amountRule).toContain("justify-content: flex-end");
    expect(amountRule).toContain("font-variant-numeric: tabular-nums");
    expect(amountRule).toContain("border-radius: var(--fp-tag-radius-table)");
    expect(tableButtonRule).toContain("--motion-fast");
    expect(checkboxRule).toContain("--motion-fast");
    expect(checkboxRowRule).toContain("--motion-fast");
    expect(closureCardRule).toContain("var(--fp-space-2) var(--fp-space-3)");
    expect(extraControlRule).toContain("--motion-fast");
    expect(exportWrapRule).toContain("calc(100vh - 280px)");
    expect(exportCellRule).toContain("--motion-fast");
    expect(exportHeaderRule).toContain("color-mix(in srgb, var(--fp-surface-muted)");
    expect(exportMoneyRule).toContain("text-align: right");
    expect(exportMoneyRule).toContain("font-variant-numeric: tabular-nums");
    expect(toastRule).toContain("border-radius: var(--fp-radius-sm)");
    expect(toastRule).toContain("box-shadow: var(--fp-shadow-popover)");
    expect(toastRule).not.toContain("--fp-shadow-lg");
    expect(toastButtonRule).toContain("--motion-fast");
    expect([
      tableHeaderRule,
      stickyCellRule,
      summaryRowRule,
      amountRule,
      exportHeaderRule,
    ].join("\n")).not.toMatch(/#d8e8f8|#eef8f0|#fff5eb|#f3f5fb/i);
  });

  test("loads every server page beyond the first 100 turnover groups", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch({
      groupedResponse: (url) => {
        const page = Number(url.searchParams.get("page") ?? 1);
        const pageSize = Number(url.searchParams.get("page_size") ?? 50);
        return Response.json(paginatedGroupedPayload(page, pageSize));
      },
    });

    renderTurnoverLedgerPage();

    expect(await screen.findByText("分页往来方 001")).toBeInTheDocument();
    expect(screen.getByText("显示 1-50 / 121")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "下一页" }));
    expect(await screen.findByText("分页往来方 051")).toBeInTheDocument();
    expect(screen.queryByText("分页往来方 001")).not.toBeInTheDocument();
    expect(screen.getByText("显示 51-100 / 121")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "下一页" }));
    expect(await screen.findByText("分页往来方 101")).toBeInTheDocument();
    expect(screen.getByText("分页往来方 121")).toBeInTheDocument();
    expect(screen.getByText("显示 101-121 / 121")).toBeInTheDocument();

    expect(requestUrls(fetchMock, "/api/turnover-ledger").map((url) => [
      url.searchParams.get("page"),
      url.searchParams.get("page_size"),
    ])).toEqual([
      ["1", "50"],
      ["2", "50"],
      ["3", "50"],
    ]);
  });

  test("renders the grouped HeroUI table with collapsed summary rows, sticky left cells, and no status column", async () => {
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    expect(within(page).getByRole("heading", { name: "外部往来款管理" })).toBeInTheDocument();
    expect(within(page).queryByText("基于银行明细标签实时汇总外部往来关系，并把已确认关系同步到关联台。")).not.toBeInTheDocument();
    expect(within(page).getByRole("radio", { name: "全部" })).toHaveAttribute("aria-checked", "true");
    expect(within(page).getByText("当前待还款金额")).toBeInTheDocument();
    expect(within(page).getByText("累计已还款金额")).toBeInTheDocument();
    expect(within(page).getByText("当前待收款金额")).toBeInTheDocument();
    expect(within(page).getByText("累计已收款金额")).toBeInTheDocument();
    expect(within(page).queryByText("已闭合金额")).not.toBeInTheDocument();
    expect(within(page).queryByText("待人工确认数量")).not.toBeInTheDocument();
    expect(within(page).queryByText("冲突/异常数量")).not.toBeInTheDocument();
    expect(within(page).queryByText("账单行数")).not.toBeInTheDocument();
    expect(within(page).queryByText("分组余额")).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "全部方向" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "借出" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "借入" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: /保存修改/ })).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "下载表格" })).toBeInTheDocument();
    const pendingRepaymentCard = within(page).getByTestId("turnover-summary-pending-repayment");
    expect(within(pendingRepaymentCard).getByText("当前待还款金额")).toBeInTheDocument();
    expect(within(pendingRepaymentCard).getAllByText("800.00")).toHaveLength(2);
    expect(within(pendingRepaymentCard).getByText("个人往来")).toBeInTheDocument();
    expect(within(pendingRepaymentCard).getByText("公司往来")).toBeInTheDocument();
    expect(within(pendingRepaymentCard).getByText("银行往来")).toBeInTheDocument();
    expect(within(pendingRepaymentCard).getByText("业务往来")).toBeInTheDocument();

    await waitFor(() => {
      const request = requestUrls(fetchMock, "/api/turnover-ledger")[0];
      expect(request?.searchParams.get("view")).toBe("grouped");
      expect(request?.searchParams.get("family")).toBe("all");
      expect(request?.searchParams.get("direction")).toBe("all");
    });

    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    expect(within(table).getByRole("columnheader", { name: "对方户名" })).toHaveClass("turnover-sticky-left-header");
    expect(within(table).queryByRole("columnheader", { name: "银行明细标签" })).not.toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "往来发生" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "结清发生" })).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "收入" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "支出" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "借款金额 / 借款日" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "还款金额 / 还款日" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "开户机构" })).not.toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "还款备注" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "利息额 / 年息或月息" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "借款天数" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "应还利息" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "还利息日期 / 方式" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "备注" })).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "关系状态" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "对方户名 / 大类 / 余额" })).not.toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "选择" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "操作" })).toBeInTheDocument();

    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:zhangsan");
    const summaryRow = within(table).getByTestId("turnover-row-rel-personal-1");
    expect(summaryRow).toHaveClass("turnover-group-start-row");
    expect(within(summaryRow).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(summaryRow).queryByRole("button", { name: /编辑/ })).not.toBeInTheDocument();
    expect(groupCell).toHaveClass("turnover-sticky-left-cell");
    expect(groupCell).not.toHaveAttribute("rowspan");
    expect(within(groupCell).getByText("张三")).toBeInTheDocument();
    expect(within(groupCell).getByText("个人往来")).toBeInTheDocument();
    expect(within(groupCell).queryByText("待还款合计：800.00")).not.toBeInTheDocument();
    expect(within(groupCell).getByText("待还款合计：")).toBeInTheDocument();
    expect(within(groupCell).getByText("800.00")).toBeInTheDocument();
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");
    expect(within(companyGroupCell).queryByText("待收款合计：2000.00")).not.toBeInTheDocument();
    expect(within(companyGroupCell).getByText("待收款合计：")).toBeInTheDocument();
    expect(within(companyGroupCell).getByText("2000.00")).toBeInTheDocument();
    expect(within(groupCell).queryByRole("button", { name: "展开 张三 批次明细" })).not.toBeInTheDocument();
    expect(within(groupCell).queryByRole("button", { name: "展开 张三 流水明细" })).not.toBeInTheDocument();
    expect(within(table).queryByText("招商银行批次账户")).not.toBeInTheDocument();
    expect(within(table).queryByText("明细")).not.toBeInTheDocument();

    const borrowAmountChip = within(table).getByTestId("amount-income-rel-personal-1-borrow");
    expect(borrowAmountChip).toHaveClass("turnover-amount-income");
    expect(within(borrowAmountChip).getByText("收")).toBeInTheDocument();
    expect(within(borrowAmountChip).getByText("1000.00")).toBeInTheDocument();
    const repaymentAmountChip = within(table).getByTestId("amount-expense-rel-personal-1-repayment");
    expect(repaymentAmountChip).toHaveClass("turnover-amount-expense");
    expect(within(repaymentAmountChip).getByText("支")).toBeInTheDocument();
    expect(within(repaymentAmountChip).getByText("200.00")).toBeInTheDocument();
    expect(within(table).getByTestId("turnover-row-rel-personal-1")).toHaveClass("turnover-summary-row");
    expect(within(table).queryByText("2026-05-01")).not.toBeInTheDocument();
    expect(within(table).queryByText("2026-05-03")).not.toBeInTheDocument();
    expect(within(table).queryByText("待人工确认")).not.toBeInTheDocument();
  });

  test("opens tag selection drawer, saves selected bank detail labels, and reloads ledger", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    await within(page).findByText("张三");
    const before = requestUrls(fetchMock, "/api/turnover-ledger").length;

    await user.click(within(page).getByRole("button", { name: "外部往来款标签设置" }));
    const drawer = await screen.findByRole("dialog", { name: "外部往来款标签设置" });
    expect(within(drawer).getByRole("heading", { name: "外部往来款标签设置" })).toBeInTheDocument();
    expect(within(drawer).getByLabelText("外部往来款付款")).toBeChecked();
    expect(within(drawer).getByLabelText("借出款")).toBeChecked();
    expect(within(drawer).getByLabelText("归还借款")).toBeChecked();
    expect(within(drawer).getByLabelText("借入款")).not.toBeChecked();

    await user.click(within(drawer).getByLabelText("归还借款"));
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      const saveRequest = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/tag-selection" && init?.method === "PUT";
      });
      expect(saveRequest).toBeDefined();
      expect(JSON.parse(String(saveRequest?.[1]?.body))).toEqual({
        expected_version: 2,
        selected_tag_codes: ["external_rule_borrow_out"],
      });
    });
    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/turnover-ledger").length).toBeGreaterThan(before);
    });
  });

  test("expands Jia Xiaohua with real flow rows instead of allocation lot rows", async () => {
    installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");

    await userEvent.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));

    const flowRows = within(table).getAllByTestId(/^turnover-flow-row-rel-jiaxiaohua-/);
    expect(flowRows).toHaveLength(3);
    expect(within(flowRows[0]).getByRole("checkbox", { name: "选择流水 贾小花 2026-02-04 13:20:48 收入 200000.00" })).toBeInTheDocument();
    expect(within(flowRows[0]).getByRole("button", { name: "编辑流水 贾小花 2026-02-04 13:20:48 收入 200000.00" })).toBeInTheDocument();
    expect(within(table).queryByText("流水")).not.toBeInTheDocument();
    expect(within(table).queryByText("总览不应展示的还款备注")).not.toBeInTheDocument();
    expect(within(flowRows[0]).getByText("200000.00")).toBeInTheDocument();
    expect(within(flowRows[0]).getByTestId("amount-empty-rel-jiaxiaohua-repayment")).toHaveTextContent("-");
    expect(within(flowRows[1]).getByText("100000.00")).toBeInTheDocument();
    expect(within(flowRows[1]).getByTestId("amount-empty-rel-jiaxiaohua-repayment")).toHaveTextContent("-");
    expect(within(flowRows[2]).getByTestId("amount-empty-rel-jiaxiaohua-borrow")).toHaveTextContent("-");
    expect(within(flowRows[2]).getByText("300000.00")).toBeInTheDocument();
    expect(within(table).getByText("200000.00")).toBeInTheDocument();
    expect(within(table).getByText("100000.00")).toBeInTheDocument();
    expect(within(table).getAllByText("300000.00")).toHaveLength(3);
    expect(within(table).getByText("2026-02-04 13:20:48")).toBeInTheDocument();
    expect(within(table).getByText("2026-02-04 17:07:45")).toBeInTheDocument();
    expect(within(table).getByText("2026-03-04 15:24:58")).toBeInTheDocument();
    expect(within(table).queryByText("分摊批次一")).not.toBeInTheDocument();
    expect(within(table).queryByText("分摊批次二")).not.toBeInTheDocument();
    expect(within(table).queryByText("批次 200000")).not.toBeInTheDocument();
    expect(within(table).queryByText("批次 100000")).not.toBeInTheDocument();
  });

  test("confirms a manual zero-difference turnover closure from two selected same-group flow rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");
    const openButton = within(page).getByRole("button", { name: "确认闭环" });
    expect(openButton).toBeDisabled();

    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-02 10:00:00 支出 1000.00" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-04 10:00:00 收入 1000.00" }));
    expect(openButton).toBeEnabled();
    await user.click(openButton);

    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    expect(within(drawer).getByRole("heading", { name: "确认外部往来闭环" })).toBeInTheDocument();
    expect(within(drawer).getByText("借出保证金")).toBeInTheDocument();
    expect(within(drawer).getByText("收回保证金")).toBeInTheDocument();
    expect(within(drawer).queryByText("bank-company-expense-1000")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("bank-company-income-1000")).not.toBeInTheDocument();
    expect(within(drawer).getByTestId("turnover-closure-delta")).toHaveTextContent("0.00");
    await user.click(within(drawer).getByRole("button", { name: "确定" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/closures/confirm" && init?.method === "POST";
      });
      expect(request).toBeDefined();
      expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
        bank_row_ids: ["bank-company-expense-1000", "bank-company-income-1000"],
        idempotency_key: expect.stringMatching(/^turnover-manual-closure:/),
      });
    });
    await waitFor(() => {
      expect(openButton).toBeDisabled();
    });
  });

  test("shows immediate pending feedback while a closure confirm request is in flight", async () => {
    const user = userEvent.setup();
    let resolveConfirm!: (response: Response) => void;
    const pendingConfirm = new Promise<Response>((resolve) => {
      resolveConfirm = resolve;
    });
    installTurnoverLedgerFetch({
      closureConfirmResponse: () => pendingConfirm,
    });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");
    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-02 10:00:00 支出 1000.00" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-04 10:00:00 收入 1000.00" }));
    await user.click(within(page).getByRole("button", { name: "确认闭环" }));

    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    await user.click(within(drawer).getByRole("button", { name: "确定" }));

    const progressDialog = await screen.findByRole("dialog", { name: "全局操作进度" });
    expect(within(progressDialog).getByText("正在确认外部往来闭环...")).toBeInTheDocument();

    resolveConfirm(Response.json({
      status: "confirmed",
      workbench_pair_relation: {
        case_id: "turnover:turnover_rel_company_closure",
        relation_mode: "turnover_manual_closure",
      },
      affected_months: ["2026-05"],
    }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "确认外部往来闭环" })).not.toBeInTheDocument();
    });
  });

  test("reloads exactly once after confirm without calling the operation barrier", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch({
      groupedPayloads: [
        groupedPayload("all"),
        groupedPayload("all"),
      ],
    });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");
    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-02 10:00:00 支出 1000.00" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-04 10:00:00 收入 1000.00" }));
    await user.click(within(page).getByRole("button", { name: "确认闭环" }));

    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    await user.click(within(drawer).getByRole("button", { name: "确定" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/closures/confirm" && init?.method === "POST";
      });
      expect(request).toBeDefined();
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "确认外部往来闭环" })).not.toBeInTheDocument();
    });
    expect(screen.queryByText("操作已提交，后台同步尚未完成，请稍后刷新。")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "操作失败" })).not.toBeInTheDocument();
    expect(requestUrls(fetchMock, "/api/turnover-ledger")).toHaveLength(2);
    expect(requestUrls(fetchMock, "/api/operation-barrier/status")).toHaveLength(0);
  });

  test("blocks closure confirm when a selected flow lacks the canonical selection version", async () => {
    const user = userEvent.setup();
    const payloadWithoutVersions = cloneJson(groupedPayload("all"));
    for (const group of payloadWithoutVersions.groups) {
      group.flow_rows = (group.flow_rows ?? []).map((row: Record<string, unknown>) => {
        const { selection_version: _selectionVersion, ...rest } = row;
        return rest;
      });
    }
    const fetchMock = installTurnoverLedgerFetch({
      groupedPayloads: [payloadWithoutVersions],
    });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");

    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-02 10:00:00 支出 1000.00" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-04 10:00:00 收入 1000.00" }));
    await user.click(within(page).getByRole("button", { name: "确认闭环" }));

    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    await user.click(within(drawer).getByRole("button", { name: "确定" }));

    expect(await screen.findByText("银行流水版本信息已更新，请刷新后重试")).toBeInTheDocument();
    const request = fetchMock.mock.calls.find(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/turnover-ledger/closures/confirm" && init?.method === "POST";
    });
    expect(request).toBeUndefined();
  });

  test("confirms a manual zero-difference turnover closure from three same-group flow rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const jiaGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    const openButton = within(page).getByRole("button", { name: "确认闭环" });
    expect(openButton).toBeDisabled();

    await user.click(within(jiaGroupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 贾小花 2026-02-04 17:07:45 收入 100000.00" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 贾小花 2026-03-04 15:24:58 支出 300000.00" }));
    expect(openButton).toBeEnabled();
    await user.click(openButton);

    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    expect(within(drawer).getAllByText("个人暂借款：待还款")).toHaveLength(2);
    expect(within(drawer).queryByText("bank-jia-income-200000")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("bank-jia-income-100000")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("bank-jia-expense-300000")).not.toBeInTheDocument();
    expect(within(drawer).getByText("收入合计").nextElementSibling).toHaveTextContent("300000.00");
    expect(within(drawer).getByText("支出合计").nextElementSibling).toHaveTextContent("300000.00");
    expect(within(drawer).getByTestId("turnover-closure-delta")).toHaveTextContent("0.00");
    await user.click(within(drawer).getByRole("button", { name: "确定" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/closures/confirm" && init?.method === "POST";
      });
      expect(request).toBeDefined();
      expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
        bank_row_ids: ["bank-jia-income-200000", "bank-jia-income-100000", "bank-jia-expense-300000"],
        idempotency_key: expect.stringMatching(/^turnover-manual-closure:/),
      });
    });
    await waitFor(() => expect(requestUrls(fetchMock, "/api/turnover-ledger").length).toBeGreaterThanOrEqual(2));
    expect(requestUrls(fetchMock, "/api/operation-barrier/status")).toHaveLength(0);
  });

  test("submits loaded exact selection versions without a pre-write ledger reload", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch({
      groupedPayloads: [
        groupedPayloadWithFlowCategoryVersions("all", {
          "bank-jia-income-200000": 1,
          "bank-jia-income-100000": 2,
          "bank-jia-expense-300000": 3,
        }),
      ],
    });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const jiaGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");

    await user.click(within(jiaGroupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 贾小花 2026-02-04 17:07:45 收入 100000.00" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 贾小花 2026-03-04 15:24:58 支出 300000.00" }));
    await user.click(within(page).getByRole("button", { name: "确认闭环" }));

    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    await user.click(within(drawer).getByRole("button", { name: "确定" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/closures/confirm" && init?.method === "POST";
      });
      expect(request).toBeDefined();
      expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
        bank_row_ids: ["bank-jia-income-200000", "bank-jia-income-100000", "bank-jia-expense-300000"],
        expected_versions: {
          "turnover_bank_row_selection:bank-jia-income-200000": "selection:bank-jia-income-200000:1",
          "turnover_bank_row_selection:bank-jia-income-100000": "selection:bank-jia-income-100000:2",
          "turnover_bank_row_selection:bank-jia-expense-300000": "selection:bank-jia-expense-300000:3",
        },
      });
    });
    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/turnover-ledger").length).toBeGreaterThanOrEqual(2);
    });
    expect(requestUrls(fetchMock, "/api/turnover-ledger")).toHaveLength(2);
  });

  test("confirms closure when cash direction crosses turnover stage columns", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");

    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-03-11 16:07:35 支出 40000.00" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-04-03 18:00:16 收入 40000.00" }));

    const openButton = within(page).getByRole("button", { name: "确认闭环" });
    expect(openButton).toBeEnabled();
    await user.click(openButton);

    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    expect(within(drawer).getByText("支出")).toBeInTheDocument();
    expect(within(drawer).getByText("收入")).toBeInTheDocument();
    expect(within(drawer).getByText("收入合计").nextElementSibling).toHaveTextContent("40000.00");
    expect(within(drawer).getByText("支出合计").nextElementSibling).toHaveTextContent("40000.00");
    expect(within(drawer).getByTestId("turnover-closure-delta")).toHaveTextContent("0.00");
    await user.click(within(drawer).getByRole("button", { name: "确定" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/closures/confirm" && init?.method === "POST";
      });
      expect(request).toBeDefined();
      const body = JSON.parse(String(request?.[1]?.body));
      expect(body.bank_row_ids).toHaveLength(2);
      expect(body.bank_row_ids).toEqual(expect.arrayContaining([
        "bank-company-borrow-expense-40000",
        "bank-company-repayment-income-40000",
      ]));
      expect(body.idempotency_key).toMatch(/^turnover-manual-closure:/);
    });
  });

  test("blocks cross-group selection and disables drawer confirmation for non-zero difference", async () => {
    const user = userEvent.setup();
    installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const jiaGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(jiaGroupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");
    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-04 10:00:00 收入 1000.00" }));
    expect(await screen.findByText("一次只能选择同一往来组内的流水")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关闭提示" })).toBeInTheDocument();

    await user.click(within(table).getByRole("checkbox", { name: "选择流水 贾小花 2026-03-04 15:24:58 支出 300000.00" }));
    await user.click(within(page).getByRole("button", { name: "确认闭环" }));
    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    expect(within(drawer).getByTestId("turnover-closure-delta")).toHaveTextContent("100000.00");
    expect(within(drawer).getByRole("button", { name: "确定" })).toBeDisabled();
  });

  test("withdraws a selected workbench cash closure from the table toolbar", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch({
      groupedPayloads: [
        groupedPayloadWithWorkbenchRelation("all", "bank-jia-income-200000", {
          workbench_relation_status: "linked",
          workbench_relation_case_ids: ["case-workbench-cash-1"],
          workbench_relation_mode: "manual_confirmed",
          workbench_relation_source: "manual",
          workbench_relation_row_ids: ["bank-jia-income-200000", "bank-jia-expense-300000"],
          cash_closure_linked: true,
          cash_closure_case_id: "case-workbench-cash-1",
          cash_closure_source: "workbench_relation",
          cash_closure_relation_id: "",
        }),
        groupedPayload("all"),
      ],
    });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));

    expect(within(page).getByText("已选 1 笔")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "确认闭环" })).not.toBeInTheDocument();
    const withdrawButton = within(page).getByRole("button", { name: "撤回闭环" });
    expect(withdrawButton).toBeEnabled();
    await user.click(withdrawButton);

    await waitFor(() => {
      const withdrawRequest = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/closures/withdraw" && init?.method === "POST"
          && JSON.parse(String(init?.body)).cash_closure_case_id === "case-workbench-cash-1";
      });
      expect(withdrawRequest).toBeDefined();
    });
    await waitFor(() => expect(requestUrls(fetchMock, "/api/turnover-ledger").length).toBeGreaterThanOrEqual(2));
    expect(requestUrls(fetchMock, "/api/operation-barrier/status")).toHaveLength(0);
  });

  test("allows manual closure confirmation when selected rows are only linked to OA", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch({
      groupedPayloads: [
        groupedPayloadWithWorkbenchRelation("all", "bank-company-expense-1000", {
          workbench_relation_status: "linked",
          workbench_relation_case_ids: ["case-oa-company-1"],
          workbench_relation_mode: "manual_confirmed",
          workbench_relation_source: "manual",
          workbench_relation_row_ids: ["oa-company-1", "bank-company-expense-1000"],
          linked_oa: true,
        }),
      ],
    });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");
    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));

    const flowRows = within(table).getAllByTestId(/^turnover-flow-row-rel-company-1-/);
    expect(within(flowRows[0]).getByText("已关联 OA")).toBeInTheDocument();
    expect(within(flowRows[0]).queryByText("未闭环")).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "撤回闭环" })).not.toBeInTheDocument();

    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-02 10:00:00 支出 1000.00" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 云南建设有限公司 2026-05-04 10:00:00 收入 1000.00" }));

    const openButton = within(page).getByRole("button", { name: "确认闭环" });
    expect(openButton).toBeEnabled();
    expect(within(page).queryByRole("button", { name: "撤回闭环" })).not.toBeInTheDocument();
    await user.click(openButton);

    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    await user.click(within(drawer).getByRole("button", { name: "确定" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/closures/confirm" && init?.method === "POST";
      });
      expect(request).toBeDefined();
      expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
        bank_row_ids: ["bank-company-expense-1000", "bank-company-income-1000"],
      });
    });
  });

  test("opens the extra drawer from a flow row, hides technical relation ids, saves, and keeps relation actions in the drawer", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    expect(within(table).queryByRole("button", { name: "确认归并" })).not.toBeInTheDocument();

    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("button", { name: "编辑流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));
    const drawer = await screen.findByRole("dialog", { name: "编辑流水补充信息" });
    expect(within(drawer).getByRole("heading", { name: "编辑流水补充信息" })).toBeInTheDocument();
    expect(within(drawer).getByText("贾小花")).toBeInTheDocument();
    expect(within(drawer).getByText("个人往来")).toBeInTheDocument();
    expect(within(drawer).getByText("2026-02-04 13:20:48")).toBeInTheDocument();
    expect(within(drawer).queryByText(/turnover_rel_/)).not.toBeInTheDocument();
    expect(within(drawer).queryByText("rel-jiaxiaohua")).not.toBeInTheDocument();
    expect(within(drawer).getByText("流水概览")).toBeInTheDocument();
    expect(within(drawer).getByText("补充信息")).toBeInTheDocument();
    expect(within(drawer).getByText("操作记录 / 关系操作")).toBeInTheDocument();
    expect(within(drawer).queryByText("bank-jia-income-200000")).not.toBeInTheDocument();
    expect(within(drawer).getAllByText("建行 8106").length).toBeGreaterThan(0);
    expect(within(drawer).getAllByText("收").length).toBeGreaterThan(0);
    expect(within(drawer).getAllByText("200000.00").length).toBeGreaterThan(0);
    expect(within(drawer).getByRole("button", { name: "确认归并" })).toBeDisabled();
    expect(within(drawer).getByRole("button", { name: "撤销归并" })).toBeEnabled();

    const saveButton = within(drawer).getByRole("button", { name: "保存补充信息" });
    expect(saveButton).toBeDisabled();
    await user.clear(within(drawer).getByLabelText("利率值"));
    await user.type(within(drawer).getByLabelText("利率值"), "0.070000");
    expect(saveButton).toBeEnabled();
    await user.click(saveButton);

    await waitFor(() => {
      const saveRequest = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/relations/rel-jiaxiaohua/extra" && init?.method === "PUT";
      });
      expect(saveRequest).toBeDefined();
      expect(JSON.parse(String(saveRequest?.[1]?.body))).toMatchObject({
        interest_rate_type: "annual",
        interest_rate_value: "0.070000",
        interest_paid_amount: "10.00",
        interest_paid_date: "2026-05-05",
        interest_payment_method: "转账",
        note: "页面内维护备注",
        expected_versions: {
          "turnover_relation_extra:rel-jiaxiaohua": "2026-05-12T10:00:00+08:00",
        },
      });
    });
    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/turnover-ledger").length).toBeGreaterThanOrEqual(2);
    });
  });

  test("keeps the active relation form when an aborted older response resolves after a newer editor", async () => {
    const user = userEvent.setup();
    const olderExtra = deferredResponse();
    const baseFetch = installTurnoverLedgerFetch({
      groupedPayloads: [groupedPayloadWithFlowRelation("all", "bank-jia-income-200000", "rel-personal-1")],
    });
    let olderSignal: AbortSignal | null = null;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/turnover-ledger/relations/rel-personal-1/extra" && init?.method === "GET") {
        olderSignal = init.signal ?? null;
        return olderExtra.promise;
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("button", { name: "编辑流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));

    const drawer = await screen.findByRole("dialog", { name: "编辑流水补充信息" });
    expect(within(drawer).getByLabelText("备注")).toBeDisabled();
    expect(within(drawer).getByRole("button", { name: "保存补充信息" })).toBeDisabled();

    act(() => {
      within(table).getByRole("button", { hidden: true, name: "编辑流水 贾小花 2026-02-04 17:07:45 收入 100000.00" }).click();
    });
    await waitFor(() => expect(within(drawer).getByLabelText("备注")).toHaveValue("页面内维护备注"));
    expect(olderSignal?.aborted).toBe(true);

    await act(async () => {
      olderExtra.resolve(Response.json({
        relation_id: "rel-personal-1",
        interest_rate_type: "annual",
        interest_rate_value: "0.990000",
        interest_paid_amount: "999.00",
        interest_paid_date: "2026-05-01",
        interest_payment_method: "旧关系",
        note: "A 的过期补充信息",
        updated_at: "2026-05-10T10:00:00+08:00",
      }));
      await olderExtra.promise;
    });
    expect(within(drawer).getByLabelText("备注")).toHaveValue("页面内维护备注");

    await user.clear(within(drawer).getByLabelText("备注"));
    await user.type(within(drawer).getByLabelText("备注"), "只保存 B");
    await user.click(within(drawer).getByRole("button", { name: "保存补充信息" }));

    await waitFor(() => {
      const saveRequests = fetchMock.mock.calls.filter(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return init?.method === "PUT" && url.pathname.endsWith("/extra");
      });
      expect(saveRequests).toHaveLength(1);
      const [input, init] = saveRequests[0];
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      expect(url.pathname).toBe("/api/turnover-ledger/relations/rel-jiaxiaohua/extra");
      expect(JSON.parse(String(init?.body))).toMatchObject({
        note: "只保存 B",
        expected_versions: {
          "turnover_relation_extra:rel-jiaxiaohua": "2026-05-12T10:00:00+08:00",
        },
      });
    });
  });

  test("ignores an older request failure and finalizer while the active relation is still loading", async () => {
    const user = userEvent.setup();
    const olderExtra = deferredResponse();
    const activeExtra = deferredResponse();
    const baseFetch = installTurnoverLedgerFetch({
      groupedPayloads: [groupedPayloadWithFlowRelation("all", "bank-jia-income-200000", "rel-personal-1")],
    });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/turnover-ledger/relations/rel-personal-1/extra" && init?.method === "GET") {
        return olderExtra.promise;
      }
      if (url.pathname === "/api/turnover-ledger/relations/rel-jiaxiaohua/extra" && init?.method === "GET") {
        return activeExtra.promise;
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("button", { name: "编辑流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));
    const drawer = await screen.findByRole("dialog", { name: "编辑流水补充信息" });
    act(() => {
      within(table).getByRole("button", { hidden: true, name: "编辑流水 贾小花 2026-02-04 17:07:45 收入 100000.00" }).click();
    });

    await act(async () => {
      olderExtra.reject(new Error("A 的过期请求失败"));
      await Promise.resolve();
    });
    expect(within(drawer).getByText("正在加载关系详情和补充信息。")).toBeInTheDocument();
    expect(within(drawer).queryByText("A 的过期请求失败")).not.toBeInTheDocument();
    expect(within(drawer).getByLabelText("备注")).toBeDisabled();

    await act(async () => {
      activeExtra.resolve(Response.json({
        relation_id: "rel-jiaxiaohua",
        interest_rate_type: "annual",
        interest_rate_value: "0.060000",
        interest_paid_amount: "10.00",
        interest_paid_date: "2026-05-05",
        interest_payment_method: "转账",
        note: "B 的有效补充信息",
        updated_at: "2026-05-12T10:00:00+08:00",
      }));
      await activeExtra.promise;
    });
    await waitFor(() => expect(within(drawer).getByLabelText("备注")).toHaveValue("B 的有效补充信息"));
    expect(within(drawer).queryByText("正在加载关系详情和补充信息。")).not.toBeInTheDocument();
  });

  test("aborts and invalidates a pending editor request when the drawer closes", async () => {
    const user = userEvent.setup();
    const pendingExtra = deferredResponse();
    const baseFetch = installTurnoverLedgerFetch();
    let pendingSignal: AbortSignal | null = null;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/turnover-ledger/relations/rel-jiaxiaohua/extra" && init?.method === "GET") {
        pendingSignal = init.signal ?? null;
        return pendingExtra.promise;
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("button", { name: "编辑流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));
    const drawer = await screen.findByRole("dialog", { name: "编辑流水补充信息" });
    await user.click(within(drawer).getByRole("button", { name: "关闭" }));

    expect(pendingSignal?.aborted).toBe(true);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "编辑流水补充信息" })).not.toBeInTheDocument());
    await act(async () => {
      pendingExtra.resolve(Response.json({ relation_id: "rel-jiaxiaohua", note: "不应重新出现" }));
      await pendingExtra.promise;
    });
    expect(screen.queryByRole("dialog", { name: "编辑流水补充信息" })).not.toBeInTheDocument();
  });

  test("keeps the active form dirty when the backend rejects a stale extra version", async () => {
    const user = userEvent.setup();
    const baseFetch = installTurnoverLedgerFetch();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/turnover-ledger/relations/rel-jiaxiaohua/extra" && init?.method === "PUT") {
        return Response.json({
          error: "turnover_relation_extra_conflict",
          message: "补充信息已被其他会话更新，请重新打开后再保存。",
        }, { status: 409 });
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("button", { name: "编辑流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));
    const drawer = await screen.findByRole("dialog", { name: "编辑流水补充信息" });
    const note = within(drawer).getByLabelText("备注");
    await user.clear(note);
    await user.type(note, "发生版本冲突时保留");
    await user.click(within(drawer).getByRole("button", { name: "保存补充信息" }));

    expect((await screen.findAllByText("补充信息已被其他会话更新，请重新打开后再保存。")).length).toBeGreaterThan(0);
    expect(note).toHaveValue("发生版本冲突时保留");
    const errorDialog = await screen.findByRole("dialog", { name: "全局操作进度" });
    await user.click(within(errorDialog).getByRole("button", { name: "确定" }));
    await waitFor(() => expect(within(drawer).getByRole("button", { name: "保存补充信息" })).toBeEnabled());
    expect(requestUrls(fetchMock, "/api/turnover-ledger")).toHaveLength(1);
  });

  test("locks editor inputs and close while an extra save is in flight", async () => {
    const user = userEvent.setup();
    const pendingSave = deferredResponse();
    const baseFetch = installTurnoverLedgerFetch();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/turnover-ledger/relations/rel-jiaxiaohua/extra" && init?.method === "PUT") {
        return pendingSave.promise;
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("button", { name: "编辑流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));
    const drawer = await screen.findByRole("dialog", { name: "编辑流水补充信息" });
    const note = within(drawer).getByLabelText("备注");
    await user.clear(note);
    await user.type(note, "保存中锁定");
    await user.click(within(drawer).getByRole("button", { name: "保存补充信息" }));

    await waitFor(() => expect(note).toBeDisabled());
    const progressDialog = await screen.findByRole("dialog", { name: "全局操作进度" });
    expect(within(progressDialog).getByText("正在保存往来关系补充信息...")).toBeInTheDocument();
    expect(drawer.querySelector<HTMLButtonElement>('button[aria-label="关闭"]')).toBeDisabled();
    expect(Array.from(drawer.querySelectorAll<HTMLButtonElement>("button"))
      .find((button) => button.textContent === "保存补充信息")).toBeDisabled();

    await act(async () => {
      pendingSave.resolve(Response.json({
        extra: {
          relation_id: "rel-jiaxiaohua",
          interest_rate_type: "annual",
          interest_rate_value: "0.060000",
          interest_paid_amount: "10.00",
          interest_paid_date: "2026-05-05",
          interest_payment_method: "转账",
          note: "保存中锁定",
          updated_at: "2026-05-13T10:00:00+08:00",
          updated_by: "TESTFULL001",
        },
      }));
      await pendingSave.promise;
    });
    await waitFor(() => expect(note).toBeEnabled());
    expect(within(drawer).getByRole("button", { name: "关闭" })).toBeEnabled();
  });

  test("shows a business error when relation detail disappears after the ledger was rendered", async () => {
    const user = userEvent.setup();
    installTurnoverLedgerFetch({ missingDetailForRelationId: "rel-jiaxiaohua" });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("button", { name: "编辑流水 贾小花 2026-02-04 13:20:48 收入 200000.00" }));

    const drawer = await screen.findByRole("dialog", { name: "编辑流水补充信息" });
    expect(await within(drawer).findByText("该流水所属往来关系已刷新或不存在，请刷新台账后再编辑。")).toBeInTheDocument();
    expect(within(drawer).queryByText(/turnover_rel_/)).not.toBeInTheDocument();
    expect(within(drawer).queryByText("rel-jiaxiaohua")).not.toBeInTheDocument();
  });

  test("recovers grouped ledger after a transient load failure when refreshed", async () => {
    const user = userEvent.setup();
    installTurnoverLedgerFetch({ groupedFailuresBeforeSuccess: 1 });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    expect(await within(page).findByText("往来款台账加载暂时失败，请刷新后重试。")).toBeInTheDocument();
    expect(within(page).queryByText("暂无往来款台账")).not.toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "刷新台账" }));

    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    expect(await within(table).findByText("贾小花")).toBeInTheDocument();
    expect(within(page).queryByText("往来款台账加载暂时失败，请刷新后重试。")).not.toBeInTheDocument();
  });

  test("shows bank-detail tags as read-only in turnover management", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");

    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));

    expect(within(table).queryByRole("combobox", { name: /往来款子标签/ })).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: /保存修改/ })).not.toBeInTheDocument();
    expect(within(table).queryByText("银行明细标签")).not.toBeInTheDocument();
    const flowRows = within(table).getAllByTestId(/^turnover-flow-row-rel-jiaxiaohua-/);
    expect(within(flowRows[0]).getByText("外部往来款收款")).toBeInTheDocument();
    expect(within(flowRows[0]).getByText("借入款")).toBeInTheDocument();
    expect(within(flowRows[0]).getByText("个人往来")).toBeInTheDocument();
    expect(within(flowRows[0]).getByText("建行 8106")).toBeInTheDocument();
    expect(within(flowRows[2]).getByText("外部往来款付款")).toBeInTheDocument();
    expect(within(flowRows[2]).getByText("归还借款")).toBeInTheDocument();
    expect(within(flowRows[2]).getByText("个人往来")).toBeInTheDocument();
    expect(within(flowRows[2]).getByText("建行 8106")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/turnover-ledger/bank-row-tags/batch" && init?.method === "POST";
    })).toBe(false);
  });

  test("shows Workbench relation feedback from the grouped ledger payload", async () => {
    const user = userEvent.setup();
    installTurnoverLedgerFetch({
      groupedPayloads: [
        groupedPayloadWithWorkbenchRelation("all", "bank-jia-income-200000", {
          workbench_relation_status: "linked",
          workbench_relation_case_ids: ["turnover:rel-jiaxiaohua"],
          workbench_relation_mode: "turnover_manual_closure",
          workbench_relation_source: "manual",
          workbench_relation_row_ids: [
            "bank-jia-income-200000",
            "bank-jia-income-100000",
            "bank-jia-expense-300000",
          ],
          cash_pair_linked: true,
          cash_pair_case_id: "turnover:rel-jiaxiaohua",
          cash_closure_linked: true,
          cash_closure_case_id: "turnover:rel-jiaxiaohua",
          cash_closure_source: "turnover_ledger",
          cash_closure_relation_id: "rel-jiaxiaohua",
        }),
      ],
    });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");

    expect(within(groupCell).getByText("收支闭环")).toBeInTheDocument();
    expect(within(groupCell).queryByText(/部分已闭环/)).not.toBeInTheDocument();
    expect(within(groupCell).queryByText("部分已关联 1/3")).not.toBeInTheDocument();
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));

    const flowRows = within(table).getAllByTestId(/^turnover-flow-row-rel-jiaxiaohua-/);
    expect(within(flowRows[0]).getByText("收支闭环")).toBeInTheDocument();
    expect(within(flowRows[1]).queryByText("未闭环")).not.toBeInTheDocument();
    expect(within(flowRows[2]).queryByText("未闭环")).not.toBeInTheDocument();
    expect(within(flowRows[0]).queryByText("关联台手工闭环")).not.toBeInTheDocument();
  });

  test("shows an active non-zero cash case as paired but unsettled", async () => {
    const user = userEvent.setup();
    installTurnoverLedgerFetch({
      groupedPayloads: [
        groupedPayloadWithWorkbenchRelation("all", "bank-jia-income-200000", {
          workbench_relation_status: "linked",
          workbench_relation_case_ids: ["case-open-cash"],
          workbench_relation_mode: "manual_confirmed",
          workbench_relation_source: "manual",
          workbench_relation_row_ids: [
            "bank-jia-income-200000",
            "bank-jia-income-100000",
            "bank-jia-expense-300000",
          ],
          cash_pair_linked: true,
          cash_pair_case_id: "case-open-cash",
          cash_closure_linked: false,
        }),
      ],
    });
    renderTurnoverLedgerPage();

    const table = await screen.findByRole("grid", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    expect(within(groupCell).getByText("已配对未结清")).toBeInTheDocument();

    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    const flowRows = within(table).getAllByTestId(/^turnover-flow-row-rel-jiaxiaohua-/);
    expect(within(flowRows[0]).getByText("已配对未结清")).toBeInTheDocument();
    expect(within(flowRows[0]).queryByText("收支闭环")).not.toBeInTheDocument();
  });

  test("does not reload on category updates and downloads a previewed export for the current tab", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    await within(page).findByText("张三");
    const before = requestUrls(fetchMock, "/api/turnover-ledger").length;

    act(() => {
      window.dispatchEvent(new CustomEvent("bankTransactionCategoryUpdated", { detail: { affectedMonths: ["2026-05"] } }));
    });
    expect(requestUrls(fetchMock, "/api/turnover-ledger")).toHaveLength(before);

    await user.click(within(page).getByRole("radio", { name: "公司往来" }));
    await within(page).findByText("云南建设有限公司");
    await user.click(within(page).getByRole("button", { name: "下载表格" }));

    const dialog = await screen.findByRole("dialog", { name: "下载往来款台账" });
    expect(within(dialog).getByRole("button", { name: /下载范围/ })).toHaveTextContent("公司往来");
    expect(await within(dialog).findByText("正式字段预览")).toBeInTheDocument();
    expect(within(dialog).getByText("行类型")).toBeInTheDocument();
    expect(within(dialog).getByText("余额")).toBeInTheDocument();
    expect(within(dialog).getByText("合计")).toBeInTheDocument();
    expect(within(dialog).getByText("对方户名")).toBeInTheDocument();
    expect(within(dialog).getByText("云南建设有限公司")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "确认下载" }));
    await waitFor(() => {
      const request = requestUrls(fetchMock, "/api/turnover-ledger/export").at(-1);
      expect(request?.searchParams.get("family")).toBe("company");
    });
  });

  test("shows backend export row-limit messages inside the export dialog", async () => {
    const user = userEvent.setup();
    installTurnoverLedgerFetch({
      exportDownloadResponse: () => new Response(JSON.stringify({
        error: "turnover_ledger_export_row_limit_exceeded",
        message: "往来款台账导出超过 20000 行，请缩小下载范围后重试。",
        details: { total: 20001, limit: 20000 },
      }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    await within(page).findByText("张三");
    await user.click(within(page).getByRole("button", { name: "下载表格" }));
    const dialog = await screen.findByRole("dialog", { name: "下载往来款台账" });
    await user.click(within(dialog).getByRole("button", { name: "确认下载" }));

    expect(await within(dialog).findByText("往来款台账导出超过 20000 行，请缩小下载范围后重试。")).toBeInTheDocument();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
