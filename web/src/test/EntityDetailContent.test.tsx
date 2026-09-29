import { fireEvent, render, screen } from "@testing-library/react";

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
        ],
      },
      { title: "基本信息", fields: [{ label: "项目名称", value: "年度检修项目" }],
      },
    ]);

    render(<EntityDetailContent sections={sections} />);

    expect(screen.getAllByRole("heading", { name: "基本信息" })).toHaveLength(2);
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

  test("preserves source text, false, zero tax, and date precision while localizing statuses", () => {
    const sections = preparePublicDetailSections([{ title: "基本信息", fields: [
      { label: "备注", value: "normal" },
      { label: "项目名称", value: "active" },
      { label: "流程状态", value: "completed" },
      { label: "是否正数发票", value: false },
      { label: "税额", value: 0 },
      { label: "开票日期", value: "2026-09-27" },
      { label: "申请时间", value: "2026-09-27T13:52" },
      { label: "交易时间", value: "2026-09-27T05:52Z" },
    ] }]);
    expect(sections[0].fields).toEqual([
      { label: "备注", value: "normal" },
      { label: "项目名称", value: "active" },
      { label: "流程状态", value: "已完成" },
      { label: "是否正数发票", value: false },
      { label: "税额", value: 0 },
      { label: "开票日期", value: "2026-09-27" },
      { label: "申请时间", value: "2026-09-27 13:52" },
      { label: "交易时间", value: "2026-09-27 13:52" },
    ]);
    render(<EntityDetailContent sections={sections} />);
    expect(screen.getByText("false")).toBeInTheDocument();
    expect(screen.getByText("normal")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});


test("public OA expense counts preserve zero while internal counts remain hidden", () => {
  const sections = preparePublicDetailSections([{ title: "费用明细 1", fields: [
    { label: "票据张数", value: 34 },
    { label: "附件文件数", value: 0 },
    { label: "expense_item_id", value: "private-item" },
    { label: "internal_count", value: 91 },
  ] }]);
  expect(sections).toEqual([{title: "费用明细 1", fields: [
    { label: "票据张数", value: 34 }, { label: "附件文件数", value: 0 },
  ]}]);
});

const documents = [
  {title: '申请信息', document_id: 'oa-1', document_kind: 'oa' as const, document_title: '张三 · 8000', fields: [{label: 'OA单号', value: '2440'}]},
  {title: '费用明细 1', document_id: 'oa-1', document_kind: 'oa' as const, document_title: '张三 · 8000', fields: [{label: '金额', value: 0}]},
  {title: '申请信息', document_id: 'oa-2', document_kind: 'oa' as const, document_title: '张三 · 8000', fields: [{label: 'OA单号', value: '2441'}]},
];

test('switches only the selected source document and all its sections using stable identities', () => {
  const {rerender} = render(<EntityDetailContent sections={documents} />);
  expect(screen.getByText('2440')).toBeVisible();
  expect(screen.getByText('0')).toBeVisible();
  expect(screen.queryByText('2441')).not.toBeInTheDocument();
  const second = screen.getByRole('tab', {name: '2 张三 · 8000'});
  fireEvent.click(second);
  expect(second).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText('2441')).toBeVisible();
  expect(screen.queryByText('2440')).not.toBeInTheDocument();
  expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
  rerender(<EntityDetailContent sections={documents.map(section => ({...section}))} />);
  expect(screen.getByText('2441')).toBeVisible();
  expect(screen.queryByRole('button', {name: /全部/})).not.toBeInTheDocument();
});

test('honors explicit initial selection and surfaces an invalid identity without selecting another record', () => {
  const {rerender} = render(<EntityDetailContent sections={documents} initialDocumentKey="oa:oa-2" />);
  expect(screen.getByText('2441')).toBeVisible();
  rerender(<EntityDetailContent sections={documents} initialDocumentKey="oa:missing" />);
  expect(screen.getByText('所选单据不在当前详情中。')).toBeVisible();
  expect(screen.queryByText('2440')).not.toBeInTheDocument();
});

test('plain and single-document sections have no navigation; switches reset only the drawer body scroll', () => {
  const {rerender,container} = render(<div className="finance-drawer__body"><EntityDetailContent sections={documents} /></div>);
  const body = container.firstElementChild!;
  body.scrollTop = 200;
  fireEvent.click(screen.getByRole('tab', {name: '1 张三 · 8000'}));
  expect(body.scrollTop).toBe(200);
  fireEvent.click(screen.getByRole('tab', {name: '2 张三 · 8000'}));
  expect(body.scrollTop).toBe(0);
  rerender(<EntityDetailContent sections={documents.slice(0,2)} />);
  expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  expect(screen.getByText('2440')).toBeVisible();
});
