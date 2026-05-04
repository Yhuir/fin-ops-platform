import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { installMockApiFetch } from "./apiMock";
import { renderWorkbenchPage } from "./renderHelpers";

function hasTextContent(expected: string) {
  return (_content: string, node: Element | null) => node?.textContent?.includes(expected) ?? false;
}

function wasSearchCalledWith(fetchMock: ReturnType<typeof installMockApiFetch>, expected: string) {
  return fetchMock.mock.calls.some(([url]) => typeof url === "string" && url === expected);
}

function findSearchParams(fetchMock: ReturnType<typeof installMockApiFetch>, predicate: (params: URLSearchParams) => boolean) {
  return fetchMock.mock.calls.some(([url]) => {
    if (typeof url !== "string" || !url.startsWith("/api/search?")) {
      return false;
    }
    return predicate(new URL(url, "http://localhost").searchParams);
  });
}

describe("Workbench global search modal and navigation", () => {
  test("opens the search modal and groups results by OA, bank, and invoice", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    expect(await screen.findByTestId("zone-open")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关联台搜索" }));

    const dialog = await screen.findByRole("dialog", { name: "关联台搜索" });
    expect(within(dialog).getByRole("tab", { name: "全部" })).toHaveClass("active");
    const projectFilter = within(dialog).getByLabelText("项目筛选");
    expect(within(projectFilter).getAllByRole("option").length).toBeGreaterThan(1);

    await user.type(
      within(dialog).getByPlaceholderText("搜索项目、公司、人名、发票号、流水号..."),
      "华东设备供应商",
    );
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));

    const oaSection = await within(dialog).findByRole("region", { name: "OA 搜索结果" });
    const bankSection = within(dialog).getByRole("region", { name: "银行流水 搜索结果" });
    const invoiceSection = within(dialog).getByRole("region", { name: "发票 搜索结果" });

    await waitFor(() => {
      expect(oaSection).toHaveTextContent("华东改造项目");
      expect(bankSection).toHaveTextContent("华东设备供应商");
      expect(invoiceSection).toHaveTextContent("00061345");
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/search?q=%E5%8D%8E%E4%B8%9C%E8%AE%BE%E5%A4%87%E4%BE%9B%E5%BA%94%E5%95%86&scope=all&month=all&limit=30",
      expect.any(Object),
    );
  });

  test("jumping to an open-zone result highlights the target row in the all-time workbench", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    expect(await screen.findByTestId("zone-open")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关联台搜索" }));
    const dialog = await screen.findByRole("dialog", { name: "关联台搜索" });
    await user.type(
      within(dialog).getByPlaceholderText("搜索项目、公司、人名、发票号、流水号..."),
      "张三广告",
    );
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));

    const bankSection = await within(dialog).findByRole("region", { name: "银行流水 搜索结果" });
    await waitFor(() => expect(bankSection).toHaveTextContent("杭州张三广告有限公司"));
    await user.click(within(bankSection).getByRole("button", { name: "跳转至" }));

    expect(screen.queryByRole("dialog", { name: "关联台搜索" })).not.toBeInTheDocument();
    const openZone = await screen.findByTestId("zone-open");
    const row = within(openZone).getByRole("row", {
      name: /2026-04-20.*杭州张三广告有限公司/,
    });
    expect(row).toHaveAttribute("data-search-highlighted", "true");
  });

  test("jumping to ignored and processed exception results opens the corresponding modal before highlighting", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    expect(await screen.findByTestId("zone-open")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关联台搜索" }));
    const dialog = await screen.findByRole("dialog", { name: "关联台搜索" });
    const input = within(dialog).getByPlaceholderText("搜索项目、公司、人名、发票号、流水号...");

    await user.type(input, "INV-IGN-001");
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));
    const invoiceSection = await within(dialog).findByRole("region", { name: "发票 搜索结果" });
    await waitFor(() => expect(invoiceSection).toHaveTextContent("INV-IGN-001"));
    await user.click(within(invoiceSection).getByRole("button", { name: "跳转至" }));

    const ignoredModal = await screen.findByRole("dialog", { name: "已忽略弹窗" });
    const ignoredRow = ignoredModal.querySelector<HTMLElement>("[data-row-id='iv-ignored-202604-001']");
    expect(ignoredRow).not.toBeNull();
    expect(ignoredRow).toHaveAttribute("data-search-highlighted", "true");

    await user.click(screen.getByRole("button", { name: "关闭已忽略弹窗" }));
    await user.click(screen.getByRole("button", { name: "关联台搜索" }));
    const nextDialog = await screen.findByRole("dialog", { name: "关联台搜索" });
    const nextInput = within(nextDialog).getByPlaceholderText("搜索项目、公司、人名、发票号、流水号...");
    await user.clear(nextInput);
    await user.type(nextInput, "SERIAL-EX-001");
    await user.click(within(nextDialog).getByRole("button", { name: "执行搜索" }));

    const nextBankSection = await within(nextDialog).findByRole("region", { name: "银行流水 搜索结果" });
    await waitFor(() => expect(nextBankSection).toHaveTextContent("异常供应商"));
    await user.click(within(nextBankSection).getByRole("button", { name: "跳转至" }));

    const processedModal = await screen.findByRole("dialog", { name: "已处理异常弹窗" });
    const processedRow = processedModal.querySelector<HTMLElement>("[data-row-id='bk-ex-202604-001']");
    expect(processedRow).not.toBeNull();
    expect(processedRow).toHaveAttribute("data-search-highlighted", "true");
  });

  test("applies scope, month, project, and status filters to search requests and grouped results", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    expect(await screen.findByTestId("zone-open")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关联台搜索" }));
    const dialog = await screen.findByRole("dialog", { name: "关联台搜索" });
    const input = within(dialog).getByPlaceholderText("搜索项目、公司、人名、发票号、流水号...");

    await user.type(input, "张三广告");
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));
    await within(dialog).findByRole("region", { name: "银行流水 搜索结果" });

    expect(within(dialog).getByText("时间范围")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "全时间" })).toHaveClass("active");

    await user.click(within(dialog).getByRole("tab", { name: "流水" }));
    await user.click(within(dialog).getByRole("button", { name: "按月份" }));
    await user.click(within(dialog).getByRole("button", { name: "搜索月份选择" }));
    await user.click(await screen.findByRole("radio", { name: "2026" }));
    await user.click(screen.getByRole("radio", { name: "四月" }));
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));

    const bankSection = await within(dialog).findByRole("region", { name: "银行流水 搜索结果" });
    await waitFor(() => expect(bankSection).toHaveTextContent("杭州张三广告有限公司"));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/search?q=%E5%BC%A0%E4%B8%89%E5%B9%BF%E5%91%8A&scope=bank&month=2026-04&limit=30",
      expect.any(Object),
    );

    await user.clear(input);
    await user.type(input, "建设银行 1138");
    await user.click(within(dialog).getByRole("button", { name: "全时间" }));
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));

    const allTimeBankSection = await within(dialog).findByRole("region", { name: "银行流水 搜索结果" });
    await waitFor(() => {
      expect(allTimeBankSection).toHaveTextContent("智能工厂设备商");
      expect(allTimeBankSection).toHaveTextContent("差旅服务商");
    });
    expect(
      fetchMock.mock.calls.some(([url]) => {
        if (typeof url !== "string" || !url.startsWith("/api/search?")) {
          return false;
        }
        const params = new URL(url, "http://localhost").searchParams;
        return params.get("q") === "建设银行 1138" && params.get("scope") === "bank" && params.get("month") === "all";
      }),
    ).toBe(true);

    await user.clear(input);
    await user.type(input, "INV-IGN-001");
    await user.click(within(dialog).getByRole("tab", { name: "发票" }));
    await user.click(within(dialog).getByRole("button", { name: "全时间" }));
    await user.selectOptions(within(dialog).getByLabelText("状态筛选"), "ignored");
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));

    const invoiceSection = await within(dialog).findByRole("region", { name: "发票 搜索结果" });
    await waitFor(() => {
      expect(invoiceSection).toHaveTextContent("INV-IGN-001");
      expect(invoiceSection).toHaveTextContent("已忽略");
    });
    expect(
      wasSearchCalledWith(fetchMock, "/api/search?q=INV-IGN-001&scope=invoice&month=all&limit=30&status=ignored"),
    ).toBe(true);

    await user.clear(input);
    await user.type(input, "云南溯源科技");
    await user.click(within(dialog).getByRole("tab", { name: "全部" }));
    await user.selectOptions(within(dialog).getByLabelText("状态筛选"), "all");
    const projectSelect = within(dialog).getByLabelText("项目筛选");
    const selectedProjectName = within(projectSelect)
      .getAllByRole("option")
      .map((option) => option.getAttribute("value") ?? "")
      .find((value) => value && value.includes("溯源"))
      ?? within(projectSelect).getAllByRole("option")[1]?.getAttribute("value")
      ?? "";
    await user.selectOptions(projectSelect, selectedProjectName);
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));

    await within(dialog).findByRole("region", { name: "OA 搜索结果" });
    await waitFor(() =>
      expect(
        findSearchParams(
          fetchMock,
          (params) =>
            params.get("q") === "云南溯源科技"
            && params.get("scope") === "all"
            && params.get("month") === "all"
            && params.get("project_name") === selectedProjectName,
        ),
      ).toBe(true),
    );
  }, 10000);

  test("shows loading, empty, and error states inside the search modal", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ searchDelayMs: 200, searchErrorQueries: ["爆炸"] });
    renderWorkbenchPage();

    expect(await screen.findByTestId("zone-open")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关联台搜索" }));
    const dialog = await screen.findByRole("dialog", { name: "关联台搜索" });
    const input = within(dialog).getByPlaceholderText("搜索项目、公司、人名、发票号、流水号...");

    await user.type(input, "张三");
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));
    expect(await within(dialog).findByText("正在搜索匹配记录...")).toBeInTheDocument();
    expect(await within(dialog).findByRole("region", { name: "银行流水 搜索结果" })).toHaveTextContent("杭州张三广告有限公司");

    await user.clear(input);
    await user.type(input, "完全不存在的记录");
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));
    expect(await within(dialog).findByText("未找到匹配记录，可调整关键词或筛选条件。")).toBeInTheDocument();
    expect(within(dialog).getByRole("region", { name: "OA 搜索结果" })).toHaveTextContent("当前分组暂无匹配结果。");
    expect(within(dialog).getByRole("region", { name: "银行流水 搜索结果" })).toHaveTextContent("当前分组暂无匹配结果。");
    expect(within(dialog).getByRole("region", { name: "发票 搜索结果" })).toHaveTextContent("当前分组暂无匹配结果。");

    await user.clear(input);
    await user.type(input, "爆炸");
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));
    expect(await within(dialog).findByText("search failed")).toBeInTheDocument();
  });

  test("opens detail from a search result and highlights only matched keyword fragments", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderWorkbenchPage();

    expect(await screen.findByTestId("zone-open")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关联台搜索" }));
    const dialog = await screen.findByRole("dialog", { name: "关联台搜索" });
    await user.type(
      within(dialog).getByPlaceholderText("搜索项目、公司、人名、发票号、流水号..."),
      "华东设备供应商",
    );
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));

    await waitFor(() =>
      expect(within(dialog).getByRole("region", { name: "银行流水 搜索结果" })).toHaveTextContent("华东设备供应商"),
    );
    const bankSection = within(dialog).getByRole("region", { name: "银行流水 搜索结果" });
    const marks = Array.from(bankSection.querySelectorAll("mark.workbench-search-highlight")).map((node) => node.textContent);

    expect(marks).toContain("华东设备供应商");
    expect(within(bankSection).queryByText(hasTextContent("命中："))).not.toBeInTheDocument();

    await user.click(within(bankSection).getByRole("button", { name: "详情" }));

    const detailDialog = await screen.findByRole("dialog", { name: "详情弹窗" });
    expect(detailDialog).toHaveTextContent("银行流水详情");
    expect(detailDialog).toHaveTextContent("记录编号：bk-p-202603-001");
  });

  test("asks the user to narrow all-time searches before sending a single-character query", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderWorkbenchPage();

    expect(await screen.findByTestId("zone-open")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关联台搜索" }));
    const dialog = await screen.findByRole("dialog", { name: "关联台搜索" });
    await user.type(within(dialog).getByPlaceholderText("搜索项目、公司、人名、发票号、流水号..."), "刘");
    await user.click(within(dialog).getByRole("button", { name: "执行搜索" }));

    expect(await within(dialog).findByText("全时间搜索请至少输入 2 个字，或切换到具体月份。")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => typeof url === "string" && url.startsWith("/api/search?")),
    ).toBe(false);
  });
});
