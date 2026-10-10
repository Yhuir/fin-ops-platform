import { actorLabel, operationDateRange, outcomeView } from '../features/operationHistory/presentation';

test('preset dates use the Beijing business day across UTC and month boundaries', () => {
  expect(operationDateRange(7, new Date('2026-09-30T16:10:00Z'))).toEqual({ dateFrom: '2026-09-25', dateTo: '2026-10-01' });
  expect(operationDateRange(1, new Date('2026-09-30T15:59:59Z'))).toEqual({ dateFrom: '2026-09-30', dateTo: '2026-09-30' });
  expect(operationDateRange(30, new Date('2024-03-01T00:00:00+08:00'))).toEqual({ dateFrom: '2024-02-01', dateTo: '2024-03-01' });
});

test('missing completion is explicit and unknown contract outcomes fail visibly', () => {
  expect(outcomeView('unknown').label).toBe('结果未记录');
  expect(outcomeView('pending').label).toBe('进行中');
  expect(() => outcomeView('new-unregistered')).toThrow('未登记');
  expect(actorLabel({ actor_id: 'system', actor_name: null, actor_account: null })).toBe('系统');
});
