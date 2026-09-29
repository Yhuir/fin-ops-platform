import { act, render, screen, waitFor } from '@testing-library/react';
import { useSourceDetail } from '../features/useSourceDetail';

function Probe({id, load}: {id: string | null; load: (id: string, signal?: AbortSignal) => Promise<string>}) {
  const result = useSourceDetail(id !== null, id, load);
  return <div>{result.loading ? 'loading' : result.error ?? result.detail}</div>;
}
test('switch and close abort reads and reject late results from the previous document', async () => {
  const pending = new Map<string, (value: string) => void>();
  const signals = new Map<string, AbortSignal>();
  const load = (id: string, signal?: AbortSignal) => { signals.set(id, signal!); return new Promise<string>(resolve => pending.set(id, resolve)); };
  const {rerender} = render(<Probe id="first" load={load} />);
  rerender(<Probe id="second" load={load} />);
  expect(signals.get('first')!.aborted).toBe(true);
  await act(async () => pending.get('second')!('second detail'));
  expect(screen.getByText('second detail')).toBeInTheDocument();
  await act(async () => pending.get('first')!('stale detail'));
  expect(screen.queryByText('stale detail')).not.toBeInTheDocument();
  rerender(<Probe id={null} load={load} />);
  expect(signals.get('second')!.aborted).toBe(true);
  expect(screen.queryByText('second detail')).not.toBeInTheDocument();
});
test('source failure is explicit and does not display a list summary', async () => {
  const load = vi.fn().mockRejectedValue(new Error('原始单据不可用'));
  render(<Probe id="missing" load={load} />);
  await waitFor(() => expect(screen.getByText('原始单据不可用')).toBeInTheDocument());
});
