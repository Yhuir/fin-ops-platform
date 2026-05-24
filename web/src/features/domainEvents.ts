export const FINANCE_DOMAIN_EVENTS = {
  workbenchRelationUpdated: "workbenchRelationUpdated",
  bankTransactionCategoryUpdated: "bankTransactionCategoryUpdated",
  turnoverRelationUpdated: "turnoverRelationUpdated",
  turnoverLedgerExtraUpdated: "turnoverLedgerExtraUpdated",
  invoiceFactUpdated: "invoiceFactUpdated",
  etcBusinessBatchUpdated: "etcBusinessBatchUpdated",
} as const;

export type FinanceDomainEventName = typeof FINANCE_DOMAIN_EVENTS[keyof typeof FINANCE_DOMAIN_EVENTS];

export type FinanceDomainEventDetail = {
  affectedMonths?: string[];
  affectedRowIds?: string[];
  source?: string;
  action?: string;
  relationId?: string;
  [key: string]: unknown;
};

export type FinanceDomainEvent = CustomEvent<FinanceDomainEventDetail>;

export function eventAffectedMonths(event: Event): string[] {
  const detail = event instanceof CustomEvent && event.detail && typeof event.detail === "object"
    ? event.detail as { affectedMonths?: unknown; affected_months?: unknown }
    : {};
  const rawMonths = Array.isArray(detail.affectedMonths)
    ? detail.affectedMonths
    : Array.isArray(detail.affected_months)
      ? detail.affected_months
      : [];
  return rawMonths.map((month) => String(month).trim()).filter(Boolean);
}

export function emitFinanceDomainEvent(
  eventName: FinanceDomainEventName,
  detail: FinanceDomainEventDetail = {},
): void {
  window.dispatchEvent(new CustomEvent(eventName, { detail }));
}

export function subscribeFinanceDomainEvent(
  eventName: FinanceDomainEventName,
  handler: (event: FinanceDomainEvent) => void,
): () => void {
  const eventHandler = (event: Event) => {
    handler(event as FinanceDomainEvent);
  };
  window.addEventListener(eventName, eventHandler);
  return () => window.removeEventListener(eventName, eventHandler);
}
