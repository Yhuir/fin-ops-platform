import { render, screen } from "@testing-library/react";

import EntityDetailContent, {
  preparePublicDetailSections,
} from "../components/common/EntityDetailContent";

describe("EntityDetailContent", () => {
  test("shows source invoice type and verification state while hiding internal evidence", () => {
    const fields = [
      { label: "发票票种", value: "电子发票（普通发票）" },
      { label: "发票类型", value: "普通发票" },
      { label: "票种状态", value: "已确认" },
      { label: "原文", value: "免税" },
    ];
    const sections = preparePublicDetailSections([{title: "发票信息", fields: [
      ...fields,
      {label: "invoice_kind_evidence", value: '[{"file_id":"internal"}]'},
    ]}]);
    expect(sections[0].fields).toEqual(fields);
    render(<EntityDetailContent sections={sections} />);
    expect(screen.getByRole("rowheader", {name: "发票类型"}).parentElement).toHaveTextContent("普通发票");
    expect(screen.getByRole("rowheader", {name: "票种状态"}).parentElement).toHaveTextContent("已确认");
    expect(screen.getByRole("rowheader", {name: "原文"}).parentElement).toHaveTextContent("免税");
    expect(screen.queryByText("internal")).not.toBeInTheDocument();
  });

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
  {title: '申请信息', document_id: 'oa-1', document_kind: 'oa' as const, document_title: '张三 · 8000', oa_navigation: {applicantName: '张三', amount: '8000.00', applicationDate: '2026-08-01', workflowNo: null}, fields: [{label: 'OA单号', value: '2440'}]},
  {title: '费用明细 1', document_id: 'oa-1', document_kind: 'oa' as const, document_title: '张三 · 8000', oa_navigation: {applicantName: '张三', amount: '8000.00', applicationDate: '2026-08-01', workflowNo: null}, fields: [{label: '金额', value: 0}]},
  {title: '申请信息', document_id: 'oa-2', document_kind: 'oa' as const, document_title: '张三 · 8000', oa_navigation: {applicantName: '张三', amount: '8000.00', applicationDate: '2026-08-01', workflowNo: null}, fields: [{label: 'OA单号', value: '2441'}]},
];

test('one source document displays all its sections with no collection navigation', () => {
  render(<EntityDetailContent sections={documents.slice(0, 2)} />);
  expect(screen.getByText('2440')).toBeVisible();
  expect(screen.getByText('0')).toBeVisible();
  expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
});

test('multiple source documents fail visibly instead of selecting an arbitrary source', () => {
  render(<EntityDetailContent sections={documents} />);
  expect(screen.getByText('详情接口返回了多条单据，请重新选择单条详情。')).toBeVisible();
  expect(screen.queryByText('2440')).not.toBeInTheDocument();
  expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
});

test('one invoice keeps all source lines, original tax text, zero and missing values', () => {
  const meta = {document_id: 'invoice-1', document_kind: 'invoice' as const};
  render(<EntityDetailContent sections={[
    {...meta, title: '金额与税额', fields: [{label: '税率', value: '免税'}, {label: '不含税金额', value: '0.00'},
      {label: '税额', value: '*'}, {label: '价税合计', value: '—'}]},
    ...Array.from({length: 5}, (_, index) => ({...meta, title: `货物或应税劳务明细 ${index+1}`,
      fields: [{label: '货物或应税劳务名称', value: `真实商品 ${index+1}`}]}))
  ]} />);
  for (const value of ['免税', '0.00', '*', '—']) expect(screen.getByRole('cell', {name: value, exact: true})).toBeVisible();
  expect(screen.getAllByRole('heading', {name: /货物或应税劳务明细/})).toHaveLength(5);
});

test.each([{labels:['退款']}, {labels:[]}])('single bank source retains its tags: %j', ({labels}) => {
  render(<EntityDetailContent sections={[{title: '交易信息', document_id: 'bank-1', document_kind: 'bank',
    bank_labels: labels, fields: [{label: '备注', value: '原始流水'}, {label: '收入金额', value: '35.00'}]}]} />);
  expect(screen.getByRole('cell', {name: labels.length ? '退款' : '未设置标签'})).toBeVisible();
  expect(screen.getByRole('cell', {name: '35.00'})).toBeVisible();
});
