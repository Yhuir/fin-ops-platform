import { expect } from "vitest";

type EventListenerSpy = {
  mock: {
    calls: unknown[][];
  };
};

export function expectCustomEventDetailContaining(
  listener: EventListenerSpy,
  expectedDetail: Record<string, unknown>,
) {
  expect(listener).toHaveBeenCalled();
  const details = listener.mock.calls.map((call) => (call[0] as CustomEvent | undefined)?.detail);
  expect(details).toContainEqual(expect.objectContaining(expectedDetail));
}
