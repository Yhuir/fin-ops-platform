import { afterEach, describe, expect, test, vi } from "vitest";

import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
  eventAffectedMonths,
  subscribeFinanceDomainEvent,
} from "../features/domainEvents";

describe("domainEvents", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("normalizes affected months from camelCase and snake_case details", () => {
    expect(eventAffectedMonths(new CustomEvent("x", { detail: { affectedMonths: ["2026-03", ""] } }))).toEqual([
      "2026-03",
    ]);
    expect(eventAffectedMonths(new CustomEvent("x", { detail: { affected_months: ["2026-04"] } }))).toEqual([
      "2026-04",
    ]);
    expect(eventAffectedMonths(new Event("x"))).toEqual([]);
  });

  test("subscribes and emits typed finance domain events", () => {
    const handler = vi.fn();
    const unsubscribe = subscribeFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, handler);

    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      affectedMonths: ["2026-05"],
      source: "test",
    });
    unsubscribe();
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      affectedMonths: ["2026-06"],
      source: "after-unsubscribe",
    });

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler.mock.calls[0][0].detail).toEqual({
      affectedMonths: ["2026-05"],
      source: "test",
    });
  });

  test("receives finance domain events from another tab broadcast channel", async () => {
    class FakeBroadcastChannel {
      static channels: FakeBroadcastChannel[] = [];

      name: string;
      onmessage: ((event: MessageEvent) => void) | null = null;
      private closed = false;

      constructor(name: string) {
        this.name = name;
        FakeBroadcastChannel.channels.push(this);
      }

      postMessage(data: unknown) {
        FakeBroadcastChannel.channels.forEach((channel) => {
          if (channel === this || channel.closed || channel.name !== this.name) {
            return;
          }
          channel.onmessage?.({ data } as MessageEvent);
        });
      }

      close() {
        this.closed = true;
      }
    }
    vi.resetModules();
    vi.stubGlobal("BroadcastChannel", FakeBroadcastChannel);
    const {
      FINANCE_DOMAIN_EVENTS: isolatedEvents,
      subscribeFinanceDomainEvent: isolatedSubscribe,
    } = await import("../features/domainEvents");
    const handler = vi.fn();
    const unsubscribe = isolatedSubscribe(isolatedEvents.bankAutoTagRulesUpdated, handler);
    const receivingChannel = FakeBroadcastChannel.channels[0];

    receivingChannel.onmessage?.({ data: {
      eventName: isolatedEvents.bankAutoTagRulesUpdated,
      detail: { version: 8, source: "other-tab" },
      origin: "other-origin",
    } } as MessageEvent);

    unsubscribe();
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler.mock.calls[0][0].detail).toEqual({ version: 8, source: "other-tab" });
  });
});
