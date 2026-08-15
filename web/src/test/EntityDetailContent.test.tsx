import { render, screen } from "@testing-library/react";

import EntityDetailContent, {
  preparePublicDetailSections,
} from "../components/common/EntityDetailContent";

describe("EntityDetailContent", () => {
  test("normalizes public fields, preserves zero values, and removes internal or raw data", () => {
    const sections = preparePublicDetailSections([
      {
        title: "OA信息",
        fields: [
          { label: "applicant", value: "张三" },
          { label: "status", value: "unpaired" },
          { label: "amount", value: 0 },
          { label: "relation_case_id", value: "CASE-001" },
          { label: "调试备注", value: "不应展示未知字段" },
        ],
      },
      {
        title: "OA主信息",
        fields: [{ label: "project_name", value: "年度检修项目" }],
      },
      {
        title: "银行原始字段",
        fields: [{ label: "摘要", value: "不应展示" }],
      },
      {
        title: "详情",
        fields: [{ label: "备注", value: '{"raw":"payload"}' }],
      },
    ]);

    expect(sections).toEqual([
      {
        title: "基本信息",
        fields: [
          { label: "申请人", value: "张三" },
          { label: "状态", value: "未配对" },
          { label: "金额", value: 0 },
          { label: "项目名称", value: "年度检修项目" },
        ],
      },
    ]);

    render(<EntityDetailContent sections={sections} />);

    expect(screen.getByRole("heading", { name: "基本信息" })).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("未配对")).toBeInTheDocument();
    expect(screen.queryByText("CASE-001")).not.toBeInTheDocument();
    expect(screen.queryByText("不应展示")).not.toBeInTheDocument();
    expect(screen.queryByText("不应展示未知字段")).not.toBeInTheDocument();
  });

  test("renders a safe OA link and the unavailable state", () => {
    const { rerender } = render(
      <EntityDetailContent
        sections={preparePublicDetailSections([
          { title: "基本信息", fields: [{ label: "打开链接", value: "https://oa.example.test/detail/1" }] },
        ])}
      />,
    );

    expect(screen.getByRole("link", { name: "打开 OA 详情" })).toHaveAttribute(
      "href",
      "https://oa.example.test/detail/1",
    );

    rerender(<EntityDetailContent detailAvailable={false} sections={[]} unavailableReason="未返回公开详情" />);
    expect(screen.getByText("未返回公开详情")).toBeInTheDocument();
  });
});
