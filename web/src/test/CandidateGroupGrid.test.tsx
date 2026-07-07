import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { useState } from "react";

import CandidateGroupGrid from "../components/workbench/CandidateGroupGrid";
import CandidateGroupCell from "../components/workbench/CandidateGroupCell";
import WorkbenchRecordCard from "../components/workbench/WorkbenchRecordCard";
import { createEmptyWorkbenchZoneDisplayState } from "../features/workbench/groupDisplayModel";
import { getWorkbenchColumns, getWorkbenchPaneGridStyle } from "../features/workbench/tableConfig";
import type { WorkbenchCandidateGroup, WorkbenchRecord } from "../features/workbench/types";
import { installMockApiFetch } from "./apiMock";
import { expectCustomEventDetailContaining } from "./eventAssertions";
import { renderWorkbenchPage } from "./workbenchRenderHelpers";

describe("Workbench candidate grouping layout", () => {
  const invoiceColumns = getWorkbenchColumns("invoice");
  const invoiceGridStyle = getWorkbenchPaneGridStyle("invoice", undefined, true);
  const appStyles = readFileSync("src/app/styles.css", "utf8");

  function createInvoiceRecord(id: string, invoiceNo: string): WorkbenchRecord {
    return {
      id,
      caseId: "CASE-SHEET-001",
      recordType: "invoice",
      label: "进项发票",
      status: "待匹配",
      statusCode: "pending_match",
      statusTone: "warn",
      exceptionHandled: false,
      amount: "100.00",
      counterparty: "测试供应商",
      tableValues: {
        sellerName: "测试供应商",
        sellerTaxId: "91330100TEST0001",
        buyerName: "云南溯源科技有限公司",
        buyerTaxId: "915300007194052520",
        invoiceCode: "032002600111",
        invoiceNo,
        issueDate: "2026-04-14",
        amount: "100.00",
        taxRate: "13%",
        taxAmount: "13.00",
        grossAmount: "113.00",
        invoiceType: "进",
      },
      detailFields: [],
      actionVariant: "detail-only",
      availableActions: ["detail"],
    };
  }

  function createBankRecord(): WorkbenchRecord {
    return {
      id: "bank-text-fields-001",
      caseId: "CASE-TEXT-FIELDS-001",
      recordType: "bank",
      label: "收入",
      status: "待匹配",
      statusCode: "pending_match",
      statusTone: "warn",
      exceptionHandled: false,
      amount: "600.00",
      counterparty: "测试客户",
      tableValues: {
        counterparty: "测试客户",
        amount: "600.00",
        direction: "收入",
        paymentAccount: "建设银行 8106",
        transactionTime: "2026-03-20 12:15:00",
        invoiceRelationStatus: "待匹配",
        note: "摘要：电子转账\n备注：代购公车款\n用途：货款",
        loanRepaymentDate: "--",
      },
      detailFields: [],
      actionVariant: "detail-only",
      availableActions: ["detail"],
      bankTextFields: [
        { label: "摘要", value: "电子转账" },
        { label: "备注", value: "代购公车款" },
        { label: "用途", value: "货款" },
      ],
    } as WorkbenchRecord;
  }

  function createSourceBankRecord(id: string, amount: string, sourceOaId: string): WorkbenchRecord {
    const baseRecord = createBankRecord();
    return {
      ...baseRecord,
      id,
      caseId: "CASE-MULTI-OA-ATTACHMENT",
      amount,
      sourceOaId,
      counterparty: "云南辰飞机电工程有限公司",
      tableValues: {
        ...baseRecord.tableValues,
        counterparty: "云南辰飞机电工程有限公司",
        amount,
        direction: "支出",
        note: "报销",
      },
    } as WorkbenchRecord;
  }

  function createOaRecord(id: string, applicant: string, amount: string): WorkbenchRecord {
    return {
      id,
      caseId: "CASE-MULTI-OA-ATTACHMENT",
      recordType: "oa",
      label: "日常报销",
      status: "完全关联",
      statusCode: "fully_linked",
      statusTone: "success",
      exceptionHandled: false,
      amount,
      counterparty: "云南溯源科技有限公司",
      tableValues: {
        applicant,
        projectName: applicant === "刘晓宇" ? "云南溯源科技" : "大理卷烟厂动力车间中水处理系统升级改造项目",
        applicationType: "日常报销",
        reconciliationStatus: "完全关联",
        amount,
        applicationTime: "2026-01-28",
      },
      detailFields: [],
      actionVariant: "detail-only",
      availableActions: ["detail"],
    };
  }

  function createAttachmentInvoiceRecord(id: string, sellerName: string, amount: string, sourceOaId: string): WorkbenchRecord {
    return {
      id,
      caseId: "CASE-MULTI-OA-ATTACHMENT",
      recordType: "invoice",
      sourceKind: "oa_attachment_invoice",
      sourceOaId,
      label: "进项发票",
      status: "OA附件",
      statusCode: "oa_attachment_invoice",
      statusTone: "info",
      exceptionHandled: false,
      amount,
      counterparty: sellerName,
      tableValues: {
        sellerName,
        sellerTaxId: "91300000TEST",
        buyerName: "云南溯源科技有限公司",
        buyerTaxId: "915300007194052520",
        invoiceCode: "--",
        invoiceNo: id,
        issueDate: "2026-01-28",
        amount,
        taxRate: "--",
        taxAmount: "--",
        grossAmount: amount,
        invoiceType: "进",
      },
      detailFields: [],
      actionVariant: "detail-only",
      availableActions: ["detail"],
    };
  }

  function createTruncatedManualInvoiceGroup(): WorkbenchCandidateGroup {
    const invoiceRows = [
      createInvoiceRecord("manual-inv-many-1", "MANUAL-MANY-001"),
      createInvoiceRecord("manual-inv-many-2", "MANUAL-MANY-002"),
      createInvoiceRecord("manual-inv-many-3", "MANUAL-MANY-003"),
    ];
    return {
      id: "case:CASE-MANUAL-INVOICE-MANY",
      groupType: "open",
      rawGroupType: "source_linked",
      matchConfidence: "high",
      reason: "manual_invoice_source_relation",
      rows: {
        oa: [],
        bank: [],
        invoice: invoiceRows,
      },
      rowCounts: {
        oa: 0,
        bank: 0,
        invoice: 5,
        rows: 5,
      },
    };
  }

  function createNoOaBankRecord(id: string, counterparty: string, amount: string, note: string): WorkbenchRecord {
    return {
      id,
      recordType: "bank",
      sourceKind: id.includes("summary") ? "no_oa_bank_batch_summary" : undefined,
      label: id.includes("summary") ? "免OA批次" : "支取",
      status: "免OA批次",
      statusCode: "no_oa_bank_batch",
      statusTone: "success",
      exceptionHandled: false,
      amount,
      counterparty,
      tableValues: {
        transactionTime: "2026-03-08 09:00:00",
        direction: "支出",
        amount,
        debitAmount: amount,
        creditAmount: "--",
        counterparty,
        paymentAccount: "建设银行 8106",
        invoiceRelationStatus: "免OA批次",
        paymentOrReceiptTime: "2026-03-08 09:00:00",
        note,
        loanRepaymentDate: "--",
      },
      detailFields: [],
      actionVariant: id.includes("summary") ? "bank-review" : "detail-only",
      availableActions: id.includes("summary") ? ["detail", "withdraw_no_oa_batch"] : ["detail"],
      specialMetadata: id.includes("summary")
        ? { source_batch_id: "NOOA-202603-FEE", batch_version: 7 }
        : undefined,
    };
  }

  function createNoOaCollapsedGroup(): WorkbenchCandidateGroup {
    const summary = createNoOaBankRecord("nooa-summary-NOOA-202603-FEE", "免OA手续费批次", "30.00", "2 条手续费");
    return {
      id: "no-oa-bank-batch:NOOA-202603-FEE",
      groupType: "manual_confirmed",
      matchConfidence: "high",
      reason: "免OA手续费批次",
      relationMode: "no_oa_bank_batch",
      displayMode: "collapsed_summary",
      defaultCollapsed: true,
      summaryRow: summary,
      rows: {
        oa: [],
        bank: [summary],
        invoice: [],
      },
      rowCounts: {
        oa: 0,
        bank: 2,
        invoice: 0,
        rows: 2,
      },
      displayRowCounts: {
        oa: 0,
        bank: 1,
        invoice: 0,
        rows: 1,
      },
      collapsedRows: {
        bank: [
          createNoOaBankRecord("bk-nooa-fee-001", "建设银行手续费", "10.00", "摘要：账户管理费"),
          createNoOaBankRecord("bk-nooa-fee-002", "网银服务费", "20.00", "摘要：企业网银年费"),
        ],
      },
    };
  }

  function createBankFlowCollapsedGroup(): WorkbenchCandidateGroup {
    const summary = createNoOaBankRecord("bank-flow-summary-BATCH-202603-FEE", "流水规则手续费批次", "124.50", "15 条手续费");
    return {
      ...createNoOaCollapsedGroup(),
      id: "bank-flow-rule-batch:BATCH-202603-FEE",
      relationMode: "bank_flow_rule_batch",
      reason: "流水规则手续费批次",
      summaryRow: summary,
      rows: {
        oa: [],
        bank: [summary],
        invoice: [],
      },
      rowCounts: {
        oa: 0,
        bank: 15,
        invoice: 0,
        rows: 15,
      },
      displayRowCounts: {
        oa: 0,
        bank: 1,
        invoice: 0,
        rows: 1,
      },
      collapsedRows: {
        bank: [
          createNoOaBankRecord("bk-bank-flow-fee-001", "建设银行手续费", "8.30", "摘要：账户管理费"),
          createNoOaBankRecord("bk-bank-flow-fee-002", "网银服务费", "7.20", "摘要：企业网银年费"),
        ],
      },
      collapsedRowCounts: {
        bank: 15,
      },
    };
  }

  function createBankFlowPlaceholderGroup(): WorkbenchCandidateGroup {
    const group = createBankFlowCollapsedGroup();
    const placeholder: WorkbenchRecord = {
      ...createNoOaBankRecord("bk-bank-flow-placeholder-001", "占位明细", "--", "--"),
      label: "--",
      status: "待处理",
      statusCode: "pending_match",
      statusTone: "warn",
      amount: "--",
      tableValues: {
        transactionTime: "--",
        direction: "--",
        amount: "--",
        debitAmount: "--",
        creditAmount: "--",
        counterparty: "占位明细",
        paymentAccount: "--",
        invoiceRelationStatus: "待处理",
        note: "--",
        loanRepaymentDate: "--",
      },
      specialMetadata: undefined,
    };
    return {
      ...group,
      collapsedRows: {
        bank: [placeholder],
      },
      collapsedRowCounts: {
        bank: 15,
      },
    };
  }

  function createBankFlowFullDetailGroup(): WorkbenchCandidateGroup {
    const group = createBankFlowCollapsedGroup();
    const collapsedRows = Array.from({ length: 15 }, (_, index) => {
      const itemNumber = index + 1;
      return createNoOaBankRecord(
        `bk-bank-flow-fee-${String(itemNumber).padStart(3, "0")}`,
        itemNumber === 1 ? "建设银行手续费" : `网银服务费${itemNumber}`,
        (8.3 + index).toFixed(2),
        `摘要：手续费${itemNumber}`,
      );
    });
    return {
      ...group,
      collapsedRows: {
        bank: collapsedRows,
      },
      collapsedRowCounts: {
        bank: 15,
      },
    };
  }

  function createTurnoverBankRecord(
    id: string,
    counterparty: string,
    amount: string,
    direction: "收入" | "支出",
    transactionTime: string,
    note: string,
  ): WorkbenchRecord {
    const baseRecord = createBankRecord();
    return {
      ...baseRecord,
      id,
      caseId: "CASE-TURNOVER-202605",
      label: direction,
      status: "完全关联",
      statusCode: "fully_linked",
      statusTone: "success",
      amount,
      counterparty,
      tableValues: {
        ...baseRecord.tableValues,
        counterparty,
        amount,
        direction,
        transactionTime,
        paymentAccount: "建设银行 8106",
        note,
        loanRepaymentDate: "--",
      },
    } as WorkbenchRecord;
  }

  function createTruncatedTurnoverGroup(): WorkbenchCandidateGroup {
    return {
      id: "case:turnover:turnover_rel_36266274e9235566",
      groupType: "open",
      rawGroupType: "candidate",
      matchConfidence: "high",
      reason: "existing_case_group",
      relationMode: "manual_confirmed",
      rows: {
        oa: [createOaRecord("oa-turnover-20260522", "刘际涛", "150000")],
        bank: [
          createTurnoverBankRecord("txn_imported_0105", "杨丽萍", "150000", "支出", "2026-05-22 14:40:07", "还5月9-11日借入款"),
          createTurnoverBankRecord("txn_imported_0077", "杨丽萍", "50000", "收入", "2026-05-11 09:06:40", "暂借款"),
          createTurnoverBankRecord("txn_imported_0076", "杨丽萍", "50000", "收入", "2026-05-10 09:45:04", "暂借款"),
        ],
        invoice: [],
      },
      rowCounts: {
        oa: 1,
        bank: 4,
        invoice: 0,
        rows: 5,
      },
    };
  }

  function createFullTurnoverGroup(): WorkbenchCandidateGroup {
    const group = createTruncatedTurnoverGroup();
    return {
      ...group,
      rows: {
        ...group.rows,
        bank: [
          ...group.rows.bank,
          createTurnoverBankRecord("txn_imported_0058", "杨丽萍 5月9隐藏流水", "50000", "收入", "2026-05-09 10:14:06", "暂借款"),
        ],
      },
    };
  }

  function createEtcInvoiceRecord(id: string, invoiceNo: string, amount: string): WorkbenchRecord {
    return {
      id,
      recordType: "invoice",
      sourceKind: "etc_invoice",
      label: "ETC发票",
      status: "ETC批次",
      statusCode: "etc_invoice",
      statusTone: "info",
      exceptionHandled: false,
      amount,
      counterparty: "云南昆玉高速公路开发有限公司",
      tableValues: {
        sellerName: "云南昆玉高速公路开发有限公司",
        sellerTaxId: "91530000ETC001",
        buyerName: "云南溯源科技有限公司",
        buyerTaxId: "915300007194052520",
        invoiceCode: "--",
        invoiceNo,
        issueDate: "2026-01-04",
        amount,
        taxRate: "--",
        taxAmount: "--",
        grossAmount: amount,
        invoiceType: "进",
      },
      detailFields: [],
      actionVariant: "detail-only",
      availableActions: ["detail"],
    };
  }

  function createEtcCollapsedGroup(): WorkbenchCandidateGroup {
    const summary: WorkbenchRecord = {
      id: "etc-summary-ETC-OA-20260215-154900",
      recordType: "invoice",
      sourceKind: "etc_invoice_summary",
      label: "ETC批次",
      status: "ETC批次",
      statusCode: "etc_invoice_summary",
      statusTone: "info",
      exceptionHandled: false,
      amount: "1546.50",
      counterparty: "云南昆玉高速公路开发有限公司",
      tableValues: {
        sellerName: "云南昆玉高速公路开发有限公司",
        sellerTaxId: "--",
        buyerName: "云南溯源科技有限公司",
        buyerTaxId: "915300007194052520",
        invoiceCode: "--",
        invoiceNo: "ETC-OA-20260215-154900",
        issueDate: "2025-12-29 至 2026-01-27",
        amount: "1546.50",
        taxRate: "--",
        taxAmount: "--",
        grossAmount: "1546.50",
        invoiceType: "ETC批次",
      },
      detailFields: [],
      actionVariant: "detail-only",
      availableActions: ["detail"],
    };
    return {
      id: "case:ETC-OA-20260215-154900",
      groupType: "paired",
      matchConfidence: "high",
      reason: "ETC批次",
      displayMode: "collapsed_summary",
      defaultCollapsed: true,
      rows: {
        oa: [],
        bank: [],
        invoice: [summary],
      },
      rowCounts: {
        oa: 0,
        bank: 0,
        invoice: 2,
        rows: 2,
      },
      displayRowCounts: {
        oa: 0,
        bank: 0,
        invoice: 1,
        rows: 1,
      },
      collapsedRows: {
        invoice: [
          createEtcInvoiceRecord("etc-inv-001", "ETC-001", "23.50"),
          createEtcInvoiceRecord("etc-inv-002", "ETC-002", "21.52"),
        ],
      },
      collapsedRowCounts: {
        invoice: 2,
      },
    };
  }

  function renderNoOaGrid(group: WorkbenchCandidateGroup = createNoOaCollapsedGroup()) {
    return render(
      <CandidateGroupGrid
        canMutateData
        displayState={createEmptyWorkbenchZoneDisplayState()}
        getRowState={() => "idle"}
        groups={[group]}
        onClearPaneSearch={() => undefined}
        onClosePaneSearch={() => undefined}
        onColumnFilterChange={() => undefined}
        onOpenDetail={() => undefined}
        onPaneSearchQueryChange={() => undefined}
        onPaneTimeFilterChange={() => undefined}
        onReorderPaneColumns={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        onTogglePaneSearch={() => undefined}
        onTogglePaneSort={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: [] },
          { id: "bank", title: "银行流水", rows: group.rows.bank },
          { id: "invoice", title: "进销项发票", rows: [] },
        ]}
        rowTemplateColumns="1fr 1fr 1fr"
        zoneId="paired"
      />,
    );
  }

  test("shows server total pane counts instead of the currently loaded page row count", () => {
    const group = createNoOaCollapsedGroup();
    render(
      <CandidateGroupGrid
        canMutateData
        displayState={createEmptyWorkbenchZoneDisplayState()}
        getRowState={() => "idle"}
        groups={[group]}
        onOpenDetail={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: [], totalRows: 24 },
          { id: "bank", title: "银行流水", rows: group.rows.bank, totalRows: 237 },
          { id: "invoice", title: "进销项发票", rows: [], totalRows: 91 },
        ]}
        rowTemplateColumns="1fr 1fr 1fr"
        zoneId="paired"
      />,
    );

    expect(screen.getByText("24 条")).toBeInTheDocument();
    expect(screen.getByText("237 条")).toBeInTheDocument();
    expect(screen.getByText("91 条")).toBeInTheDocument();
  });

  function buildNoOaWorkbenchPayload() {
    return {
      month: "all",
      oa_status: { code: "ready", message: "OA 已同步" },
      summary: {
        oa_count: 0,
        bank_count: 3,
        invoice_count: 0,
        paired_count: 1,
        open_count: 0,
        exception_count: 0,
        zone_counts: {
          paired: { groups: 1, oa: 0, bank: 3, invoice: 0, rows: 3 },
          open: { groups: 0, oa: 0, bank: 0, invoice: 0, rows: 0 },
        },
      },
      invoice_inventory: {},
      paired: {
        groups: [
          {
            group_id: "no-oa-bank-batch:NOOA-202603-FEE",
            group_type: "manual_confirmed",
            match_confidence: "high",
            reason: "免OA手续费批次",
            relation_mode: "no_oa_bank_batch",
            display_mode: "collapsed_summary",
            default_collapsed: true,
            oa_rows: [],
            bank_rows: [
              {
                id: "nooa-summary-NOOA-202603-FEE",
                type: "bank",
                source_kind: "no_oa_bank_batch_summary",
                trade_time: "2026-03",
                direction: "支出",
                debit_amount: "30.00",
                credit_amount: "",
                counterparty_name: "免OA手续费批次",
                payment_account_label: "建设银行 8106",
                invoice_relation: { code: "no_oa_bank_batch", label: "免OA批次", tone: "success" },
                available_actions: ["detail", "withdraw_no_oa_batch"],
                special_metadata: {
                  source_batch_id: "NOOA-202603-FEE",
                  batch_version: 7,
                },
              },
            ],
            invoice_rows: [],
            collapsed_rows: {
              bank: [
                {
                  id: "bk-nooa-fee-001",
                  type: "bank",
                  trade_time: "2026-03-08 09:00:00",
                  direction: "支出",
                  debit_amount: "10.00",
                  credit_amount: "",
                  counterparty_name: "建设银行手续费",
                  payment_account_label: "建设银行 8106",
                  invoice_relation: { code: "no_oa_bank_batch", label: "免OA批次", tone: "success" },
                  bank_text_fields: [{ label: "摘要", value: "账户管理费" }],
                  available_actions: ["detail"],
                },
              ],
            },
          },
        ],
      },
      open: { groups: [] },
    };
  }

  function buildBankFlowRuleWorkbenchPayload() {
    const payload = buildNoOaWorkbenchPayload();
    const group = payload.paired.groups[0];
    group.group_id = "bank-flow-rule-batch:BANKFLOW-202603-FEE";
    group.reason = "流水规则手续费批次";
    group.relation_mode = "bank_flow_rule_batch";
    const summaryRow = group.bank_rows[0];
    summaryRow.id = "bank-flow-summary-BANKFLOW-202603-FEE";
    summaryRow.source_kind = "bank_flow_rule_batch_summary";
    summaryRow.counterparty_name = "流水规则手续费批次";
    summaryRow.invoice_relation = { code: "bank_flow_rule_batch", label: "流水规则批次", tone: "success" };
    summaryRow.special_metadata = {
      source_batch_id: "BANKFLOW-202603-FEE",
      batch_version: 7,
      relation_mode: "bank_flow_rule_batch",
    };
    return payload;
  }

  function mockWorkbenchPageFetch(payload = buildNoOaWorkbenchPayload()) {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/workbench") {
        return new Response(JSON.stringify(payload), { status: 200 });
      }
      if (url.pathname === "/api/workbench/summary") {
        return new Response(
          JSON.stringify({
            month: payload.month,
            summary: payload.summary,
            oa_status: payload.oa_status,
            invoice_inventory: payload.invoice_inventory,
            read_model_status: "fresh",
            generated_at: "2026-05-22T09:30:00+08:00",
          }),
          { status: 200 },
        );
      }
      if (url.pathname === "/api/workbench/groups") {
        const zone = url.searchParams.get("zone") === "open" ? "open" : "paired";
        const groups = payload[zone].groups;
        return new Response(
          JSON.stringify({
            month: payload.month,
            zone,
            page: 1,
            page_size: 50,
            total: groups.length,
            row_counts: zone === "paired"
              ? { oa: 0, bank: 3, invoice: 0, rows: 3 }
              : { oa: 0, bank: 0, invoice: 0, rows: 0 },
            has_more: false,
            groups,
            read_model_status: "fresh",
          }),
          { status: 200 },
        );
      }
      if (url.pathname === "/api/workbench/ignored") {
        return new Response(JSON.stringify({ month: url.searchParams.get("month") ?? "all", rows: [] }), { status: 200 });
      }
      if (url.pathname === "/api/workbench/settings") {
        return new Response(
          JSON.stringify({
            projects: { active: [], completed: [], completed_project_ids: [] },
            bank_account_mappings: [],
          }),
          { status: 200 },
        );
      }
      if (url.pathname === "/api/oa-sync/status") {
        return new Response(
          JSON.stringify({
            status: "synced",
            message: "OA 已同步",
            dirty_scopes: [],
            changed_scopes: [],
            last_seen_change_at: null,
            last_synced_at: "2026-04-01T12:00:00+08:00",
            lag_seconds: 0,
            failed_event_count: 0,
            version: 0,
          }),
          { status: 200 },
        );
      }
      if (url.pathname === "/api/bank-flow-rule-batches/BANKFLOW-202603-FEE/withdraw") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toEqual({
          expected_version: 7,
          reason: "由关联台撤回流水规则批次",
        });
        return new Response(
          JSON.stringify({
            batch: null,
            affected_months: ["2026-03"],
            workbench_rebuild_queued: true,
            results: [],
          }),
          { status: 200 },
        );
      }
      if (url.pathname === "/api/workbench/actions/cancel-link") {
        throw new Error("ordinary cancel-link must not be called for bank-flow rule summaries");
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });
    return fetchMock;
  }

  function getZoneGroupOrder(zone: HTMLElement) {
    return Array.from(zone.querySelectorAll<HTMLElement>(".candidate-grid-body > [data-testid^='candidate-group-']")).map(
      (element) => element.getAttribute("data-testid") ?? "",
    );
  }

  function getCssRuleBody(selector: string) {
    const selectorIndex = appStyles.indexOf(selector);
    expect(selectorIndex).toBeGreaterThanOrEqual(0);
    const openBraceIndex = appStyles.indexOf("{", selectorIndex);
    const closeBraceIndex = appStyles.indexOf("}", openBraceIndex);
    expect(openBraceIndex).toBeGreaterThan(selectorIndex);
    expect(closeBraceIndex).toBeGreaterThan(openBraceIndex);
    return appStyles.slice(openBraceIndex + 1, closeBraceIndex);
  }

  function countInitialWorkbenchPageRequests(fetchMock: ReturnType<typeof mockWorkbenchPageFetch>) {
    return fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(String(input), "http://localhost");
      return url.pathname === "/api/workbench/summary" || url.pathname === "/api/workbench/groups";
    }).length;
  }

  function getStandaloneCssRuleBody(selector: string, occurrence = 0) {
    let selectorIndex = -1;
    let searchFrom = 0;
    for (let index = 0; index <= occurrence; index += 1) {
      selectorIndex = appStyles.indexOf(`${selector} {`, searchFrom);
      searchFrom = selectorIndex + 1;
    }
    expect(selectorIndex).toBeGreaterThanOrEqual(0);
    const openBraceIndex = appStyles.indexOf("{", selectorIndex);
    const closeBraceIndex = appStyles.indexOf("}", openBraceIndex);
    expect(openBraceIndex).toBeGreaterThan(selectorIndex);
    expect(closeBraceIndex).toBeGreaterThan(openBraceIndex);
    return appStyles.slice(openBraceIndex + 1, closeBraceIndex);
  }

  test("allows invoice candidate rows to grow vertically while long text stays inside cells", () => {
    expect(getCssRuleBody(".record-card-invoice.record-card-has-action")).not.toMatch(/\bheight\s*:/);
    expect(getStandaloneCssRuleBody(".record-card-cell", 1)).toMatch(/overflow:\s*hidden/);
    expect(getStandaloneCssRuleBody(".record-card-cell-content")).not.toMatch(/(?:^|\n)\s*height\s*:\s*100%/);
    expect(getStandaloneCssRuleBody(".record-card-cell-content")).toMatch(/overflow:\s*hidden/);
    expect(getStandaloneCssRuleBody(".record-card-cell.column-compact .cell-text-value-full")).toMatch(/overflow-wrap:\s*anywhere/);
    expect(getStandaloneCssRuleBody(".record-card-cell.column-compact .cell-text-value-full")).toMatch(/word-break:\s*break-word/);
  });

  test("keeps candidate expand controls in normal flow so they do not cover row text", () => {
    const controlRule = getCssRuleBody(".candidate-group-collapse-control");

    expect(controlRule).toMatch(/margin:\s*6px 10px 4px;/);
    expect(controlRule).toMatch(/white-space:\s*normal;/);
    expect(controlRule).not.toMatch(/\bposition:\s*absolute/);
    expect(controlRule).not.toMatch(/\btop\s*:/);
    expect(controlRule).not.toMatch(/\bleft\s*:/);
  });

  test("shows zone titles with total item counts instead of group counts", async () => {
    mockWorkbenchPageFetch();
    renderWorkbenchPage();

    expect(await screen.findByText("已配对 3 项")).toBeInTheDocument();
    expect(screen.getByText("未配对 0 项")).toBeInTheDocument();
    expect(screen.queryByText("已配对 1 组")).not.toBeInTheDocument();
  });

  test("renders an explicit expand control when summary response truncates ordinary visible rows", async () => {
    const group = createTruncatedManualInvoiceGroup();
    const ensureGroupDetail = vi.fn().mockResolvedValue(undefined);

    render(
      <CandidateGroupGrid
        canMutateData
        getRowState={() => "idle"}
        groups={[group]}
        onEnsureGroupDetail={ensureGroupDetail}
        onOpenDetail={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: group.rows.oa },
          { id: "bank", title: "银行流水", rows: group.rows.bank },
          { id: "invoice", title: "进销项发票", rows: group.rows.invoice },
        ]}
        rowTemplateColumns="1fr 8px 1fr 8px 1fr"
        sourceGroups={[group]}
        zoneId="open"
      />,
    );

    const expandButton = screen.getByRole("button", {
      name: "展开全部发票，当前显示 3 张，共 5 张",
    });

    expect(expandButton).toHaveTextContent("还有 2 张，展开");
    expect(ensureGroupDetail).not.toHaveBeenCalled();

    fireEvent.click(expandButton);

    await waitFor(() => expect(ensureGroupDetail).toHaveBeenCalledWith("open", "case:CASE-MANUAL-INVOICE-MANY"));
  });

  test("auto-loads complete collapsed summary detail when summary response truncates collapsed rows", async () => {
    const group = createBankFlowCollapsedGroup();
    const ensureGroupDetail = vi.fn().mockResolvedValue(undefined);

    render(
      <CandidateGroupGrid
        canMutateData
        displayState={createEmptyWorkbenchZoneDisplayState()}
        getRowState={() => "idle"}
        groups={[group]}
        onEnsureGroupDetail={ensureGroupDetail}
        onOpenDetail={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: [] },
          { id: "bank", title: "银行流水", rows: group.rows.bank },
          { id: "invoice", title: "进销项发票", rows: [] },
        ]}
        rowTemplateColumns="1fr 8px 1fr 8px 1fr"
        zoneId="paired"
      />,
    );

    await waitFor(() => expect(ensureGroupDetail).toHaveBeenCalledWith("paired", "bank-flow-rule-batch:BATCH-202603-FEE"));
  });

  test("renders OA, bank, and invoice candidates on the same horizontal group row", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const groupRow = await screen.findByTestId("candidate-group-open-case:CASE-202603-101");

    expect(within(groupRow).getByText("陈涛")).toBeInTheDocument();
    expect(within(groupRow).getAllByText("智能工厂设备商").length).toBeGreaterThan(0);
    expect(within(groupRow).getAllByText("58000").length).toBeGreaterThan(0);
    expect(within(groupRow).getByText("进")).toBeInTheDocument();
  });

  test("aligns source attachment invoices with their source OA inside a multi-OA group", () => {
    const oa294 = createOaRecord("oa-294", "刘晓宇", "294.31");
    const oa135 = createOaRecord("oa-135", "陈雄兵", "135");
    const bank = createBankRecord();
    const group: WorkbenchCandidateGroup = {
      id: "case:CASE-MULTI-OA-ATTACHMENT",
      groupType: "open",
      rawGroupType: "manual_confirmed",
      matchConfidence: "high",
      reason: "existing_case_group",
      rows: {
        oa: [oa294, oa135],
        bank: [{ ...bank, amount: "429.31", tableValues: { ...bank.tableValues, amount: "429.31" } }],
        invoice: [
          createAttachmentInvoiceRecord("iv-56", "中山市安自康贸易有限公司", "56.22", "oa-294"),
          createAttachmentInvoiceRecord("iv-200", "昆明啄木鸟信息技术服务有限公司", "200", "oa-294"),
          createAttachmentInvoiceRecord("iv-38", "南平市延平区松禾贸易有限公司", "38.09", "oa-294"),
          createAttachmentInvoiceRecord("iv-135", "大理江尾老军饭店", "135", "oa-135"),
        ],
      },
    };

    render(
      <CandidateGroupGrid
        canMutateData
        displayState={createEmptyWorkbenchZoneDisplayState()}
        getRowState={() => "idle"}
        groups={[group]}
        onOpenDetail={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: group.rows.oa },
          { id: "bank", title: "银行流水", rows: group.rows.bank },
          { id: "invoice", title: "进销项发票", rows: group.rows.invoice },
        ]}
        rowTemplateColumns="1fr 8px 1fr 8px 1fr"
        zoneId="open"
      />,
    );

    const firstOaSegment = screen.getByTestId("candidate-group-segment-open-case:CASE-MULTI-OA-ATTACHMENT-oa-294");
    expect(within(firstOaSegment).getByText("刘晓宇")).toBeInTheDocument();
    expect(within(firstOaSegment).getByText("294.31")).toBeInTheDocument();
    expect(within(firstOaSegment).getAllByText("56.22").length).toBeGreaterThan(0);
    expect(within(firstOaSegment).getAllByText("200").length).toBeGreaterThan(0);
    expect(within(firstOaSegment).getAllByText("38.09").length).toBeGreaterThan(0);
    expect(within(firstOaSegment).queryByText("陈雄兵")).not.toBeInTheDocument();
    expect(within(firstOaSegment).queryByText("大理江尾老军饭店")).not.toBeInTheDocument();

    const secondOaSegment = screen.getByTestId("candidate-group-segment-open-case:CASE-MULTI-OA-ATTACHMENT-oa-135");
    expect(within(secondOaSegment).getByText("陈雄兵")).toBeInTheDocument();
    expect(within(secondOaSegment).getByText("大理江尾老军饭店")).toBeInTheDocument();
    expect(within(secondOaSegment).getAllByText("135").length).toBeGreaterThanOrEqual(2);
    expect(within(secondOaSegment).queryByText("刘晓宇")).not.toBeInTheDocument();
    expect(within(secondOaSegment).queryByText("56.22")).not.toBeInTheDocument();
  });

  test("aligns attachment invoice item ids with their parent OA row inside a multi-OA group", () => {
    const parentOa = createOaRecord("oa-exp-1968", "吴云江", "405");
    const siblingOa = createOaRecord("oa-exp-2001", "吴云江", "282");
    const group: WorkbenchCandidateGroup = {
      id: "case:CASE-MULTI-OA-ITEM-ATTACHMENT",
      groupType: "paired",
      rawGroupType: "manual_confirmed",
      matchConfidence: "high",
      reason: "existing_case_group",
      rows: {
        oa: [parentOa, siblingOa],
        bank: [],
        invoice: [
          createAttachmentInvoiceRecord(
            "iv-oa-exp-1968-item-4",
            "云南澳约出行科技有限公司",
            "55",
            "oa-exp-1968:item:4:de54f988bd66",
          ),
        ],
      },
    };

    render(
      <CandidateGroupGrid
        canMutateData
        displayState={createEmptyWorkbenchZoneDisplayState()}
        getRowState={() => "idle"}
        groups={[group]}
        onOpenDetail={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: group.rows.oa },
          { id: "bank", title: "银行流水", rows: group.rows.bank },
          { id: "invoice", title: "进销项发票", rows: group.rows.invoice },
        ]}
        rowTemplateColumns="1fr 8px 1fr 8px 1fr"
        zoneId="paired"
      />,
    );

    const parentSegment = screen.getByTestId("candidate-group-segment-paired-case:CASE-MULTI-OA-ITEM-ATTACHMENT-oa-exp-1968");
    expect(within(parentSegment).getByText("405")).toBeInTheDocument();
    expect(within(parentSegment).getByText("云南澳约出行科技有限公司")).toBeInTheDocument();
    expect(within(parentSegment).getAllByText("55").length).toBeGreaterThan(0);

    const siblingSegment = screen.getByTestId("candidate-group-segment-paired-case:CASE-MULTI-OA-ITEM-ATTACHMENT-oa-exp-2001");
    expect(within(siblingSegment).getByText("282")).toBeInTheDocument();
    expect(within(siblingSegment).queryByText("云南澳约出行科技有限公司")).not.toBeInTheDocument();
  });

  test("aligns source bank rows with their parent OA row inside a multi-OA group", () => {
    const parentOa = createOaRecord("oa-exp-1968", "吴云江", "405");
    const siblingOa = createOaRecord("oa-exp-2001", "吴云江", "282");
    const group: WorkbenchCandidateGroup = {
      id: "case:CASE-MULTI-OA-SOURCE-BANK",
      groupType: "paired",
      rawGroupType: "manual_confirmed",
      matchConfidence: "high",
      reason: "existing_case_group",
      rows: {
        oa: [parentOa, siblingOa],
        bank: [createSourceBankRecord("bank-oa-exp-1968", "405", "oa-exp-1968:item:0:feed")],
        invoice: [],
      },
    };

    render(
      <CandidateGroupGrid
        canMutateData
        displayState={createEmptyWorkbenchZoneDisplayState()}
        getRowState={() => "idle"}
        groups={[group]}
        onOpenDetail={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: group.rows.oa },
          { id: "bank", title: "银行流水", rows: group.rows.bank },
          { id: "invoice", title: "进销项发票", rows: group.rows.invoice },
        ]}
        rowTemplateColumns="1fr 8px 1fr 8px 1fr"
        zoneId="paired"
      />,
    );

    const parentSegment = screen.getByTestId("candidate-group-segment-paired-case:CASE-MULTI-OA-SOURCE-BANK-oa-exp-1968");
    expect(within(parentSegment).getAllByText("405").length).toBeGreaterThan(1);
    expect(within(parentSegment).getByText("云南辰飞机电工程有限公司")).toBeInTheDocument();

    const siblingSegment = screen.getByTestId("candidate-group-segment-paired-case:CASE-MULTI-OA-SOURCE-BANK-oa-exp-2001");
    expect(within(siblingSegment).getByText("282")).toBeInTheDocument();
    expect(within(siblingSegment).queryByText("云南辰飞机电工程有限公司")).not.toBeInTheDocument();
  });

  test("aligns unlinked same-amount and sum-matched rows inside a multi-OA group", () => {
    const makeBankRow = (id: string, amount: string, counterparty: string): WorkbenchRecord => {
      const baseRecord = createBankRecord();
      return {
        ...baseRecord,
        id,
        caseId: "CASE-MULTI-OA-AMOUNT-FALLBACK",
        amount,
        counterparty,
        tableValues: {
          ...baseRecord.tableValues,
          amount,
          counterparty,
          direction: "支出",
        },
      };
    };
    const oa29350 = createOaRecord("oa-exp-29350", "樊祖芳", "29350");
    const oa88050 = createOaRecord("oa-exp-88050", "樊祖芳", "88050");
    const bank29350 = makeBankRow("bank-29350", "29350", "云南辰飞机电工程有限公司");
    const bank64996 = makeBankRow("bank-64996", "64996.69", "云南辰飞机电工程有限公司");
    const bank23053 = makeBankRow("bank-23053", "23053.31", "云南辰飞机电工程有限公司");
    const invoice29350Base = createInvoiceRecord("invoice-29350", "INV-29350");
    const invoice29350 = {
      ...invoice29350Base,
      amount: "29350",
      tableValues: {
        ...invoice29350Base.tableValues,
        amount: "29350",
        grossAmount: "29350",
      },
    };
    const group: WorkbenchCandidateGroup = {
      id: "case:CASE-MULTI-OA-AMOUNT-FALLBACK",
      groupType: "paired",
      rawGroupType: "manual_confirmed",
      matchConfidence: "high",
      reason: "existing_case_group",
      rows: {
        oa: [oa29350, oa88050],
        bank: [bank64996, bank23053, bank29350],
        invoice: [invoice29350],
      },
    };

    render(
      <CandidateGroupGrid
        canMutateData
        displayState={createEmptyWorkbenchZoneDisplayState()}
        getRowState={() => "idle"}
        groups={[group]}
        onOpenDetail={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: group.rows.oa },
          { id: "bank", title: "银行流水", rows: group.rows.bank },
          { id: "invoice", title: "进销项发票", rows: group.rows.invoice },
        ]}
        rowTemplateColumns="1fr 8px 1fr 8px 1fr"
        zoneId="paired"
      />,
    );

    const exactAmountSegment = screen.getByTestId(
      "candidate-group-segment-paired-case:CASE-MULTI-OA-AMOUNT-FALLBACK-oa-exp-29350",
    );
    expect(within(exactAmountSegment).getAllByText("29350").length).toBeGreaterThanOrEqual(3);
    expect(within(exactAmountSegment).queryByText("64996.69")).not.toBeInTheDocument();
    expect(within(exactAmountSegment).queryByText("23053.31")).not.toBeInTheDocument();

    const sumAmountSegment = screen.getByTestId(
      "candidate-group-segment-paired-case:CASE-MULTI-OA-AMOUNT-FALLBACK-oa-exp-88050",
    );
    expect(within(sumAmountSegment).getByText("88050")).toBeInTheDocument();
    expect(within(sumAmountSegment).getByText("64996.69")).toBeInTheDocument();
    expect(within(sumAmountSegment).getByText("23053.31")).toBeInTheDocument();
    expect(within(sumAmountSegment).queryByText("INV-29350")).not.toBeInTheDocument();
  });

  test("renders no-OA summary rows collapsed by default and expands to original bank detail rows", () => {
    renderNoOaGrid();
    const bankCell = screen.getByTestId("candidate-scroll-paired-no-oa-bank-batch:NOOA-202603-FEE-bank");

    expect(screen.getByText("免OA手续费批次")).toBeInTheDocument();
    expect(screen.queryByText("建设银行手续费")).not.toBeInTheDocument();
    expect(screen.queryByText("网银服务费")).not.toBeInTheDocument();
    const expandButton = screen.getByRole("button", { name: "展开免OA批次明细，2 条" });
    expect(expandButton).toHaveTextContent("展开 2 条明细");
    expect(expandButton).toHaveClass("candidate-group-collapse-control");
    expect(screen.queryByText("当前显示 1 条摘要")).not.toBeInTheDocument();
    expect(screen.queryByText("实际 2 条流水")).not.toBeInTheDocument();
    expect(bankCell).not.toContainElement(expandButton);
    expect(within(bankCell).getAllByRole("row")).toHaveLength(1);

    fireEvent.click(expandButton);

    expect(screen.getByText("建设银行手续费")).toBeInTheDocument();
    expect(screen.getByText("网银服务费")).toBeInTheDocument();
    expect(screen.queryByText("免OA手续费批次")).not.toBeInTheDocument();
    expect(within(bankCell).getAllByRole("row")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "收起免OA批次明细" })).toBeInTheDocument();
  });

  test("renders bank-flow summary rows without overlapping collapsed count copy", () => {
    renderNoOaGrid(createBankFlowCollapsedGroup());

    const expandButton = screen.getByRole("button", { name: "展开流水规则批次明细，15 条" });
    expect(expandButton).toHaveTextContent("展开 15 条明细");
    expect(screen.queryByText("当前显示 1 条摘要")).not.toBeInTheDocument();
    expect(screen.queryByText("实际 15 条流水")).not.toBeInTheDocument();
  });

  test("renders a non-overlapping expand control for ordinary truncated bank previews and loads hidden rows", async () => {
    const summaryGroup = createTruncatedTurnoverGroup();
    const fullDetailGroup = createFullTurnoverGroup();
    const ensureGroupDetail = vi.fn();
    let resolveDetail!: () => void;
    const detailLoaded = new Promise<void>((resolve) => {
      resolveDetail = resolve;
    });

    function GridHarness() {
      const [group, setGroup] = useState(summaryGroup);
      return (
        <CandidateGroupGrid
          canMutateData
          displayState={createEmptyWorkbenchZoneDisplayState()}
          getRowState={() => "idle"}
          groups={[group]}
          onEnsureGroupDetail={async (zoneId, groupId) => {
            ensureGroupDetail(zoneId, groupId);
            await detailLoaded;
            setGroup(fullDetailGroup);
          }}
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          panes={[
            { id: "oa", title: "OA", rows: group.rows.oa },
            { id: "bank", title: "银行流水", rows: group.rows.bank },
            { id: "invoice", title: "进销项发票", rows: group.rows.invoice },
          ]}
          rowTemplateColumns="1fr 8px 1fr 8px 1fr"
          zoneId="open"
        />
      );
    }

    render(<GridHarness />);

    const bankCell = screen.getByTestId("candidate-scroll-open-case:turnover:turnover_rel_36266274e9235566-bank");
    const expandButton = screen.getByRole("button", {
      name: "展开全部银行流水，当前显示 3 条，共 4 条",
    });

    expect(screen.getByText("2026-05-22")).toBeInTheDocument();
    expect(screen.getByText("14:40:07")).toBeInTheDocument();
    expect(screen.getByText("2026-05-11")).toBeInTheDocument();
    expect(screen.getByText("09:06:40")).toBeInTheDocument();
    expect(screen.getByText("2026-05-10")).toBeInTheDocument();
    expect(screen.getByText("09:45:04")).toBeInTheDocument();
    expect(screen.queryByText("杨丽萍 5月9隐藏流水")).not.toBeInTheDocument();
    expect(expandButton).toHaveTextContent("还有 1 条，展开");
    expect(expandButton).toHaveClass("candidate-group-collapse-control");
    expect(bankCell).not.toContainElement(expandButton);
    expect(ensureGroupDetail).not.toHaveBeenCalled();

    fireEvent.click(expandButton);

    expect(screen.getByText("加载中")).toBeInTheDocument();
    await waitFor(() => {
      expect(ensureGroupDetail).toHaveBeenCalledWith("open", "case:turnover:turnover_rel_36266274e9235566");
    });

    await act(async () => {
      resolveDetail();
      await detailLoaded;
    });

    expect(await screen.findByText("杨丽萍 5月9隐藏流水")).toBeInTheDocument();
    expect(screen.getByText("2026-05-09")).toBeInTheDocument();
    expect(screen.getByText("10:14:06")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /展开全部银行流水/ })).not.toBeInTheDocument();
  });

  test("waits for full collapsed detail before expanding truncated summary rows", async () => {
    const summaryGroup = createBankFlowPlaceholderGroup();
    const fullDetailGroup = createBankFlowFullDetailGroup();
    const ensureGroupDetail = vi.fn();
    let resolveDetail!: () => void;
    const detailLoaded = new Promise<void>((resolve) => {
      resolveDetail = resolve;
    });

    function GridHarness() {
      const [group, setGroup] = useState(summaryGroup);
      return (
        <CandidateGroupGrid
          canMutateData
          displayState={createEmptyWorkbenchZoneDisplayState()}
          getRowState={() => "idle"}
          groups={[group]}
          onEnsureGroupDetail={async (zoneId, groupId) => {
            ensureGroupDetail(zoneId, groupId);
            await detailLoaded;
            setGroup(fullDetailGroup);
          }}
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          panes={[
            { id: "oa", title: "OA", rows: [] },
            { id: "bank", title: "银行流水", rows: group.rows.bank },
            { id: "invoice", title: "进销项发票", rows: [] },
          ]}
          rowTemplateColumns="1fr 8px 1fr 8px 1fr"
          zoneId="paired"
        />
      );
    }

    render(<GridHarness />);

    fireEvent.click(screen.getByRole("button", { name: "展开流水规则批次明细，15 条" }));

    expect(screen.getByText("流水规则手续费批次")).toBeInTheDocument();
    expect(screen.getByText("加载中")).toBeInTheDocument();
    expect(screen.queryByText("占位明细")).not.toBeInTheDocument();
    expect(screen.queryByText("建设银行手续费")).not.toBeInTheDocument();
    await waitFor(() => expect(ensureGroupDetail).toHaveBeenCalledWith("paired", "bank-flow-rule-batch:BATCH-202603-FEE"));

    await act(async () => {
      resolveDetail();
      await detailLoaded;
    });

    expect(await screen.findByText("建设银行手续费")).toBeInTheDocument();
    expect(screen.queryByText("占位明细")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起流水规则批次明细" })).toBeInTheDocument();
  });

  test("keeps truncated collapsed summary closed when full detail loading fails", async () => {
    const group = createBankFlowCollapsedGroup();
    const ensureGroupDetail = vi.fn().mockRejectedValue(new Error("stale"));
    render(
      <CandidateGroupGrid
        canMutateData
        displayState={createEmptyWorkbenchZoneDisplayState()}
        getRowState={() => "idle"}
        groups={[group]}
        onEnsureGroupDetail={ensureGroupDetail}
        onOpenDetail={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: [] },
          { id: "bank", title: "银行流水", rows: group.rows.bank },
          { id: "invoice", title: "进销项发票", rows: [] },
        ]}
        rowTemplateColumns="1fr 8px 1fr 8px 1fr"
        zoneId="paired"
      />,
    );

    await waitFor(() => expect(ensureGroupDetail).toHaveBeenCalledWith("paired", "bank-flow-rule-batch:BATCH-202603-FEE"));
    ensureGroupDetail.mockClear();

    fireEvent.click(screen.getByRole("button", { name: "展开流水规则批次明细，15 条" }));

    await waitFor(() => expect(ensureGroupDetail).toHaveBeenCalledWith("paired", "bank-flow-rule-batch:BATCH-202603-FEE"));
    await waitFor(() => expect(screen.getByRole("button", { name: "展开流水规则批次明细，15 条" })).not.toBeDisabled());
    expect(screen.getByText("流水规则手续费批次")).toBeInTheDocument();
    expect(screen.queryByText("建设银行手续费")).not.toBeInTheDocument();
    expect(screen.queryByText("网银服务费")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "收起流水规则批次明细" })).not.toBeInTheDocument();
  });

  test("renders ETC invoice summaries collapsed by default and expands in the invoice pane", () => {
    const group = createEtcCollapsedGroup();
    render(
      <CandidateGroupGrid
        canMutateData
        displayState={createEmptyWorkbenchZoneDisplayState()}
        getRowState={() => "idle"}
        groups={[group]}
        onOpenDetail={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: group.rows.oa },
          { id: "bank", title: "银行流水", rows: group.rows.bank },
          { id: "invoice", title: "进销项发票", rows: group.rows.invoice },
        ]}
        rowTemplateColumns="1fr 8px 1fr 8px 1fr"
        zoneId="paired"
      />,
    );

    const invoiceCell = screen.getByTestId("candidate-scroll-paired-case:ETC-OA-20260215-154900-invoice");
    expect(screen.getByText("ETC批次")).toBeInTheDocument();
    expect(screen.queryByText("ETC-001")).not.toBeInTheDocument();
    expect(screen.queryByText("ETC-002")).not.toBeInTheDocument();
    const expandButton = screen.getByRole("button", { name: "展开ETC发票明细，2 张" });
    expect(expandButton).toHaveTextContent("展开 2 张明细");
    expect(screen.queryByText("当前显示 1 条摘要")).not.toBeInTheDocument();
    expect(screen.queryByText("实际 2 张发票")).not.toBeInTheDocument();
    expect(invoiceCell).not.toContainElement(expandButton);
    expect(within(invoiceCell).getAllByRole("row")).toHaveLength(1);

    fireEvent.click(expandButton);

    expect(screen.getByText("ETC-001")).toBeInTheDocument();
    expect(screen.getByText("ETC-002")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起ETC发票明细" })).toBeInTheDocument();
    expect(within(invoiceCell).getAllByRole("row")).toHaveLength(2);
  });

  test("renders submitted salary and internal-transfer batches as collapsed no-OA summaries", () => {
    const salarySummary = createNoOaBankRecord("nooa-summary-NOOA-202603-SALARY", "免OA工资批次", "80,000.00", "4 条工资");
    const internalSummary = createNoOaBankRecord(
      "nooa-summary-NOOA-202603-INTERNAL",
      "免OA内部往来款批次",
      "125,000.00",
      "1 条内部往来款",
    );

    render(
      <CandidateGroupGrid
        canMutateData
        displayState={createEmptyWorkbenchZoneDisplayState()}
        getRowState={() => "idle"}
        groups={[
          {
            id: "no-oa-bank-batch:NOOA-202603-SALARY",
            groupType: "manual_confirmed",
            matchConfidence: "high",
            reason: "免OA工资批次",
            relationMode: "no_oa_bank_batch",
            displayMode: "collapsed_summary",
            defaultCollapsed: true,
            rows: { oa: [], bank: [salarySummary], invoice: [] },
            collapsedRows: {
              bank: [createNoOaBankRecord("bk-nooa-salary-001", "员工工资", "80,000.00", "摘要：工资")],
            },
          },
          {
            id: "no-oa-bank-batch:NOOA-202603-INTERNAL",
            groupType: "manual_confirmed",
            matchConfidence: "high",
            reason: "免OA内部往来款批次",
            relationMode: "no_oa_bank_batch",
            displayMode: "collapsed_summary",
            defaultCollapsed: true,
            rows: { oa: [], bank: [internalSummary], invoice: [] },
            collapsedRows: {
              bank: [createNoOaBankRecord("bk-nooa-internal-001", "内部往来款", "125,000.00", "摘要：内部往来款")],
            },
          },
        ]}
        onClearPaneSearch={() => undefined}
        onClosePaneSearch={() => undefined}
        onColumnFilterChange={() => undefined}
        onOpenDetail={() => undefined}
        onPaneSearchQueryChange={() => undefined}
        onPaneTimeFilterChange={() => undefined}
        onReorderPaneColumns={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
        onTogglePaneSearch={() => undefined}
        onTogglePaneSort={() => undefined}
        panes={[
          { id: "oa", title: "OA", rows: [] },
          { id: "bank", title: "银行流水", rows: [salarySummary, internalSummary] },
          { id: "invoice", title: "进销项发票", rows: [] },
        ]}
        rowTemplateColumns="1fr 1fr 1fr"
        zoneId="paired"
      />,
    );

    expect(screen.getByText("免OA工资批次")).toBeInTheDocument();
    expect(screen.getByText("免OA内部往来款批次")).toBeInTheDocument();
    expect(screen.queryByText("已匹配：工资")).not.toBeInTheDocument();
    expect(screen.queryByText("已匹配：内部往来款")).not.toBeInTheDocument();
    expect(screen.queryByText("员工工资")).not.toBeInTheDocument();
    expect(screen.queryByText("内部往来款")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "展开免OA批次明细，1 条" })).toHaveLength(2);
  });

  test("withdraws bank-flow summaries through the bank flow rule batch API instead of ordinary cancel-link", async () => {
    const fetchMock = mockWorkbenchPageFetch(buildBankFlowRuleWorkbenchPayload());
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderWorkbenchPage();

      const pairedZone = await screen.findByTestId("zone-paired");
      const groupRow = await screen.findByTestId("candidate-group-paired-bank-flow-rule-batch:BANKFLOW-202603-FEE");
      fireEvent.click(within(groupRow).getByRole("row", { name: /流水规则手续费批次.*30/ }));
      fireEvent.click(within(pairedZone).getByRole("button", { name: "撤回关联" }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/bank-flow-rule-batches/BANKFLOW-202603-FEE/withdraw",
          expect.objectContaining({ method: "POST" }),
        );
      });
      expect(fetchMock).not.toHaveBeenCalledWith(
        "/api/workbench/actions/cancel-link",
        expect.anything(),
      );
      expectCustomEventDetailContaining(relationListener, { affectedMonths: ["2026-03"] });
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
  });

  test("refreshes the workbench when bank transaction categories are updated", async () => {
    const fetchMock = mockWorkbenchPageFetch();

    renderWorkbenchPage();
    await screen.findByTestId("candidate-group-paired-no-oa-bank-batch:NOOA-202603-FEE");
    const initialWorkbenchRequests = countInitialWorkbenchPageRequests(fetchMock);

    await act(async () => {
      window.dispatchEvent(new CustomEvent("bankTransactionCategoryUpdated", { detail: { affectedMonths: ["2026-03"] } }));
    });

    await waitFor(() => {
      const workbenchRequests = countInitialWorkbenchPageRequests(fetchMock);
      expect(workbenchRequests).toBeGreaterThan(initialWorkbenchRequests);
    });
  });

  test("renders bank note column from structured bank text fields", () => {
    const bankColumns = getWorkbenchColumns("bank");
    const bankGridStyle = getWorkbenchPaneGridStyle("bank");

    render(
      <WorkbenchRecordCard
        canMutateData
        columnGridStyle={bankGridStyle}
        columns={bankColumns}
        paneId="bank"
        row={createBankRecord()}
        rowState="idle"
        showWorkflowActions={false}
        zoneId="open"
        onOpenDetail={() => undefined}
        onRowAction={() => undefined}
        onSelectRow={() => undefined}
      />,
    );

    expect(screen.getByText("摘要：电子转账")).toBeInTheDocument();
    expect(screen.getByText("备注：代购公车款")).toBeInTheDocument();
    expect(screen.getByText("用途：货款")).toBeInTheDocument();
    expect(screen.queryByText(/交易用途：/)).not.toBeInTheDocument();
    expect(screen.queryByText(/客户附言：/)).not.toBeInTheDocument();
  });

  test("renders OA 2035 source OA and formal attachment invoices in the same horizontal group row", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const groupRow = await screen.findByTestId("candidate-group-open-case:CASE-202603-OA-ATTACHMENT-2035");
    const oaCell = within(groupRow).getByTestId("candidate-scroll-open-case:CASE-202603-OA-ATTACHMENT-2035-oa");
    const invoiceCell = within(groupRow).getByTestId(
      "candidate-scroll-open-case:CASE-202603-OA-ATTACHMENT-2035-invoice",
    );

    expect(within(oaCell).getByRole("row", { name: /胡瑢.*248/ })).toBeInTheDocument();
    expect(within(invoiceCell).getByRole("row", { name: /OA2035-MACHINE-25.*25/ })).toBeInTheDocument();
    expect(within(invoiceCell).getByRole("row", { name: /OA2035-MACHINE-23.*23/ })).toBeInTheDocument();
    expect(within(invoiceCell).getByRole("row", { name: /OA2035-FUEL-200.*200/ })).toBeInTheDocument();
    expect(within(invoiceCell).queryByRole("row", { name: /微信支付/ })).not.toBeInTheDocument();
    expect(within(invoiceCell).getAllByRole("row")).toHaveLength(3);
    expect(within(invoiceCell).getAllByText("OA附件")).toHaveLength(3);
    expect(within(invoiceCell).queryByText("付款凭证")).not.toBeInTheDocument();
    expect(within(invoiceCell).queryByText("人工导入")).not.toBeInTheDocument();

    expect(screen.queryByRole("row", { name: /胡瑢付款项/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /付款项\s*[123].*248/ })).not.toBeInTheDocument();
  });

  test("renders 292 source OA with only one OA attachment invoice in the same horizontal group row", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const groupRow = await screen.findByTestId("candidate-group-open-case:CASE-202603-OA-ATTACHMENT-292");
    const oaCell = within(groupRow).getByTestId("candidate-scroll-open-case:CASE-202603-OA-ATTACHMENT-292-oa");
    const invoiceCell = within(groupRow).getByTestId(
      "candidate-scroll-open-case:CASE-202603-OA-ATTACHMENT-292-invoice",
    );

    expect(within(oaCell).getByRole("row", { name: /胡瑢.*292/ })).toBeInTheDocument();
    expect(within(invoiceCell).getByRole("row", { name: /OAATT-292-001.*292/ })).toBeInTheDocument();
    expect(within(invoiceCell).getAllByRole("row")).toHaveLength(1);
  });

  test("renders each candidate group as a shared sheet band instead of isolated cards", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const groupedRow = await screen.findByTestId("candidate-group-open-case:CASE-202603-101");
    const emptyRow = await screen.findByTestId("candidate-group-open-row:oa-o-202603-002");

    const oaCell = within(groupedRow).getByTestId("candidate-scroll-open-case:CASE-202603-101-oa");
    const bankCell = within(groupedRow).getByTestId("candidate-scroll-open-case:CASE-202603-101-bank");
    const invoiceCell = within(groupedRow).getByTestId("candidate-scroll-open-case:CASE-202603-101-invoice");
    const bankRow = within(bankCell).getByRole("row", { name: /2026-03-28.*智能工厂设备商/ });
    const emptyBankCell = within(emptyRow).getByTestId("candidate-scroll-open-row:oa-o-202603-002-bank");

    expect(groupedRow).toHaveClass("candidate-group-row-sheet");
    expect(oaCell).toHaveClass("candidate-group-cell-sheet");
    expect(bankCell).toHaveClass("candidate-group-cell-sheet");
    expect(invoiceCell).toHaveClass("candidate-group-cell-sheet");
    expect(bankRow).toHaveClass("record-card-sheet-row");
    expect(emptyBankCell).toHaveClass("candidate-group-cell-empty-sheet");
  });

  test("cycles subtle sheet tones across adjacent candidate groups", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const rows = await screen.findAllByTestId(/candidate-group-open-/);
    expect(rows[0]).toHaveClass("candidate-group-row-tone-0");
    expect(rows[1]).toHaveClass("candidate-group-row-tone-1");
    expect(rows[2]).toHaveClass("candidate-group-row-tone-2");
    expect(rows[3]).toHaveClass("candidate-group-row-tone-3");
  });

  test("uses stretched sheet rows for single records and split sheet rows for multiple records", () => {
    render(
      <div>
        <CandidateGroupCell
          actionMode="default"
          canMutateData
          columnGridStyle={invoiceGridStyle}
          columns={invoiceColumns}
          getRowState={() => "idle"}
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          paneId="invoice"
          records={[createInvoiceRecord("single-invoice", "INV-SINGLE-001")]}
          scrollPaneId="invoice"
          scrollTestId="sheet-single"
          showWorkflowActions
          zoneId="open"
        />
        <CandidateGroupCell
          actionMode="default"
          canMutateData
          columnGridStyle={invoiceGridStyle}
          columns={invoiceColumns}
          getRowState={() => "idle"}
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          paneId="invoice"
          records={[
            createInvoiceRecord("multi-invoice-1", "INV-MULTI-001"),
            createInvoiceRecord("multi-invoice-2", "INV-MULTI-002"),
          ]}
          scrollPaneId="invoice"
          scrollTestId="sheet-multi"
          showWorkflowActions
          zoneId="open"
        />
      </div>,
    );

    const singleCell = screen.getByTestId("sheet-single");
    const multiCell = screen.getByTestId("sheet-multi");
    const singleRow = within(singleCell).getAllByRole("row")[0];
    const multiRows = within(multiCell).getAllByRole("row");

    expect(singleCell).toHaveClass("candidate-group-cell-sheet-single");
    expect(singleRow).toHaveClass("record-card-sheet-row-stretched");
    expect(multiCell).toHaveClass("candidate-group-cell-sheet-multi");
    expect(multiRows[0]).toHaveClass("record-card-sheet-row-split");
    expect(multiRows[1]).toHaveClass("record-card-sheet-row-split");
  });

  test("keeps selected related and highlighted rows compatible with sheet state classes", () => {
    render(
      <div>
        <WorkbenchRecordCard
          actionMode="default"
          canMutateData
          columnGridStyle={invoiceGridStyle}
          columns={invoiceColumns}
          highlighted={false}
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          paneId="invoice"
          row={createInvoiceRecord("state-selected", "INV-STATE-001")}
          rowState="selected"
          showWorkflowActions
          zoneId="open"
        />
        <WorkbenchRecordCard
          actionMode="default"
          canMutateData
          columnGridStyle={invoiceGridStyle}
          columns={invoiceColumns}
          highlighted={false}
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          paneId="invoice"
          row={createInvoiceRecord("state-related", "INV-STATE-002")}
          rowState="related"
          showWorkflowActions
          zoneId="open"
        />
        <WorkbenchRecordCard
          actionMode="default"
          canMutateData
          columnGridStyle={invoiceGridStyle}
          columns={invoiceColumns}
          highlighted
          onOpenDetail={() => undefined}
          onRowAction={() => undefined}
          onSelectRow={() => undefined}
          paneId="invoice"
          row={createInvoiceRecord("state-highlight", "INV-STATE-003")}
          rowState="idle"
          showWorkflowActions
          zoneId="open"
        />
      </div>,
    );

    const selectedRow = screen.getByRole("row", { name: /INV-STATE-001/ });
    const relatedRow = screen.getByRole("row", { name: /INV-STATE-002/ });
    const highlightedRow = screen.getByRole("row", { name: /INV-STATE-003/ });

    expect(selectedRow).toHaveClass("record-card-sheet-selected");
    expect(relatedRow).toHaveClass("record-card-sheet-related");
    expect(highlightedRow).toHaveClass("record-card-sheet-highlighted");
  });

  test("renders blank cells when a candidate group is missing bank and invoice records", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const groupRow = await screen.findByTestId("candidate-group-open-row:oa-o-202603-002");
    const emptyCells = within(groupRow).getAllByText("-");

    expect(within(groupRow).getByText("孙敏")).toBeInTheDocument();
    expect(emptyCells).toHaveLength(2);
  });

  test("shows backend invoice inventory diagnostics on the invoice pane title", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const invoicePane = within(openZone).getByTestId("pane-invoice");
    const groupRow = await screen.findByTestId("candidate-group-open-row:oa-o-202603-002");
    const diagnostics = within(invoicePane).getByRole("button", {
      name: "进销项发票库存统计：系统发票总数 9，人工导入总数 7，普通可见 4，已提交 ETC 隐藏 2，额外 ETC 1，ETC 折叠批次 3，OA附件解析发票 5",
    });

    expect(diagnostics).toHaveTextContent("进销项发票");
    expect(within(invoicePane).getByText("系统发票总数")).toBeInTheDocument();
    expect(within(invoicePane).getByText("人工导入总数")).toBeInTheDocument();
    expect(within(invoicePane).getByText("普通可见")).toBeInTheDocument();
    expect(within(invoicePane).getByText("已提交 ETC 隐藏")).toBeInTheDocument();
    expect(within(invoicePane).getByText("额外 ETC")).toBeInTheDocument();
    expect(within(invoicePane).getByText("ETC 折叠批次")).toBeInTheDocument();
    expect(within(invoicePane).getByText("OA附件解析发票")).toBeInTheDocument();
    expect(within(invoicePane).queryByText("已导入的发票数量")).not.toBeInTheDocument();
    expect(within(groupRow).queryByRole("button", { name: /附件统计/ })).not.toBeInTheDocument();
  });

  test("syncs pane header and candidate blocks from a single bottom scrollbar", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const headerScroll = await screen.findByTestId("pane-scroll-head-open-bank");
    const footerScroll = screen.getByTestId("pane-scrollbar-open-bank");
    const groupScroll = screen.getByTestId("candidate-scroll-open-case:CASE-202603-101-bank");

    fireEvent.scroll(footerScroll, { target: { scrollLeft: 96 } });

    expect(headerScroll.scrollLeft).toBe(96);
    expect(groupScroll.scrollLeft).toBe(96);
  });

  test("keeps the synchronized bottom scrollbar thin instead of rendering a large visual band", () => {
    const footerRule = appStyles.match(/\.candidate-grid-footer\s*\{[^}]*\}/s)?.[0] ?? "";
    const footerScrollRule = appStyles.match(/\.candidate-pane-footer-scroll\s*\{[^}]*\}/s)?.[0] ?? "";

    expect(footerRule).toMatch(/height:\s*10px;/);
    expect(footerRule).not.toContain("background: #fbfdff");
    expect(footerScrollRule).toMatch(/height:\s*10px;/);
  });

  test("toggles bank and invoice group sorting in open and paired zones", async () => {
    installMockApiFetch();
    renderWorkbenchPage();

    const openZone = await screen.findByTestId("zone-open");
    const pairedZone = await screen.findByTestId("zone-paired");
    const openBankPane = within(openZone).getByTestId("pane-bank");
    const pairedInvoicePane = within(pairedZone).getByTestId("pane-invoice");

    fireEvent.click(within(openBankPane).getByRole("button", { name: "银行流水按时间降序" }));

    await waitFor(() => {
      const openDescOrder = getZoneGroupOrder(openZone);
      expect(openDescOrder.indexOf("candidate-group-open-case:CASE-202604-101")).toBeLessThan(
        openDescOrder.indexOf("candidate-group-open-case:CASE-202603-101"),
      );
      expect(openDescOrder.indexOf("candidate-group-open-row:oa-o-202603-002")).toBeGreaterThan(
        openDescOrder.indexOf("candidate-group-open-case:CASE-202603-101"),
      );
    });

    fireEvent.click(within(openBankPane).getByRole("button", { name: "银行流水按时间升序" }));

    await waitFor(() => {
      const openAscOrder = getZoneGroupOrder(openZone);
      expect(openAscOrder.indexOf("candidate-group-open-case:CASE-202603-101")).toBeLessThan(
        openAscOrder.indexOf("candidate-group-open-case:CASE-202604-101"),
      );
    });

    fireEvent.click(within(pairedInvoicePane).getByRole("button", { name: "进销项发票按时间降序" }));

    await waitFor(() => {
      const pairedDescOrder = getZoneGroupOrder(pairedZone);
      expect(pairedDescOrder.indexOf("candidate-group-paired-case:CASE-202604-001")).toBeLessThan(
        pairedDescOrder.indexOf("candidate-group-paired-case:CASE-202603-001"),
      );
    });

    fireEvent.click(within(pairedInvoicePane).getByRole("button", { name: "进销项发票按时间升序" }));

    await waitFor(() => {
      const pairedAscOrder = getZoneGroupOrder(pairedZone);
      expect(pairedAscOrder.indexOf("candidate-group-paired-case:CASE-202603-001")).toBeLessThan(
        pairedAscOrder.indexOf("candidate-group-paired-case:CASE-202604-001"),
      );
    });
  });
});
