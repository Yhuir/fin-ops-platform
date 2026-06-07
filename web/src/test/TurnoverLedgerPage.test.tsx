import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";
import TurnoverLedgerPage from "../pages/TurnoverLedgerPage";
import { expectCustomEventDetailContaining } from "./eventAssertions";

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
    <MuiProviders>
      <SessionContext.Provider value={value}>
        <PageSessionStateProvider>
          <TurnoverLedgerPage />
        </PageSessionStateProvider>
      </SessionContext.Provider>
    </MuiProviders>,
  );
}

function readWebSource(path: string) {
  return readFileSync(resolve(path), "utf8");
}

function requestUrls(fetchMock: ReturnType<typeof installTurnoverLedgerFetch>, pathname: string) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === pathname);
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
  const groups = family === "all" ? allGroups : allGroups.filter((group) => group.family === family);
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
      page_size: 100,
      total: groups.length,
    },
    ...overrides,
  };
}

function installTurnoverLedgerFetch(options: {
  groupedOverrides?: Record<string, unknown>;
  missingDetailForRelationId?: string;
} = {}) {
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
      return new Response(new Blob(["mock xlsx"], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }));
    }
    if (url.pathname === "/api/turnover-ledger/relations/confirm" && method === "POST") {
      return Response.json({ relation_id: "rel-personal-1", status: "confirmed" });
    }
    if (url.pathname === "/api/turnover-ledger/closures/confirm" && method === "POST") {
      return Response.json({
        turnover_relation: {
          relation_id: "turnover_rel_company_closure",
          status: "confirmed",
        },
        workbench_pair_relation: {
          case_id: "turnover:turnover_rel_company_closure",
          relation_mode: "turnover_manual_closure",
        },
        affected_months: ["2026-05"],
      });
    }
    if (url.pathname === "/api/turnover-ledger/relations/rel-personal-1/withdraw" && method === "POST") {
      return Response.json({ relation_id: "rel-personal-1", status: "withdrawn" });
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
      return /DownloadOutlinedIcon|KeyboardArrowDownIcon|KeyboardArrowRightIcon|CloseIcon|TextField|TableCell|TableRow|TableHead|TableBody|TableContainer|DialogTitle|DialogContent|DialogActions|Snackbar|Drawer|Chip|IconButton|Tooltip|Tabs|Tab|FormControlLabel|MenuItem/.test(source)
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

  test("renders grouped MUI table with collapsed summary rows, sticky left cells, and no status column", async () => {
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    expect(within(page).getByRole("heading", { name: "外部往来款管理" })).toBeInTheDocument();
    expect(within(page).queryByText("基于银行明细标签实时汇总外部往来关系，并把已确认关系同步到关联台。")).not.toBeInTheDocument();
    expect(within(page).getByRole("tab", { name: "全部" })).toHaveAttribute("aria-selected", "true");
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

    const table = await within(page).findByRole("table", { name: "往来款左右双栏台账" });
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
    expect(groupCell).toHaveAttribute("rowspan", "1");
    expect(within(groupCell).getByText("张三")).toBeInTheDocument();
    expect(within(groupCell).getByText("个人往来")).toBeInTheDocument();
    expect(within(groupCell).queryByText("待还款合计：800.00")).not.toBeInTheDocument();
    expect(within(groupCell).getByText("待还款合计：")).toBeInTheDocument();
    expect(within(groupCell).getByText("800.00")).toBeInTheDocument();
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");
    expect(within(companyGroupCell).queryByText("待收款合计：2,000.00")).not.toBeInTheDocument();
    expect(within(companyGroupCell).getByText("待收款合计：")).toBeInTheDocument();
    expect(within(companyGroupCell).getByText("2,000.00")).toBeInTheDocument();
    expect(within(groupCell).queryByRole("button", { name: "展开 张三 批次明细" })).not.toBeInTheDocument();
    expect(within(groupCell).queryByRole("button", { name: "展开 张三 流水明细" })).not.toBeInTheDocument();
    expect(within(table).queryByText("招商银行批次账户")).not.toBeInTheDocument();
    expect(within(table).queryByText("明细")).not.toBeInTheDocument();

    const borrowAmountChip = within(table).getByTestId("amount-income-rel-personal-1-borrow");
    expect(borrowAmountChip).toHaveClass("turnover-amount-income");
    expect(within(borrowAmountChip).getByText("收")).toBeInTheDocument();
    expect(within(borrowAmountChip).getByText("1,000.00")).toBeInTheDocument();
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
    const table = await within(page).findByRole("table", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");

    await userEvent.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));

    const flowRows = within(table).getAllByTestId(/^turnover-flow-row-rel-jiaxiaohua-/);
    expect(flowRows).toHaveLength(3);
    expect(within(flowRows[0]).getByRole("checkbox", { name: "选择流水 bank-jia-income-200000" })).toBeInTheDocument();
    expect(within(flowRows[0]).getByRole("button", { name: "编辑流水 bank-jia-income-200000" })).toBeInTheDocument();
    expect(within(table).queryByText("流水")).not.toBeInTheDocument();
    expect(within(table).queryByText("总览不应展示的还款备注")).not.toBeInTheDocument();
    expect(within(flowRows[0]).getByText("200,000.00")).toBeInTheDocument();
    expect(within(flowRows[0]).getByTestId("amount-empty-rel-jiaxiaohua-repayment")).toHaveTextContent("-");
    expect(within(flowRows[1]).getByText("100,000.00")).toBeInTheDocument();
    expect(within(flowRows[1]).getByTestId("amount-empty-rel-jiaxiaohua-repayment")).toHaveTextContent("-");
    expect(within(flowRows[2]).getByTestId("amount-empty-rel-jiaxiaohua-borrow")).toHaveTextContent("-");
    expect(within(flowRows[2]).getByText("300,000.00")).toBeInTheDocument();
    expect(within(table).getByText("200,000.00")).toBeInTheDocument();
    expect(within(table).getByText("100,000.00")).toBeInTheDocument();
    expect(within(table).getAllByText("300,000.00")).toHaveLength(3);
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
    const turnoverListener = vi.fn();
    const workbenchListener = vi.fn();
    window.addEventListener("turnoverRelationUpdated", turnoverListener);
    window.addEventListener("workbenchRelationUpdated", workbenchListener);
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("table", { name: "往来款左右双栏台账" });
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");
    const openButton = within(page).getByRole("button", { name: "确认闭环" });
    expect(openButton).toBeDisabled();

    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 bank-company-expense-1000" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 bank-company-income-1000" }));
    expect(openButton).toBeEnabled();
    await user.click(openButton);

    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    expect(within(drawer).getByRole("heading", { name: "确认外部往来闭环" })).toBeInTheDocument();
    expect(within(drawer).getByText("bank-company-expense-1000")).toBeInTheDocument();
    expect(within(drawer).getByText("bank-company-income-1000")).toBeInTheDocument();
    expect(within(drawer).getByTestId("turnover-closure-delta")).toHaveTextContent("0.00");
    await user.click(within(drawer).getByRole("button", { name: "确定" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/closures/confirm" && init?.method === "POST";
      });
      expect(request).toBeDefined();
      expect(JSON.parse(String(request?.[1]?.body))).toEqual({
        bank_row_ids: ["bank-company-expense-1000", "bank-company-income-1000"],
      });
    });
    await waitFor(() => {
      expectCustomEventDetailContaining(turnoverListener, {
        relationId: "turnover_rel_company_closure",
        action: "manual_closure",
      });
      expectCustomEventDetailContaining(workbenchListener, {
        relationId: "turnover:turnover_rel_company_closure",
        action: "turnover_manual_closure",
      });
    });
    await waitFor(() => {
      expect(openButton).toBeDisabled();
    });
    window.removeEventListener("turnoverRelationUpdated", turnoverListener);
    window.removeEventListener("workbenchRelationUpdated", workbenchListener);
  });

  test("confirms closure when cash direction crosses turnover stage columns", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("table", { name: "往来款左右双栏台账" });
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");

    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 bank-company-borrow-expense-40000" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 bank-company-repayment-income-40000" }));

    const openButton = within(page).getByRole("button", { name: "确认闭环" });
    expect(openButton).toBeEnabled();
    await user.click(openButton);

    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    expect(within(drawer).getByText("支出")).toBeInTheDocument();
    expect(within(drawer).getByText("收入")).toBeInTheDocument();
    expect(within(drawer).getByText("收入合计").nextElementSibling).toHaveTextContent("40,000.00");
    expect(within(drawer).getByText("支出合计").nextElementSibling).toHaveTextContent("40,000.00");
    expect(within(drawer).getByTestId("turnover-closure-delta")).toHaveTextContent("0.00");
    await user.click(within(drawer).getByRole("button", { name: "确定" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/turnover-ledger/closures/confirm" && init?.method === "POST";
      });
      expect(request).toBeDefined();
      expect(JSON.parse(String(request?.[1]?.body))).toEqual({
        bank_row_ids: ["bank-company-borrow-expense-40000", "bank-company-repayment-income-40000"],
      });
    });
  });

  test("blocks cross-group selection and disables drawer confirmation for non-zero difference", async () => {
    const user = userEvent.setup();
    installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("table", { name: "往来款左右双栏台账" });
    const jiaGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(jiaGroupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 bank-jia-income-200000" }));
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");
    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));
    await user.click(within(table).getByRole("checkbox", { name: "选择流水 bank-company-income-1000" }));
    expect(await screen.findByText("一次只能选择同一往来组内的两条流水")).toBeInTheDocument();

    await user.click(within(table).getByRole("checkbox", { name: "选择流水 bank-jia-expense-300000" }));
    await user.click(within(page).getByRole("button", { name: "确认闭环" }));
    const drawer = await screen.findByRole("dialog", { name: "确认外部往来闭环" });
    expect(within(drawer).getByTestId("turnover-closure-delta")).toHaveTextContent("100,000.00");
    expect(within(drawer).getByRole("button", { name: "确定" })).toBeDisabled();
  });

  test("opens the extra drawer from a flow row, hides technical relation ids, saves, and keeps relation actions in the drawer", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    const extraListener = vi.fn();
    window.addEventListener("turnoverLedgerExtraUpdated", extraListener);
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("table", { name: "往来款左右双栏台账" });
    expect(within(table).queryByRole("button", { name: "确认归并" })).not.toBeInTheDocument();

    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("button", { name: "编辑流水 bank-jia-income-200000" }));
    const drawer = await screen.findByRole("dialog", { name: "编辑流水补充信息" });
    expect(within(drawer).getByRole("heading", { name: "编辑流水补充信息" })).toBeInTheDocument();
    expect(within(drawer).getByText("贾小花 / 个人往来 / 2026-02-04 13:20:48")).toBeInTheDocument();
    expect(within(drawer).queryByText(/turnover_rel_/)).not.toBeInTheDocument();
    expect(within(drawer).queryByText("rel-jiaxiaohua")).not.toBeInTheDocument();
    expect(within(drawer).getByText("流水概览")).toBeInTheDocument();
    expect(within(drawer).getByText("补充信息")).toBeInTheDocument();
    expect(within(drawer).getByText("操作记录 / 关系操作")).toBeInTheDocument();
    expect(within(drawer).getAllByText("bank-jia-income-200000").length).toBeGreaterThan(0);
    expect(within(drawer).getAllByText("建行 8106").length).toBeGreaterThan(0);
    expect(within(drawer).getAllByText("收").length).toBeGreaterThan(0);
    expect(within(drawer).getAllByText("200,000.00").length).toBeGreaterThan(0);
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
      });
    });
    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/turnover-ledger").length).toBeGreaterThanOrEqual(2);
    });
    await waitFor(() => {
      expectCustomEventDetailContaining(extraListener, { relationId: "rel-jiaxiaohua" });
    });
    window.removeEventListener("turnoverLedgerExtraUpdated", extraListener);
  });

  test("shows a business error when relation detail disappears after the ledger was rendered", async () => {
    const user = userEvent.setup();
    installTurnoverLedgerFetch({ missingDetailForRelationId: "rel-jiaxiaohua" });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("table", { name: "往来款左右双栏台账" });
    const groupCell = within(table).getByTestId("turnover-group-cell-counterparty:personal:jiaxiaohua");
    await user.click(within(groupCell).getByRole("button", { name: "展开 贾小花 流水明细" }));
    await user.click(within(table).getByRole("button", { name: "编辑流水 bank-jia-income-200000" }));

    const drawer = await screen.findByRole("dialog", { name: "编辑流水补充信息" });
    expect(await within(drawer).findByText("该流水所属往来关系已刷新或不存在，请刷新台账后再编辑。")).toBeInTheDocument();
    expect(within(drawer).queryByText(/turnover_rel_/)).not.toBeInTheDocument();
    expect(within(drawer).queryByText("rel-jiaxiaohua")).not.toBeInTheDocument();
  });

  test("disables turnover write actions while grouped read model is stale", async () => {
    const user = userEvent.setup();
    installTurnoverLedgerFetch({
      groupedOverrides: {
        read_model_status: "stale",
        read_model_stale_reasons: ["source_version_mismatch"],
      },
    });
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    expect(await within(page).findByText("往来款台账正在刷新，当前展示的是非最新数据。")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "确认闭环" })).toBeDisabled();

    const table = await within(page).findByRole("table", { name: "往来款左右双栏台账" });
    const companyGroupCell = within(table).getByTestId("turnover-group-cell-counterparty:company:yunnan");
    await user.click(within(companyGroupCell).getByRole("button", { name: "展开 云南建设有限公司 流水明细" }));

    expect(within(table).getByRole("checkbox", { name: "选择流水 bank-company-expense-1000" })).toBeDisabled();
    expect(within(table).getByRole("button", { name: "编辑流水 bank-company-expense-1000" })).toBeDisabled();
  });

  test("shows bank-detail tags as read-only in turnover management", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    const table = await within(page).findByRole("table", { name: "往来款左右双栏台账" });
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

  test("reloads on category updates and downloads a previewed export for the current tab", async () => {
    const user = userEvent.setup();
    const fetchMock = installTurnoverLedgerFetch();
    renderTurnoverLedgerPage();

    const page = await screen.findByTestId("turnover-ledger-page");
    await within(page).findByText("张三");
    const before = requestUrls(fetchMock, "/api/turnover-ledger").length;

    act(() => {
      window.dispatchEvent(new CustomEvent("bankTransactionCategoryUpdated", { detail: { affectedMonths: ["2026-05"] } }));
    });
    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/turnover-ledger").length).toBeGreaterThan(before);
    });

    await user.click(within(page).getByRole("tab", { name: "公司往来" }));
    await within(page).findByText("云南建设有限公司");
    await user.click(within(page).getByRole("button", { name: "下载表格" }));

    const dialog = await screen.findByRole("dialog", { name: "下载往来款台账" });
    expect(within(dialog).getByRole("combobox", { name: "下载范围" })).toHaveTextContent("公司往来");
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
});
