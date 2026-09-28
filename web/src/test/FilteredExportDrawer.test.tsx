import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, test, vi } from 'vitest';
import FilteredExportDrawer from '../components/common/FilteredExportDrawer';
import type { ExportSummary } from '../features/exports/types';

const summary: ExportSummary = { rowCount: 3, groups: [{ field: 'relation_status', label: '关联状态', options: [
  { value: 'no_oa', label: '未关联 OA', count: 2 }, { value: 'oa_with_bank', label: 'OA / 流水均已关联', count: 1 },
] }] };
afterEach(cleanup);
describe('独立导出筛选', () => {
  test('默认全量、清空为零、重新勾选、日期非法和关闭均不产生下载', async () => {
    const user = userEvent.setup(); const loadSummary = vi.fn().mockResolvedValue(summary);
    const download = vi.fn(); const close = vi.fn();
    render(<FilteredExportDrawer title="导出发票" unit="张" loadSummary={loadSummary} download={download} onClose={close} />);
    expect(await screen.findByText('导出 3 张')).toBeVisible();
    expect(loadSummary.mock.calls[0][0]).toEqual({ values: {}, startDate: '', endDate: '' });
    expect(screen.queryByRole('grid')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '清空' }));
    expect(screen.getByText('导出 0 张')).toBeVisible();
    expect(screen.getByRole('button', { name: '下载 Excel' })).toBeDisabled();
    expect(loadSummary).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('checkbox', { name: /未关联 OA/ }));
    await waitFor(() => expect(loadSummary.mock.calls.at(-1)?.[0].values).toEqual({ relation_status: ['no_oa'] }));
    fireEvent.change(screen.getByLabelText('导出开始日期'), { target: { value: '2026-09-28' } });
    fireEvent.change(screen.getByLabelText('导出结束日期'), { target: { value: '2026-09-01' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('开始日期不能晚于结束日期');
    expect(screen.getByRole('button', { name: '下载 Excel' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: '关闭导出发票' }));
    expect(close).toHaveBeenCalledTimes(1); expect(download).not.toHaveBeenCalled();
  });
  test('丢弃迟到统计、失败明确显示并可重试，下载失败不关闭抽屉', async () => {
    const user = userEvent.setup(); let resolveOld!: (value: ExportSummary) => void;
    const loadSummary = vi.fn().mockResolvedValueOnce(summary)
      .mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
      .mockResolvedValueOnce({ ...summary, rowCount: 1 })
      .mockRejectedValueOnce(new Error('统计暂不可用')).mockResolvedValue(summary);
    const download = vi.fn().mockRejectedValue(new Error('下载失败')); const close = vi.fn();
    render(<FilteredExportDrawer title="导出发票" unit="张" loadSummary={loadSummary} download={download} onClose={close} />);
    await screen.findByText('导出 3 张');
    await user.click(screen.getByRole('checkbox', { name: /未关联 OA/ }));
    expect(screen.getByRole('button', { name: '下载 Excel' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: '全选' }));
    expect(await screen.findByText('导出 1 张')).toBeVisible();
    await act(async () => { resolveOld({ ...summary, rowCount: 99 }); });
    expect(screen.queryByText('导出 99 张')).not.toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: /未关联 OA/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('统计暂不可用');
    expect(screen.getByRole('button', { name: '下载 Excel' })).toBeDisabled();
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: '重试' }));
    await screen.findByText('导出 3 张');
    await user.click(screen.getByRole('button', { name: '下载 Excel' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('下载失败');
    expect(download.mock.calls[0][0].values).toEqual({ relation_status: ['oa_with_bank'] });
    expect(close).not.toHaveBeenCalled();
  });
});
