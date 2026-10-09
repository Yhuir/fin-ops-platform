import userEvent from '@testing-library/user-event';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import BankSplitEditor from '../features/bankSplits/BankSplitEditor';
import BankTransactionDetailContent from '../features/bankSplits/BankTransactionDetailContent';
import SourceDetailDrawer from '../features/SourceDetailDrawer';
import { fetchBankSplits, saveBankSplits, type BankSplitDetail } from '../features/bankSplits/api';
import { ApiClientError } from '../features/apiClient';
import { amountCents, centsText } from '../features/bankSplits/amount';

vi.mock('../features/bankSplits/api', () => ({ fetchBankSplits: vi.fn(), saveBankSplits: vi.fn() }));
const detail: BankSplitDetail = {
  transaction_id: 'bank-1', canonical_transaction_id: 'canonical-1', amount: '1001497.22', direction: 'expense', version: 2,
  category_code: 'principal', category_label_path: ['外部往来款', '归还借款', '银行往来'], turnover_third_label_options: [{ value: '银行往来', label: '银行往来' }, { value: '公司往来', label: '公司往来' }], can_edit: true,
  parts: [
    { id: 'part-1', category_code: 'principal', category_label: '外部往来款 / 归还借款', category_path: ['外部往来款', '归还借款', '银行往来'], amount: '1000000.00' },
    { id: 'part-2', category_code: 'interest', category_label: '费用 / 利息', category_path: ['费用', '利息'], amount: '1497.22' },
  ],
  tag_definitions: [
    { code: 'principal', label: '外部往来款 / 归还借款', path: ['外部往来款', '归还借款'], primary_label: '外部往来款', sub_label: '归还借款', status: 'active', turnover_role: 'external_turnover' },
    { code: 'interest', label: '费用 / 利息', path: ['费用', '利息'], primary_label: '费用', sub_label: '利息', status: 'active', turnover_role: '' },
  ],
};
beforeEach(() => { vi.clearAllMocks(); vi.mocked(fetchBankSplits).mockResolvedValue(detail); });

test('amount arithmetic remains exact beyond floating point precision and rejects invalid input', () => {
  expect(amountCents('1001497.22')).toBe(100149722n);
  expect(centsText(amountCents('900719925474099.99')! + 1n)).toBe('900719925474100.00');
  for (const value of ['', '1.001', '-2', '1e3', 'NaN']) expect(amountCents(value)).toBeNull();
});

test('loads complete saved parts and saves stable identities, then uses returned version', async () => {
  const onSaved = vi.fn();
  vi.mocked(saveBankSplits).mockResolvedValue({ ...detail, version: 3, changed: true, affected_months: ['2026-04'] });
  render(<BankSplitEditor transactionId="part-2" onSaved={onSaved} />);
  expect(await screen.findByLabelText('子项 1 金额')).toHaveValue('1000000.00');
  expect(fetchBankSplits).toHaveBeenCalledWith('part-2', expect.any(AbortSignal));
  fireEvent.change(screen.getByLabelText('子项 2 金额'), { target: { value: '1497.20' } });
  fireEvent.change(screen.getByLabelText('子项 1 金额'), { target: { value: '1000000.02' } });
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  await waitFor(() => expect(saveBankSplits).toHaveBeenCalledWith('part-2', { version: 2, parts: [
    { id: 'part-1', category_code: 'principal', category_label_path: ['外部往来款', '归还借款', '银行往来'], amount: '1000000.02' },
    { id: 'part-2', category_code: 'interest', category_label_path: ['费用', '利息'], amount: '1497.20' },
  ] }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  expect(await screen.findByText('已保存')).toBeInTheDocument();
});

test('adds and removes draft items without writes, checks total, and cancels locally', async () => {
  render(<BankSplitEditor transactionId="bank-1" />);
  await screen.findByLabelText('子项 1 金额');
  fireEvent.click(screen.getByRole('button', { name: '新增流水子项' }));
  expect(screen.getByLabelText('子项 3 金额')).toHaveValue('');
  expect(saveBankSplits).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '删除子项 3' }));
  fireEvent.change(screen.getByLabelText('子项 2 金额'), { target: { value: '1497.21' } });
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  expect(await screen.findByRole('alert')).toHaveTextContent('子项合计必须等于流水金额');
  expect(saveBankSplits).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '取消' }));
  expect(screen.getByLabelText('子项 2 金额')).toHaveValue('1497.22');
});

test('completes external tags in the third column without a separate selector', async () => {
  render(<BankSplitEditor transactionId="bank-1" />);
  fireEvent.click(await screen.findByRole('combobox', { name: '子项 2 标签' }));
  const primary = await screen.findByRole('listbox', { name: '主标签' });
  await userEvent.click(within(primary).getByRole('option', { name: '外部往来款' }));
  const child = await screen.findByRole('listbox', { name: '子标签' });
  await userEvent.click(within(child).getByRole('option', { name: '归还借款' }));
  expect(screen.getByLabelText('子项 2 标签', { selector: '[role=combobox]' })).toHaveTextContent('费用 / 利息');
  await userEvent.click(within(screen.getByRole('listbox', { name: '往来归属' })).getByRole('option', { name: '银行往来' }));
  expect(screen.getByRole('combobox', { name: '子项 2 标签' })).toHaveTextContent('外部往来款 / 归还借款 / 银行往来');
  expect(saveBankSplits).not.toHaveBeenCalled();
});

test('keeps draft and exposes version conflict without retrying the write', async () => {
  vi.mocked(saveBankSplits).mockRejectedValue(new ApiClientError('流水已被修改', { status: 409, url: '/splits' }));
  render(<BankSplitEditor transactionId="bank-1" />);
  await screen.findByLabelText('子项 1 金额');
  fireEvent.change(screen.getByLabelText('子项 2 金额'), { target: { value: '1497.2' } });
  fireEvent.change(screen.getByLabelText('子项 2 金额'), { target: { value: '1497.22' } });
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  expect(await screen.findByRole('alert')).toHaveTextContent('流水已被修改');
  expect(screen.getByLabelText('子项 2 金额')).toHaveValue('1497.22');
  expect(screen.getByRole('button', { name: '保存', exact: true })).toBeDisabled();
  expect(saveBankSplits).toHaveBeenCalledOnce();
});

test('read-only permission disables mutations and non-bank detail does not load split data', async () => {
  const view = render(<BankTransactionDetailContent sections={[{ title: '基本信息', fields: [{ label: '金额', value: '10' }] }]} />);
  expect(fetchBankSplits).not.toHaveBeenCalled();
  vi.mocked(fetchBankSplits).mockResolvedValue({ ...detail, can_edit: false });
  view.rerender(<BankTransactionDetailContent bankTransactionId="bank-1" sections={[{ title: '交易信息', fields: [{ label: '金额', value: detail.amount }] }]} />);
  expect(fetchBankSplits).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: '流水子项拆分'}));
  expect(await screen.findByRole('button', { name: '新增流水子项' })).toBeDisabled();
  expect(screen.getByLabelText('子项 1 金额')).toBeDisabled();
});

test('unsplit transaction starts empty and adding items never writes guessed labels or amounts', async () => {
  vi.mocked(fetchBankSplits).mockResolvedValue({ ...detail, parts: [], version: 0 });
  render(<BankSplitEditor transactionId="bank-1" />);
  fireEvent.click(await screen.findByRole('button', { name: '新增流水子项' }));
  expect(screen.getByLabelText('子项 1 金额')).toHaveValue('');
  expect(screen.getByRole('combobox', { name: '子项 1 标签' })).toHaveTextContent('选择标签');
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  expect(screen.getByRole('alert')).toHaveTextContent('拆分至少需要两个子项');
  expect(saveBankSplits).not.toHaveBeenCalled();
});

test('removing every part restores an explicitly selected whole-transaction category', async () => {
  vi.mocked(saveBankSplits).mockResolvedValue({ ...detail, parts: [], version: 3, changed: true, affected_months: [] });
  render(<BankSplitEditor transactionId="bank-1" />);
  fireEvent.click(await screen.findByRole('button', { name: '删除子项 2' }));
  fireEvent.click(screen.getByRole('button', { name: '删除子项 1' }));
  expect(screen.getByRole('combobox', { name: '整笔流水标签' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  await waitFor(() => expect(saveBankSplits).toHaveBeenCalledWith('bank-1', { version: 2, parts: [], category_code: 'principal', category_label_path: ['外部往来款', '归还借款', '银行往来'] }));
});

test('bank detail sections read each editor only after its operation is opened', async () => {
  render(<BankTransactionDetailContent sections={[
    { title: '交易信息', bank_transaction_id: 'first-bank', fields: [{ label: '金额', value: '1001497.22' }] },
    { title: '交易信息', bank_transaction_id: 'second-bank', fields: [{ label: '金额', value: '1001497.22' }] },
  ]} />);
  expect(fetchBankSplits).not.toHaveBeenCalled();
  for (const button of screen.getAllByRole('button', {name: '流水子项拆分'})) fireEvent.click(button);
  await waitFor(() => expect(screen.getAllByLabelText('子项 1 金额')).toHaveLength(2));
  expect(fetchBankSplits).toHaveBeenCalledTimes(2);
  expect(fetchBankSplits).toHaveBeenCalledWith('first-bank', expect.any(AbortSignal));
  expect(fetchBankSplits).toHaveBeenCalledWith('second-bank', expect.any(AbortSignal));
});

test('failed persistence retains edits and never announces success', async () => {
  vi.mocked(saveBankSplits).mockRejectedValue(new Error('数据库写入失败'));
  render(<BankSplitEditor transactionId="bank-1" />);
  await screen.findByLabelText('子项 1 金额');
  fireEvent.change(screen.getByLabelText('子项 1 金额'), { target: { value: '1000001.00' } });
  fireEvent.change(screen.getByLabelText('子项 2 金额'), { target: { value: '1496.22' } });
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  expect(await screen.findByRole('alert')).toHaveTextContent('数据库写入失败');
  expect(screen.getByLabelText('子项 1 金额')).toHaveValue('1000001.00');
  expect(screen.queryByText('已保存')).not.toBeInTheDocument();
});


test('saving one bank and refreshing its page retains the other bank draft without refetching split facts', async () => {
  vi.mocked(saveBankSplits).mockResolvedValue({ ...detail, version: 3, changed: true, affected_months: ['2026-04'] });
  const refresh = vi.fn();
  const sections = [
    { title: '第一笔', bank_transaction_id: 'bank-1', fields: [{ label: '金额', value: detail.amount }] },
    { title: '第二笔', bank_transaction_id: 'second-bank', fields: [{ label: '金额', value: detail.amount }] },
  ];
  const { rerender } = render(<BankTransactionDetailContent sections={sections} onBankSplitSaved={refresh} />);
  expect(fetchBankSplits).not.toHaveBeenCalled();
  for (const button of screen.getAllByRole('button', {name: '流水子项拆分'})) fireEvent.click(button);
  await waitFor(() => expect(screen.getAllByLabelText('子项 1 金额')).toHaveLength(2));
  fireEvent.change(screen.getAllByLabelText('子项 1 金额')[1], { target: { value: '999999.00' } });
  fireEvent.change(screen.getAllByLabelText('子项 2 金额')[1], { target: { value: '1498.22' } });
  fireEvent.change(screen.getAllByLabelText('子项 1 金额')[0], { target: { value: '1000000.0' } });
  fireEvent.click(screen.getAllByRole('button', { name: '保存', exact: true })[0]);
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  rerender(<BankTransactionDetailContent sections={sections.map(section => ({ ...section }))} onBankSplitSaved={refresh} />);
  expect(screen.getAllByLabelText('子项 1 金额')[1]).toHaveValue('999999.00');
  expect(screen.getAllByLabelText('子项 2 金额')[1]).toHaveValue('1498.22');
  expect(screen.getByRole('button', { name: '保存', exact: true })).toBeEnabled();
  expect(fetchBankSplits).toHaveBeenCalledTimes(2);
  expect(saveBankSplits).toHaveBeenCalledOnce();
});


test('external instance family is human-selected and remains in the complete save path', async () => {
  vi.mocked(saveBankSplits).mockResolvedValue({ ...detail, version: 3, changed: true, affected_months: [] });
  render(<BankSplitEditor transactionId="bank-1" />);
  fireEvent.click(await screen.findByRole('combobox', { name: '子项 1 标签' }));
  expect(screen.queryByLabelText('子项 1 往来归属')).not.toBeInTheDocument();
  await userEvent.click(within(screen.getByRole('listbox', { name: '往来归属' })).getByRole('option', { name: '公司往来' }));
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  await waitFor(() => expect(saveBankSplits).toHaveBeenCalledWith('bank-1', expect.objectContaining({ parts: [
    { id: 'part-1', category_code: 'principal', amount: '1000000.00', category_label_path: ['外部往来款', '归还借款', '公司往来'] },
    { id: 'part-2', category_code: 'interest', amount: '1497.22', category_label_path: ['费用', '利息'] },
  ] })));
});

test('incomplete external selection closes without changing the saved label or another item', async () => {
  render(<BankSplitEditor transactionId="bank-1" />);
  fireEvent.click(await screen.findByRole('combobox', { name: '子项 2 标签' }));
  await userEvent.click(within(screen.getByRole('listbox', { name: '主标签' })).getByRole('option', { name: '外部往来款' }));
  await userEvent.click(within(screen.getByRole('listbox', { name: '子标签' })).getByRole('option', { name: '归还借款' }));
  fireEvent.keyDown(screen.getByRole('listbox', { name: '往来归属' }), { key: 'Escape' });
  expect(screen.getByRole('combobox', { name: '子项 2 标签' })).toHaveTextContent('费用 / 利息');
  expect(screen.getByRole('combobox', { name: '子项 1 标签' })).toHaveTextContent('外部往来款 / 归还借款 / 银行往来');
  expect(screen.queryByRole('button', { name: '保存', exact: true })).not.toBeInTheDocument();
  expect(saveBankSplits).not.toHaveBeenCalled();
});

test('bank details expose delete only and preserve read-only controls', async () => {
  vi.mocked(fetchBankSplits).mockResolvedValue({ ...detail, can_edit: false });
  render(<BankTransactionDetailContent bankTransactionId="bank-1" sections={[{ title: '交易信息', fields: [] }]} />);
  fireEvent.click(screen.getByRole('button', {name: '流水子项拆分'}));
  expect(await screen.findByRole('button', { name: '删除子项 1' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '删除子项 2' })).toBeDisabled();
  expect(screen.queryByRole('button', { name: /选中/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('combobox', { name: '子项 1 标签' }));
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
});


test('restoring the whole transaction uses the same complete three-column selection', async () => {
  vi.mocked(saveBankSplits).mockResolvedValue({ ...detail, parts: [], version: 3, changed: true, affected_months: [] });
  render(<BankSplitEditor transactionId="bank-1" />);
  fireEvent.click(await screen.findByRole('button', { name: '删除子项 2' }));
  fireEvent.click(screen.getByRole('button', { name: '删除子项 1' }));
  fireEvent.click(screen.getByRole('combobox', { name: '整笔流水标签' }));
  await userEvent.click(within(screen.getByRole('listbox', { name: '往来归属' })).getByRole('option', { name: '公司往来' }));
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  await waitFor(() => expect(saveBankSplits).toHaveBeenCalledWith('bank-1', { version: 2, parts: [], category_code: 'principal', category_label_path: ['外部往来款', '归还借款', '公司往来'] }));
});

test('an unchanged historical part remains readable and savable but cannot be modified with a retired tag', async () => {
  const historic = { ...detail, tag_definitions: detail.tag_definitions.filter(tag => tag.code !== 'interest') };
  vi.mocked(fetchBankSplits).mockResolvedValue(historic);
  vi.mocked(saveBankSplits).mockResolvedValue({ ...historic, changed: false, affected_months: [] });
  render(<BankSplitEditor transactionId="bank-1" />);
  const amount = await screen.findByLabelText('子项 2 金额');
  expect(screen.getByRole('combobox', { name: '子项 2 标签' })).toHaveTextContent('费用 / 利息');
  fireEvent.change(amount, { target: { value: '1497.2' } });
  fireEvent.change(amount, { target: { value: '1497.22' } });
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  await screen.findByText('已保存');
  expect(saveBankSplits).toHaveBeenCalledOnce();
  fireEvent.change(amount, { target: { value: '1497.23' } });
  fireEvent.change(screen.getByLabelText('子项 1 金额'), { target: { value: '999999.99' } });
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  expect(screen.getByRole('alert')).toHaveTextContent('有效标签');
  expect(saveBankSplits).toHaveBeenCalledOnce();
});

const groupedBanks = ['bank-1', 'bank-2'].map((id, index) => ({
  title: '交易信息', document_id: id, document_kind: 'bank' as const,
  document_title: `公司 · ${index + 1}`, bank_transaction_id: id,
  bank_navigation: {counterpartyName: '公司', amount: `${index + 1}.00`, direction: '支出', transactionDate: null, labels: []},
  fields: [{label: '金额', value: detail.amount}],
}));

test('shared source drawer preserves a canceled draft and discards only after approval without eager split reads', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const onClose = vi.fn();
  render(<SourceDetailDrawer open target={{kind:'bank',id:'bank-1'}} sections={[groupedBanks[0]]} loading={false} onClose={onClose} />);
  expect(fetchBankSplits).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: '流水子项拆分'}));
  fireEvent.change(await screen.findByLabelText('子项 1 金额'), {target: {value: '999999.00'}});
  fireEvent.click(screen.getByRole('button', {name:'关闭详情抽屉'}));
  expect(confirm).toHaveBeenCalledOnce();
  expect(onClose).not.toHaveBeenCalled();
  expect(screen.getByLabelText('子项 1 金额')).toHaveValue('999999.00');
  expect(fetchBankSplits).toHaveBeenCalledOnce();
  confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole('button', {name:'关闭详情抽屉'}));
  expect(onClose).toHaveBeenCalledOnce();
  expect(saveBankSplits).not.toHaveBeenCalled();
  confirm.mockRestore();
});

test('shared source drawer cannot close a saving bank and saves against its original identity', async () => {
  let finish!: (value: Awaited<ReturnType<typeof saveBankSplits>>) => void;
  vi.mocked(saveBankSplits).mockReturnValue(new Promise(resolve => {finish = resolve;}));
  const confirm = vi.spyOn(window, 'confirm');
  const onClose = vi.fn();
  render(<SourceDetailDrawer open target={{kind:'bank',id:'bank-1'}} sections={[groupedBanks[0]]} loading={false} onClose={onClose} />);
  fireEvent.click(screen.getByRole('button', {name: '流水子项拆分'}));
  fireEvent.change(await screen.findByLabelText('子项 1 金额'), {target: {value: '1000000.0'}});
  fireEvent.click(screen.getByRole('button', {name: '保存', exact: true}));
  fireEvent.click(screen.getByRole('button', {name:'关闭详情抽屉'}));
  expect(onClose).not.toHaveBeenCalled();
  expect(confirm).not.toHaveBeenCalled();
  expect(saveBankSplits).toHaveBeenCalledWith('bank-1', expect.any(Object));
  finish({...detail, changed: true, version: 3, affected_months: []});
  await screen.findByText('已保存');
  fireEvent.click(screen.getByRole('button', {name:'关闭详情抽屉'}));
  expect(onClose).toHaveBeenCalledOnce();
  confirm.mockRestore();
});
