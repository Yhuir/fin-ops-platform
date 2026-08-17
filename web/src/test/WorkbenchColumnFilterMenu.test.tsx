import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import WorkbenchColumnFilterMenu from "../components/workbench/WorkbenchColumnFilterMenu";

describe("Workbench grouped column filter menu", () => {
  test("renders grouped project and expense options without flattening long labels", async () => {
    const onChange = vi.fn();
    render(
      <WorkbenchColumnFilterMenu
        columnKey="projectName"
        label="项目名称"
        loadFilterOptions={async () => ({
          options: [
            { value: "expenseType:交通费", label: "交通费", missing: false, group: "OA 费用类型" },
            {
              value: "project:2024年-2027年玉溪卷烟厂动力车间供配电、复烤二车间能源系统维护项目",
              label: "2024年-2027年玉溪卷烟厂动力车间供配电、复烤二车间能源系统维护项目",
              missing: false,
              group: "项目名称",
            },
          ],
          pageSize: 100,
          hasMore: false,
          nextCursor: null,
        })}
        onChange={onChange}
        onClose={() => undefined}
        open
        paneId="oa"
        selectedValues={[]}
        zoneId="unpaired"
      />,
    );

    expect(await screen.findByText("OA 费用类型")).toBeInTheDocument();
    expect(screen.getByText("项目名称", { selector: ".column-filter-option-group" })).toBeInTheDocument();
    const longProject = screen.getByText(/2024年-2027年玉溪卷烟厂动力车间供配电/);
    expect(longProject.closest("label")).toHaveClass("column-filter-option");
    expect(document.querySelector(".column-filter-popover--wide")).toBeInTheDocument();

    await userEvent.click(longProject);
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([
      "project:2024年-2027年玉溪卷烟厂动力车间供配电、复烤二车间能源系统维护项目",
    ]));
  });
});
