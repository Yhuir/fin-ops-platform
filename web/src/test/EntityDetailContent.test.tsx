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

const invoiceDocuments = [0, 1, 2].map(index => ({
  title: '发票信息', document_id: `invoice-${index}`, document_kind: 'invoice' as const,
  document_title: '旧标题不应进入发票导航',
  invoice_navigation: {polarity: index === 1 ? '红字' : '蓝字', counterpartyName: '相同公司',
    totalWithTax: index === 1 ? '-0.005' : '0.00', invoiceDate: '2026-10-02'},
  fields: [{label: '发票号码', value: `123456789${index}`}],
}));

test('invoice grid uses source summaries, preserves identities and scroll, and honors the switch guard', () => {
  const guard = vi.fn(() => false);
  const {rerender, container} = render(<div className="finance-drawer__body"><EntityDetailContent sections={invoiceDocuments} beforeDocumentChange={guard} /></div>);
  const body = container.firstElementChild!;
  body.scrollTop = 70;
  expect(screen.getAllByRole('tab')).toHaveLength(3);
  expect(screen.queryByText('旧标题不应进入发票导航')).not.toBeInTheDocument();
  expect(screen.getByText('-0.005')).toBeVisible();
  fireEvent.click(screen.getAllByRole('tab')[1]);
  expect(screen.getAllByRole('tab')[0]).toHaveAttribute('aria-selected', 'true');
  guard.mockReturnValue(true);
  fireEvent.click(screen.getAllByRole('tab')[1]);
  expect(body.scrollTop).toBe(70);
  expect(screen.getByRole('cell', {name: '1234567891'})).toBeVisible();
  expect(screen.queryByRole('cell', {name: '1234567890'})).not.toBeInTheDocument();
  expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
  rerender(<EntityDetailContent sections={invoiceDocuments.slice(0, 1)} />);
  expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
});


test('invoice details preserve source tax text, true zero and missing values', () => {
  const section = {...invoiceDocuments[0], title: '金额与税额', fields: [
    {label: '税率', value: '免税'},
    {label: '不含税金额', value: '0.00'},
    {label: '税额', value: '*'},
    {label: '价税合计', value: '—'},
  ]};
  render(<EntityDetailContent sections={[section]} />);
  for (const value of ['免税', '0.00', '*', '—']) {
    expect(screen.getByRole('cell', {name: value, exact: true})).toBeVisible();
  }
});

test('all source line items stay with their invoice and remain numbered after switching', () => {
  const lineSections = Array.from({length: 5}, (_, index) => ({
    ...invoiceDocuments[0], title: `货物或应税劳务明细 ${index + 1}`,
    fields: [{label: '货物或应税劳务名称', value: `真实商品 ${index + 1}`}],
  }));
  render(<EntityDetailContent sections={[invoiceDocuments[0], ...lineSections, invoiceDocuments[1]]} />);
  expect(screen.getAllByRole('heading', {name: /货物或应税劳务明细/})).toHaveLength(5);
  fireEvent.click(screen.getAllByRole('tab')[1]);
  expect(screen.queryByRole('heading', {name: /货物或应税劳务明细/})).not.toBeInTheDocument();
  fireEvent.click(screen.getAllByRole('tab')[0]);
  for (let index = 1; index <= 5; index++) {
    expect(screen.getByRole('heading', {name: `货物或应税劳务明细 ${index}`})).toBeVisible();
    expect(screen.getByRole('cell', {name: `真实商品 ${index}`})).toBeVisible();
  }
});

test('bank grid keeps raw directions, labels and identity together without moving scroll', () => {
  const sections = [0, 1, 2].flatMap(index => {
    const labels = index === 2 ? [] : [index === 0 ? '货款 / 设备采购' : '退款'];
    const meta = {document_id: `bank-${index}`, document_kind: 'bank' as const,
      bank_navigation: {counterpartyName: '同名公司', amount: index === 1 ? '35.00' : '1050.00',
        direction: index === 1 ? '收入' : '支出', transactionDate: '2026-06-10', labels}};
    return [{...meta, title: '交易信息', fields: [{label: '备注', value: `原始流水${index}`}]},
      {...meta, title: '业务分类', fields: [], bank_labels: labels}];
  });
  const {container} = render(<div className="finance-drawer__body"><EntityDetailContent sections={preparePublicDetailSections(sections)} /></div>);
  const body = container.firstElementChild!;
  body.scrollTop = 123;
  expect(screen.getAllByRole('tab')).toHaveLength(3);
  expect(screen.getAllByRole('tab')[0]).toHaveTextContent('支出1050.00');
  fireEvent.click(screen.getAllByRole('tab')[1]);
  expect(screen.getAllByRole('tab')[1]).toHaveTextContent('收入35.00');
  expect(screen.getByRole('cell', {name: '退款'})).toBeVisible();
  expect(screen.queryByRole('cell', {name: '货款 / 设备采购'})).not.toBeInTheDocument();
  expect(screen.getByRole('cell', {name: '原始流水1'})).toBeVisible();
  expect(body.scrollTop).toBe(123);
  expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
  fireEvent.click(screen.getAllByRole('tab')[2]);
  expect(screen.getByRole('cell', {name: '未设置标签'})).toBeVisible();
});
