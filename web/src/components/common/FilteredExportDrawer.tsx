import CountLabel from "./CountLabel";
import { Button, Checkbox, Input } from '@heroui/react';
import { useEffect, useState } from 'react';
import type { ExportSelection, ExportSummary } from '../../features/exports/types';
import AppDrawer from './AppDrawer';
import './filtered-export.css';

type Props = {
  title: string; unit: '张' | '笔'; onClose: () => void;
  initialSelection?: ExportSelection;
  loadSummary: (selection: ExportSelection, signal: AbortSignal) => Promise<ExportSummary>;
  download: (selection: ExportSelection) => Promise<{ blob: Blob; fileName: string }>;
};
export default function FilteredExportDrawer({ title, unit, onClose, loadSummary, download, initialSelection }: Props) {
  const [selection, setSelection] = useState<ExportSelection>(() => initialSelection ?? { values: {}, startDate: '', endDate: '' });
  const [result, setResult] = useState<{ selection: ExportSelection; summary: ExportSummary } | null>(null);
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [completed, setCompleted] = useState('');
  const empty = Object.values(selection.values).some(values => values.length === 0);
  const invalidDates = Boolean(selection.startDate && selection.endDate && selection.startDate > selection.endDate);
  const current = result?.selection === selection;
  const count = empty ? 0 : current ? result.summary.rowCount : null;
  useEffect(() => {
    setError(''); setCompleted('');
    if (empty || invalidDates) return;
    const controller = new AbortController();
    loadSummary(selection, controller.signal).then(summary => {
      if (!controller.signal.aborted) setResult({ selection, summary });
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '导出数量查询失败');
    });
    return () => controller.abort();
  }, [selection, empty, invalidDates, loadSummary]);
  async function handleDownload() {
    if (!current || !count || error || downloading || invalidDates) return;
    setDownloading(true); setError('');
    try {
      const { blob, fileName } = await download(selection);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = fileName;
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setCompleted(`已导出 ${fileName}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '导出失败'); }
    finally { setDownloading(false); }
  }
  function choose(field: string, values?: string[]) {
    setSelection(old => {
      const next = { ...old.values };
      if (values === undefined) delete next[field]; else next[field] = values;
      return { ...old, values: next };
    });
  }
  return <AppDrawer open title={title} closeLabel={`关闭${title}`} width="min(560px, 100vw)"
    closeDisabled={downloading} onClose={onClose} className="filtered-export-drawer"
    footer={<div className="filtered-export-footer"><strong aria-live="polite">导出 {count === null || invalidDates || error ? '—' : count.toLocaleString()} {unit}</strong>
      <Button variant="primary" isPending={downloading} isDisabled={!current || !count || Boolean(error) || invalidDates || downloading} onPress={handleDownload}>下载 Excel</Button></div>}>
    <div className="filtered-export-content">
      <fieldset disabled={downloading} className="filtered-export-fields" aria-busy={!current && !empty && !error && !invalidDates}>
        <section className="filtered-export-group"><h3>时间范围</h3><div className="filtered-export-dates">
          <label>开始日期<Input aria-label="导出开始日期" type="date" value={selection.startDate} onChange={e => setSelection(old => ({ ...old, startDate: e.target.value }))} /></label>
          <label>结束日期<Input aria-label="导出结束日期" type="date" value={selection.endDate} onChange={e => setSelection(old => ({ ...old, endDate: e.target.value }))} /></label>
        </div></section>
        {result?.summary.groups.map(group => <section key={group.field} className="filtered-export-group" aria-label={group.label}>
          <div className="filtered-export-group-heading"><h3>{group.label}</h3><div><Button size="sm" variant="ghost" onPress={() => choose(group.field)}>全选</Button><Button size="sm" variant="ghost" onPress={() => choose(group.field, [])}>清空</Button></div></div>
          <div className="filtered-export-options">{group.options.map(option => {
            const selected = selection.values[group.field];
            return <Checkbox key={option.value} isSelected={!selected || selected.includes(option.value)} className="filtered-export-option"
              onChange={() => choose(group.field, (selected ?? group.options.map(item => item.value)).includes(option.value)
                ? (selected ?? group.options.map(item => item.value)).filter(value => value !== option.value)
                : [...(selected ?? []), option.value])}>
              <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><span className="filtered-export-label">{option.label}</span><span className="filtered-export-count"><CountLabel value={error ? undefined : option.count} unit={unit} spaced /></span>
            </Checkbox>;
          })}</div>
        </section>)}
      </fieldset>
      <div className="filtered-export-status" role="status">{!current && !empty && !error && !invalidDates ? "正在统计…" : ""}</div>
      {invalidDates ? <div role="alert">开始日期不能晚于结束日期。</div> : null}
      {error ? <div role="alert">{error}<Button variant="ghost" onPress={() => setSelection(old => ({ ...old }))}>重试</Button></div> : null}
      {completed ? <div role="status">{completed}</div> : null}
    </div>
  </AppDrawer>;
}
