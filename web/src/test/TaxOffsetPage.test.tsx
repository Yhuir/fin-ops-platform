import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

function getStatCard(label: string) {
  const card = screen
    .getAllByText(label)
    .map((element) => element.closest(".stat-card"))
    .find((element): element is HTMLElement => Boolean(element));
  if (!card) {
    throw new Error(`Stat card not found for ${label}`);
  }
  return card;
}

describe("Tax offset workbench", () => {
  test("renders read-only output invoices, editable input plan, and certified drawer", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();
    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "返回关联台" })).not.toBeInTheDocument();

    const outputTable = screen.getByRole("table", { name: "销项票开票情况" });
    expect(within(outputTable).queryByRole("checkbox")).not.toBeInTheDocument();

    const inputTable = screen.getByRole("table", { name: "进项票认证计划" });
    expect(within(inputTable).getByRole("checkbox", { name: /11203490/ })).toBeDisabled();
    expect(within(inputTable).getByRole("checkbox", { name: /11203491/ })).not.toBeDisabled();

    expect(screen.getByRole("complementary", { name: "已认证结果" })).toBeInTheDocument();
    expect(screen.getByText("已匹配计划")).toBeInTheDocument();
    expect(screen.getByText("已认证但未进入计划")).toBeInTheDocument();
    expect(screen.getByText("税金抵扣计划与试算")).toBeInTheDocument();
    expect(screen.getByText("税金抵扣试算")).toBeInTheDocument();
    expect(screen.queryByText("提交认证")).not.toBeInTheDocument();
    expect(screen.queryByText("正式申报")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /已认证结果/ }));
    expect(screen.getByRole("button", { name: /展开已认证结果/ })).toBeInTheDocument();
  });

  test("opens certified invoice import in a page modal instead of navigating to the import page", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();
    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "已认证发票导入" }));

    expect(screen.getByRole("dialog", { name: "已认证发票导入" })).toBeInTheDocument();
    expect(screen.getByText("税金抵扣页内的专用导入窗口。后续真实识别与回写逻辑会直接接在这里，不再跳转到关联台导入界面。")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/tax-offset");
    expect(screen.queryByRole("heading", { name: "导入中心" })).not.toBeInTheDocument();
  });

  test("recalculates using certified invoices plus selected uncertified plan rows", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    expect(within(getStatCard("销项税额")).getByText("41,600.00")).toBeInTheDocument();
    expect(within(getStatCard("已认证结果进项税额")).getByText("14,080.00")).toBeInTheDocument();
    expect(within(getStatCard("计划进项税额")).getByText("5,760.00")).toBeInTheDocument();
    expect(within(getStatCard("本月抵扣额")).getByText("19,840.00")).toBeInTheDocument();
    expect(within(getStatCard("本月应纳税额")).getByText("21,760.00")).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: /11203491/ }));

    expect(await within(getStatCard("计划进项税额")).findByText("0.00")).toBeInTheDocument();
    expect(within(getStatCard("已认证结果进项税额")).getByText("14,080.00")).toBeInTheDocument();
    expect(within(getStatCard("本月抵扣额")).getByText("14,080.00")).toBeInTheDocument();
    expect(within(getStatCard("本月应纳税额")).getByText("27,520.00")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tax-offset/calculate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "2026-03",
          selected_output_ids: ["to-202603-001"],
          selected_input_ids: [],
        }),
      }),
    );
  });

  test("clicking a matched certified row highlights the corresponding input plan row", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();
    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();

    const drawer = screen.getByRole("complementary", { name: "已认证结果" });
    await user.click(within(drawer).getByRole("button", { name: /11203490/ }));

    const inputTable = screen.getByRole("table", { name: "进项票认证计划" });
    const highlightedRow = within(inputTable).getByRole("row", { name: /11203490/ });
    expect(highlightedRow).toHaveAttribute("data-certified-highlighted", "true");
  });

  test("shows an empty state when the selected month has no tax invoices", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    await user.click(screen.getByRole("button", { name: "年月选择" }));
    await user.click(screen.getByRole("button", { name: "2026年" }));
    await user.click(screen.getByRole("button", { name: "5月" }));

    expect(await screen.findByText("当前月份没有可用于计划与试算的发票数据。")).toBeInTheDocument();
  });

  test("refreshes summary, plan locks, and drawer rows when the page regains focus", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    const responses = [
      {
        month: "2026-03",
        output_items: [
          {
            id: "to-202603-001",
            buyer_name: "华东项目甲方",
            issue_date: "2026-03-25",
            invoice_no: "90342011",
            tax_amount: "41,600.00",
            total_with_tax: "361,600.00",
            invoice_type: "销项专票",
          },
        ],
        input_plan_items: [
          {
            id: "ti-202603-001",
            seller_name: "设备供应商",
            issue_date: "2026-03-22",
            invoice_no: "11203490",
            tax_amount: "12,480.00",
            total_with_tax: "108,480.00",
            risk_level: "低",
            certified_status: "待认证",
            is_locked_certified: false,
          },
          {
            id: "ti-202603-002",
            seller_name: "集成服务商",
            issue_date: "2026-03-24",
            invoice_no: "11203491",
            tax_amount: "5,760.00",
            total_with_tax: "101,760.00",
            risk_level: "中",
            certified_status: "待认证",
            is_locked_certified: false,
          },
        ],
        certified_items: [],
        certified_matched_rows: [],
        certified_outside_plan_rows: [],
        locked_certified_input_ids: [],
        default_selected_output_ids: ["to-202603-001"],
        default_selected_input_ids: ["ti-202603-001", "ti-202603-002"],
        summary: {
          output_tax: "41,600.00",
          certified_input_tax: "0.00",
          planned_input_tax: "18,240.00",
          input_tax: "18,240.00",
          deductible_tax: "18,240.00",
          result_label: "本月应纳税额",
          result_amount: "23,360.00",
        },
      },
      {
        month: "2026-03",
        output_items: [
          {
            id: "to-202603-001",
            buyer_name: "华东项目甲方",
            issue_date: "2026-03-25",
            invoice_no: "90342011",
            tax_amount: "41,600.00",
            total_with_tax: "361,600.00",
            invoice_type: "销项专票",
          },
        ],
        input_plan_items: [
          {
            id: "ti-202603-001",
            seller_name: "设备供应商",
            issue_date: "2026-03-22",
            invoice_no: "11203490",
            tax_amount: "12,480.00",
            total_with_tax: "108,480.00",
            risk_level: "低",
            certified_status: "已认证",
            is_locked_certified: true,
          },
          {
            id: "ti-202603-002",
            seller_name: "集成服务商",
            issue_date: "2026-03-24",
            invoice_no: "11203491",
            tax_amount: "5,760.00",
            total_with_tax: "101,760.00",
            risk_level: "中",
            certified_status: "待认证",
            is_locked_certified: false,
          },
        ],
        certified_items: [
          {
            id: "tc-202603-001",
            seller_name: "设备供应商",
            issue_date: "2026-03-22",
            invoice_no: "11203490",
            tax_amount: "12,480.00",
            total_with_tax: "108,480.00",
            status: "已认证",
          },
          {
            id: "tc-202603-099",
            seller_name: "物业服务商",
            issue_date: "2026-03-28",
            invoice_no: "11203999",
            tax_amount: "1,600.00",
            total_with_tax: "13,600.00",
            status: "已认证",
          },
        ],
        certified_matched_rows: [
          {
            id: "tc-202603-001",
            seller_name: "设备供应商",
            issue_date: "2026-03-22",
            invoice_no: "11203490",
            tax_amount: "12,480.00",
            total_with_tax: "108,480.00",
            status: "已认证",
            matched_input_id: "ti-202603-001",
          },
        ],
        certified_outside_plan_rows: [
          {
            id: "tc-202603-099",
            seller_name: "物业服务商",
            issue_date: "2026-03-28",
            invoice_no: "11203999",
            tax_amount: "1,600.00",
            total_with_tax: "13,600.00",
            status: "已认证",
            matched_input_id: null,
          },
        ],
        locked_certified_input_ids: ["ti-202603-001"],
        default_selected_output_ids: ["to-202603-001"],
        default_selected_input_ids: ["ti-202603-002"],
        summary: {
          output_tax: "41,600.00",
          certified_input_tax: "14,080.00",
          planned_input_tax: "5,760.00",
          input_tax: "19,840.00",
          deductible_tax: "19,840.00",
          result_label: "本月应纳税额",
          result_amount: "21,760.00",
        },
      },
    ];
    let currentSnapshot = responses[0];

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/tax-offset?month=2026-03") {
        currentSnapshot = responses.length > 1 ? responses.shift() ?? responses[0] : responses[0];
        return new Response(JSON.stringify(currentSnapshot), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/tax-offset/calculate") {
        const jsonBody =
          typeof init?.body === "string" && init.body.length > 0
            ? (JSON.parse(init.body) as { selected_input_ids?: string[] })
            : {};
        const selectedInputIds = new Set(jsonBody.selected_input_ids ?? []);
        const lockedIds = new Set(currentSnapshot.locked_certified_input_ids);
        const selectedPlanTax = currentSnapshot.input_plan_items
          .filter((item) => selectedInputIds.has(item.id) && !lockedIds.has(item.id))
          .reduce((sum, item) => sum + Number(item.tax_amount.replace(/,/g, "")), 0);
        const certifiedTax = currentSnapshot.certified_items.reduce(
          (sum, item) => sum + Number(item.tax_amount.replace(/,/g, "")),
          0,
        );
        const outputTax = currentSnapshot.output_items.reduce(
          (sum, item) => sum + Number(item.tax_amount.replace(/,/g, "")),
          0,
        );
        const deductibleTax = Math.min(outputTax, certifiedTax + selectedPlanTax);
        const resultAmount = outputTax - deductibleTax;
        return new Response(
          JSON.stringify({
            month: "2026-03",
            summary: {
              output_tax: outputTax.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
              certified_input_tax: certifiedTax.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }),
              planned_input_tax: selectedPlanTax.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }),
              input_tax: (certifiedTax + selectedPlanTax).toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }),
              deductible_tax: deductibleTax.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }),
              result_label: "本月应纳税额",
              result_amount: resultAmount.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }),
            },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    expect(within(getStatCard("已认证结果进项税额")).getByText("0.00")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /11203490/ })).not.toBeDisabled();
    expect(screen.getAllByText("当前分组暂无记录")).toHaveLength(2);

    await user.click(document.body);
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });

    await waitFor(() =>
      expect(within(getStatCard("已认证结果进项税额")).getByText("14,080.00")).toBeInTheDocument(),
    );
    expect(screen.getByRole("checkbox", { name: /11203490/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /11203999/ })).toBeInTheDocument();
  });
});
