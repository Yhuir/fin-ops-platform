import { afterEach, describe, expect, test, vi } from "vitest";

import {
  confirmTurnoverRelation,
  downloadTurnoverLedgerExport,
  fetchTurnoverLedger,
  fetchTurnoverLedgerExportPreview,
  fetchTurnoverLedgerGrouped,
  fetchTurnoverRelationExtra,
  fetchTurnoverRelationDetail,
  saveTurnoverRelationExtra,
  withdrawTurnoverRelation,
} from "../features/turnoverLedger/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("turnover ledger API", () => {
  test("maps ledger, detail, confirm, and withdraw responses from snake_case", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/turnover-ledger") {
        expect(url.searchParams.get("family")).toBe("personal");
        expect(url.searchParams.get("status")).toBe("suggested");
        expect(url.searchParams.get("page")).toBe("2");
        expect(url.searchParams.get("page_size")).toBe("50");
        return new Response(JSON.stringify({
          summary: {
            pending_repayment_amount: "1000.00",
            repaid_amount: "200.00",
            pending_collection_amount: "300.00",
            collected_amount: "400.00",
            closed_amount: "600.00",
            suggested_count: 1,
            conflict_count: 2,
            row_count: 3,
          },
          family_summaries: {
            personal: {
              label: "个人往来",
              pending_repayment_amount: "1000.00",
              pending_collection_amount: "300.00",
              closed_amount: "600.00",
              row_count: 3,
            },
          },
          rows: [
            {
              relation_id: "rel-001",
              status: "suggested",
              status_label: "待人工确认",
              row_tone: "warning",
              chips: [{ label: "待确认", tone: "warning" }],
              family: "personal",
              family_label: "个人往来",
              counterparty_name: "张三",
              principal_amount: "1000.00",
              settled_amount: "200.00",
              balance_amount: "800.00",
              first_transaction_at: "2026-05-01 10:00:00",
              last_settlement_at: "2026-05-03 10:00:00",
              bank_account_labels: ["建行 8106"],
              summary_text: "暂借款 / 还款",
              annual_interest_rate: "3.50%",
              loan_days: 2,
              accrued_interest: "0.19",
              sync_to_workbench: false,
              bank_row_ids: ["bank-001", "bank-002"],
              category_codes: ["borrow_in_personal_pending_repayment"],
              business_type: "borrow_in",
            },
          ],
          pagination: {
            page: 2,
            page_size: 50,
            total: 3,
          },
        }), { headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/turnover-ledger/relations/rel-001") {
        return new Response(JSON.stringify({
          relation: {
            relation_id: "rel-001",
            status: "suggested",
            status_label: "",
            row_tone: "",
            counterparty_name: "raw relation",
            bank_row_ids: ["raw-bank"],
          },
          row: {
            relation_id: "rel-001",
            status: "suggested",
            status_label: "待人工确认",
            row_tone: "warning",
            chips: [{ label: "待确认", tone: "warning" }],
            family: "personal",
            family_label: "个人往来",
            counterparty_name: "张三",
            principal_amount: "1000.00",
            settled_amount: "200.00",
            balance_amount: "800.00",
            first_transaction_at: "2026-05-01 10:00:00",
            last_settlement_at: null,
            bank_account_labels: ["建行 8106"],
            summary_text: "暂借款",
            annual_interest_rate: null,
            loan_days: null,
            accrued_interest: null,
            sync_to_workbench: false,
            bank_row_ids: ["bank-001"],
            category_codes: ["borrow_in_personal_pending_repayment"],
            business_type: "borrow_in",
          },
          bank_rows: [
            {
              id: "bank-001",
              trade_time: "2026-05-01 10:00:00",
              counterparty_name_raw: "张三",
              debit_amount: "0.00",
              credit_amount: "1000.00",
              imported_bank_name: "建行",
              imported_bank_last4: "8106",
              summary: "暂借款",
              remark: "借入",
            },
          ],
          audit_history: [{ action: "generated", note: "system" }],
        }), { headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/turnover-ledger/relations/confirm") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toEqual({
          bank_row_ids: ["bank-001"],
          note: "确认归并",
        });
        return new Response(JSON.stringify({
          relation: {
            relation_id: "rel-confirmed",
            status: "confirmed",
          },
        }), {
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.pathname === "/api/turnover-ledger/relations/rel-001/withdraw") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toEqual({ note: "撤销原因" });
        return new Response(JSON.stringify({ relation_id: "rel-001", status: "withdrawn" }), {
          headers: { "Content-Type": "application/json" },
        });
      }
      throw new Error(`Unexpected request ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const ledger = await fetchTurnoverLedger({ family: "personal", status: "suggested", page: 2, pageSize: 50 });
    expect(ledger.summary.pendingRepaymentAmount).toBe("1000.00");
    expect(ledger.familySummaries[0]).toMatchObject({ family: "personal", pendingAmount: "1300.00" });
    expect(ledger.rows[0]).toMatchObject({
      relationId: "rel-001",
      rowTone: "warning",
      bankRowIds: ["bank-001", "bank-002"],
      syncToWorkbench: false,
    });
    expect(ledger.pagination.pageSize).toBe(50);

    const detail = await fetchTurnoverRelationDetail("rel-001");
    expect(detail.relation.relationId).toBe("rel-001");
    expect(detail.relation.counterpartyName).toBe("张三");
    expect(detail.relation.statusLabel).toBe("待人工确认");
    expect(detail.bankRows[0]).toMatchObject({
      id: "bank-001",
      counterpartyName: "张三",
      directionLabel: "收",
      amount: "1000.00",
      bankAccountLabel: "建行 8106",
      summary: "暂借款 / 借入",
    });
    expect(detail.auditHistory[0]).toEqual({ action: "generated", note: "system" });

    await expect(confirmTurnoverRelation({ bankRowIds: ["bank-001"], note: "确认归并" })).resolves.toEqual({
      relationId: "rel-confirmed",
      status: "confirmed",
    });
    await expect(withdrawTurnoverRelation({ relationId: "rel-001", note: "撤销原因" })).resolves.toEqual({
      relationId: "rel-001",
      status: "withdrawn",
    });
  });

  test("reports HTML API responses as a routing problem instead of a JSON parse error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<!DOCTYPE HTML><html><body>Vite fallback</body></html>", {
        status: 200,
        headers: { "Content-Type": "text/html;charset=utf-8" },
      })),
    );

    await expect(fetchTurnoverLedger()).rejects.toThrow("接口返回了 HTML 页面");
  });

  test("maps grouped ledger DTO with stable defaults and string amounts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        expect(url.pathname).toBe("/api/turnover-ledger");
        expect(url.searchParams.get("view")).toBe("grouped");
        expect(url.searchParams.get("family")).toBe("company");
        return new Response(JSON.stringify({
          summary: {
            pending_repayment_amount: "200000.00",
            row_count: 1,
          },
          family_summaries: [
            { family: "company", label: "公司往来", pending_amount: "200000.00", row_count: 1 },
          ],
          groups: [
            {
              group_id: "counterparty:company:梁希涛",
              counterparty_name: "梁希涛",
              family: "company",
              family_label: "公司往来",
              pending_direction: "repayment",
              pending_direction_label: "待还款",
              pending_amount: "200000.00",
              row_span: 3,
              group_tone: "warning",
              summary_row: {
                row_kind: "summary",
                relation_id: "turnover_rel_001",
                status: "suggested",
                status_label: "待人工确认",
                row_tone: "warning",
                borrow_amount: "300000.00",
                borrow_date: "2026-02-04",
                borrow_direction: "income",
                repayment_amount: "300000.00",
                repayment_date: "2026-03-04",
                repayment_direction: "expense",
                balance_amount: "0.00",
                counterparty_bank_name: "中国建设银行",
                repayment_remark: "还暂借款",
                interest_rate_type: "annual",
                interest_rate_value: "0.060000",
                interest_paid_amount: "0.00",
                loan_days: null,
                accrued_interest: "2761.64",
                bank_row_ids: ["bank_001", "bank_002", "bank_003"],
              },
              lot_rows: [
                {
                  row_kind: "lot",
                  relation_id: "turnover_rel_001",
                  lot_id: "lot-001",
                  parent_relation_id: "turnover_rel_001",
                  principal_bank_row_id: "bank_001",
                  settlement_bank_row_ids: ["bank_003"],
                  status: "suggested",
                  status_label: "待人工确认",
                  row_tone: "info",
                  borrow_amount: "200000.00",
                  borrow_date: "2026-02-04",
                  borrow_direction: "income",
                  repayment_amount: "200000.00",
                  repayment_date: "2026-03-04",
                  repayment_direction: "expense",
                  balance_amount: "0.00",
                  counterparty_bank_name: "中国建设银行",
                  repayment_remark: "还暂借款",
                  interest_rate_type: "annual",
                  interest_rate_value: "0.060000",
                  interest_paid_amount: "0.00",
                  loan_days: 28,
                  accrued_interest: "920.55",
                  bank_row_ids: ["bank_001", "bank_003"],
                },
                {
                  row_kind: "lot",
                  relation_id: "turnover_rel_001",
                  lot_id: "lot-002",
                  parent_relation_id: "turnover_rel_001",
                  principal_bank_row_id: "bank_002",
                  settlement_bank_row_ids: ["bank_003"],
                  status: "suggested",
                  status_label: "待人工确认",
                  row_tone: "info",
                  borrow_amount: "100000.00",
                  borrow_date: "2026-02-04",
                  borrow_direction: "income",
                  repayment_amount: "100000.00",
                  repayment_date: "2026-03-04",
                  repayment_direction: "expense",
                  balance_amount: "0.00",
                  counterparty_bank_name: "中国建设银行",
                  repayment_remark: "还暂借款",
                  interest_rate_type: "annual",
                  interest_rate_value: "0.060000",
                  interest_paid_amount: "0.00",
                  loan_days: 28,
                  accrued_interest: "460.27",
                  bank_row_ids: ["bank_002", "bank_003"],
                },
              ],
              rows: [
                {
                  relation_id: "turnover_rel_001",
                  status: "suggested",
                  status_label: "待人工确认",
                  row_tone: "warning",
                  borrow_amount: "200000.00",
                  borrow_date: "2026-02-04",
                  borrow_direction: "income",
                  repayment_amount: "0.00",
                  repayment_date: null,
                  repayment_direction: "expense",
                  counterparty_bank_name: "中国建设银行",
                  repayment_remark: "还暂借款",
                  interest_rate_type: "annual",
                  interest_rate_value: "0.060000",
                  interest_paid_amount: "0.00",
                  loan_days: 97,
                  accrued_interest: "3189.04",
                  balance_amount: "200000.00",
                  bank_row_ids: ["bank_001"],
                },
              ],
            },
          ],
          pagination: {
            page: 1,
            page_size: 100,
            total: 1,
          },
        }), { headers: { "Content-Type": "application/json" } });
      }),
    );

    const ledger = await fetchTurnoverLedgerGrouped({ family: "company" });

    expect(ledger.summary.pendingRepaymentAmount).toBe("200000.00");
    expect(ledger.groups[0]).toMatchObject({
      groupId: "counterparty:company:梁希涛",
      counterpartyName: "梁希涛",
      pendingDirection: "repayment",
      pendingAmount: "200000.00",
      rowSpan: 3,
      groupTone: "warning",
    });
    expect(ledger.groups[0].summaryRow).toMatchObject({
      rowKind: "summary",
      relationId: "turnover_rel_001",
      borrowAmount: "300000.00",
      balanceAmount: "0.00",
      bankRowIds: ["bank_001", "bank_002", "bank_003"],
    });
    expect(ledger.groups[0].lotRows).toHaveLength(2);
    expect(ledger.groups[0].lotRows[0]).toMatchObject({
      rowKind: "lot",
      lotId: "lot-001",
      parentRelationId: "turnover_rel_001",
      principalBankRowId: "bank_001",
      settlementBankRowIds: ["bank_003"],
      borrowAmount: "200000.00",
      balanceAmount: "0.00",
    });
    expect(ledger.groups[0].rows[0]).toMatchObject({
      relationId: "turnover_rel_001",
      borrowAmount: "200000.00",
      balanceAmount: "200000.00",
      repaymentAmount: "0.00",
      interestRateType: "annual",
      interestRateValue: "0.060000",
      interestPaidDate: null,
      interestPaymentMethod: "",
      note: "",
      bankRowIds: ["bank_001"],
    });
  });

  test("uses first grouped rows entry as summaryRow when backend has legacy rows only", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        groups: [
          {
            group_id: "counterparty:personal:张三",
            row_span: 1,
            rows: [
              {
                relation_id: "legacy-rel-001",
                borrow_amount: "1000.00",
                balance_amount: "800.00",
                bank_row_ids: ["bank-legacy-001"],
              },
            ],
          },
        ],
      }), { headers: { "Content-Type": "application/json" } })),
    );

    const ledger = await fetchTurnoverLedgerGrouped();

    expect(ledger.groups[0].summaryRow).toMatchObject({
      relationId: "legacy-rel-001",
      rowKind: "summary",
      borrowAmount: "1000.00",
      balanceAmount: "800.00",
    });
    expect(ledger.groups[0].lotRows).toEqual([]);
  });

  test("maps extra GET and PUT payloads", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (init?.method === "PUT") {
        expect(url.pathname).toBe("/api/turnover-ledger/relations/rel-001/extra");
        expect(JSON.parse(String(init.body))).toEqual({
          interest_rate_type: "monthly",
          interest_rate_value: "0.005000",
          interest_paid_amount: "100.00",
          interest_paid_date: "2026-05-10",
          interest_payment_method: "银行转账",
          note: "已线下确认",
        });
        return new Response(JSON.stringify({
          extra: {
            relation_id: "rel-001",
            interest_rate_type: "monthly",
            interest_rate_value: "0.005000",
            interest_paid_amount: "100.00",
            interest_paid_date: "2026-05-10",
            interest_payment_method: "银行转账",
            note: "已线下确认",
            updated_at: "2026-05-12T10:00:00+08:00",
            updated_by: "user",
          },
          row: {
            relation_id: "rel-001",
            borrow_amount: "2000.00",
            accrued_interest: "9.67",
          },
        }), { headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({
        relation_id: "rel-001",
        interest_rate_type: "annual",
        interest_rate_value: "0.060000",
        interest_paid_amount: "0.00",
        interest_paid_date: null,
        interest_payment_method: "",
        note: "旧备注",
        updated_at: "2026-05-11T10:00:00+08:00",
        updated_by: "user",
      }), { headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchTurnoverRelationExtra("rel-001")).resolves.toMatchObject({
      relationId: "rel-001",
      interestRateType: "annual",
      interestRateValue: "0.060000",
      interestPaidAmount: "0.00",
      note: "旧备注",
    });

    const saved = await saveTurnoverRelationExtra("rel-001", {
      interestRateType: "monthly",
      interestRateValue: "0.005000",
      interestPaidAmount: "100.00",
      interestPaidDate: "2026-05-10",
      interestPaymentMethod: "银行转账",
      note: "已线下确认",
    });
    expect(saved.extra.interestRateType).toBe("monthly");
    expect(saved.row?.accruedInterest).toBe("9.67");
  });

  test("maps export preview and downloads xlsx as Blob without JSON parsing", async () => {
    const exportJsonSpy = vi.fn(() => {
      throw new Error("download response should not be parsed as JSON");
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/turnover-ledger/export-preview") {
        expect(url.searchParams.get("family")).toBe("business");
        return new Response(JSON.stringify({
          file_name: "往来款台账-业务往来-2026-05-12.xlsx",
          scope_label: "业务往来",
          summary: {
            row_count: 1,
            pending_repayment_amount: "0.00",
            pending_collection_amount: "8000.00",
          },
          columns: ["序号", "往来大类", "对方户名"],
          rows: [
            {
              sequence_no: 1,
              family_label: "业务往来",
              counterparty_name: "昆明客户",
              pending_repayment_amount: "0.00",
              pending_collection_amount: "8000.00",
              borrow_amount: "8000.00",
              borrow_date: "2026-05-01",
              repayment_amount: "0.00",
              repayment_date: null,
              counterparty_bank_name: "招商银行",
              repayment_remark: "",
              interest_rate_type: "none",
              interest_rate_value: "0.000000",
              interest_paid_amount: "0.00",
              loan_days: null,
              accrued_interest: "0.00",
              interest_paid_date: null,
              interest_payment_method: "",
              note: "",
              status_label: "待人工确认",
              row_type: "lot",
              lot_id: "lot-business-001",
              balance_amount: "8000.00",
            },
          ],
        }), { headers: { "Content-Type": "application/json" } });
      }
      return {
        ok: true,
        status: 200,
        headers: {
          get(name: string) {
            if (name.toLowerCase() === "content-type") {
              return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
            }
            if (name.toLowerCase() === "content-disposition") {
              return "attachment; filename=\"turnover.xlsx\"";
            }
            return null;
          },
        },
        blob: async () => new Blob(["xlsx-bytes"]),
        text: async () => {
          throw new Error("download response should not be parsed as text");
        },
        json: exportJsonSpy,
      } as unknown as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    const preview = await fetchTurnoverLedgerExportPreview({ family: "business" });
    expect(preview.fileName).toBe("往来款台账-业务往来-2026-05-12.xlsx");
    expect(preview.summary.pendingCollectionAmount).toBe("8000.00");
    expect(preview.rows[0]).toMatchObject({
      sequenceNo: 1,
      counterpartyName: "昆明客户",
      pendingCollectionAmount: "8000.00",
      interestRateType: "none",
      loanDays: null,
      rowType: "lot",
      lotId: "lot-business-001",
      balanceAmount: "8000.00",
    });

    const downloaded = await downloadTurnoverLedgerExport({ family: "business" });
    expect(downloaded.fileName).toBe("turnover.xlsx");
    expect(downloaded.blob).toBeInstanceOf(Blob);
    expect(downloaded.blob.size).toBeGreaterThan(0);
    expect(exportJsonSpy).not.toHaveBeenCalled();
  });
});
