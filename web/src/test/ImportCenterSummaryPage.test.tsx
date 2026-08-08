import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

describe("ImportCenterPage", () => {
  test("shows file history and switches to canonical batch history", async () => {
    window.history.pushState({}, "", "/imports");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "导入中心" })).toBeInTheDocument();
    expect(await screen.findByText("建行流水.xlsx")).toBeInTheDocument();
    expect(screen.getByText("财务用户")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/import-facts/files?page=1&page_size=50", expect.any(Object));

    await user.click(screen.getByRole("tab", { name: "导入批次" }));

    expect(await screen.findByText("来源文件")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/import-facts/batches?page=1&page_size=50", expect.any(Object));
  });
});
