import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, test, vi } from 'vitest';
import FilteredExportDrawer from '../components/common/FilteredExportDrawer';
import type { ExportSummary } from '../features/exports/types';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
describe('当前范围导出确认', () => {
  test('只显示业务数量和一个主要操作，无筛选和预览，关闭不下载', async () => {
    const user = userEvent.setup();
    const loadSummary = vi.fn().mockResolvedValue({ rowCount: 17 });
    const download = vi.fn(); const close = vi.fn();
    render(<FilteredExportDrawer title="导出 OA" unit="条 OA" loadSummary={loadSummary} download={download} onClose={close} />);
    expect(await screen.findByText('即将导出 17 条 OA')).toBeVisible();
    expect(loadSummary.mock.calls[0][0]).toBeInstanceOf(AbortSignal);
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('grid')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(2);
    await user.click(screen.getByRole('button', { name: '关闭导出 OA' }));
    expect(close).toHaveBeenCalledOnce(); expect(download).not.toHaveBeenCalled();
  });
  test('空集禁止下载，缺失数量报错并使用同一个主要按钮重试', async () => {
    const user = userEvent.setup(); const download = vi.fn();
    const loadSummary = vi.fn().mockResolvedValueOnce({}).mockResolvedValue({ rowCount: 0 });
    render(<FilteredExportDrawer title="导出发票" unit="张发票" loadSummary={loadSummary} download={download} onClose={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('导出数量不完整或无效');
    await user.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByText('当前筛选范围没有可导出的数据')).toBeVisible();
    expect(screen.getByRole('button', { name: '导出' })).toBeDisabled();
    expect(download).not.toHaveBeenCalled();
  });
  test('下载失败保留范围且可重试，防止双击，成功显示实际数量', async () => {
    const user = userEvent.setup(); let finish!: (value: { blob: Blob; fileName: string; count: number }) => void;
    const loadSummary = vi.fn().mockResolvedValue({ rowCount: 3 });
    const download = vi.fn().mockRejectedValueOnce(new Error('下载失败')).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const close = vi.fn(); const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const create = vi.fn().mockReturnValue('blob:export'); const revoke = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }));
    render(<FilteredExportDrawer title="导出发票" unit="张发票" loadSummary={loadSummary} download={download} onClose={close} />);
    await screen.findByText('即将导出 3 张发票');
    await user.click(screen.getByRole('button', { name: '导出' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('下载失败');
    await user.dblClick(screen.getByRole('button', { name: '重试' }));
    expect(download).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: '关闭导出发票' })).toBeDisabled();
    await act(async () => finish({ blob: new Blob(['xlsx']), fileName: 'test.xlsx', count: 4 }));
    expect(await screen.findByText('已导出 4 张发票')).toBeVisible();
    expect(screen.queryByText('即将导出 3 张发票')).not.toBeInTheDocument();
    expect(screen.getAllByRole('status')).toHaveLength(1);
    expect(create).toHaveBeenCalledOnce(); expect(click).toHaveBeenCalledOnce();
    expect(close).not.toHaveBeenCalled(); expect(loadSummary).toHaveBeenCalledOnce();
    click.mockRestore();
  });
  test('关闭取消数量请求，迟到响应不会进入重新打开的抽屉', async () => {
    let resolveOld!: (value: ExportSummary) => void;
    const loadSummary = vi.fn().mockImplementation(() => new Promise(resolve => { resolveOld = resolve; }));
    const { unmount } = render(<FilteredExportDrawer title="导出发票" unit="张" loadSummary={loadSummary} download={vi.fn()} onClose={vi.fn()} />);
    await waitFor(() => expect(loadSummary).toHaveBeenCalledOnce());
    const signal = loadSummary.mock.calls[0][0] as AbortSignal;
    unmount(); expect(signal.aborted).toBe(true);
    render(<FilteredExportDrawer title="导出发票" unit="张" loadSummary={vi.fn().mockResolvedValue({ rowCount: 2 })} download={vi.fn()} onClose={vi.fn()} />);
    await screen.findByText('即将导出 2 张');
    await act(async () => resolveOld({ rowCount: 99 }));
    expect(screen.queryByText(/99/)).not.toBeInTheDocument();
  });
});
