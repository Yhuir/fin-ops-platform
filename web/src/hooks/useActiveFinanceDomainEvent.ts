import { useEffect, useRef } from "react";

import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import {
  subscribeFinanceDomainEvent,
  type FinanceDomainEvent,
  type FinanceDomainEventName,
} from "../features/domainEvents";

export function useActiveFinanceDomainEvent(
  eventName: FinanceDomainEventName,
  handler: (event: FinanceDomainEvent) => void,
) {
  const { active, activationGeneration } = useOptionalPageActivation();
  const activeRef = useRef(active);
  const handlerRef = useRef(handler);
  const pendingEventRef = useRef<FinanceDomainEvent | null>(null);

  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => (
    subscribeFinanceDomainEvent(eventName, (event) => {
      if (activeRef.current) {
        handlerRef.current(event);
        return;
      }
      pendingEventRef.current = event;
    })
  ), [eventName]);

  useEffect(() => {
    if (!active || !pendingEventRef.current) {
      return;
    }
    const pendingEvent = pendingEventRef.current;
    pendingEventRef.current = null;
    handlerRef.current(pendingEvent);
  }, [active, activationGeneration]);
}
