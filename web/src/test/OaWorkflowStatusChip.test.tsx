import { render, screen } from "@testing-library/react";

import OaWorkflowStatusChip from "../components/common/OaWorkflowStatusChip";

describe("OaWorkflowStatusChip", () => {
  test.each([
    ["completed", "已完成", "completed"],
    ["in_progress", "进行中", "in_progress"],
    [undefined, "状态未知", "unknown"],
  ])("renders canonical workflow status %s", (status, label, canonicalStatus) => {
    render(<OaWorkflowStatusChip status={status} />);

    const chip = screen.getByLabelText(`OA流程状态：${label}`);
    expect(chip).toHaveTextContent(label);
    expect(chip).toHaveAttribute("data-workflow-status", canonicalStatus);
  });
});
