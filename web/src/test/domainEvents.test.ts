import { describe, expect, test, vi } from "vitest";

import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
  eventAffectedMonths,
  subscribeFinanceDomainEvent,
} from "../features/domainEvents";

describe("domainEvents", () => {
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
});
