import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { RelationKind } from '../features/relations/types';

// A list response owns the expansion. Replacing it invalidates the old members.
export function useRelationExpansion(rows: readonly unknown[]) {
  const [selection, setSelection] = useState<{ rows: typeof rows; id: string; view: RelationKind; expanded: boolean } | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const current = selection?.rows === rows ? selection : null;
  const toggle = useCallback((id: string, view: RelationKind) => {
    setSelection(previous => {
      if (previous?.rows === rows && previous.id === id && previous.view === view) {
        if (previous.expanded) opener.current?.focus({ preventScroll: true });
        return { ...previous, expanded: !previous.expanded };
      }
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      return { rows, id, view, expanded: true };
    });
  }, [rows]);
  const rowId = current?.id ?? null;
  const view = current?.view ?? null;
  const exited = useCallback(() => {
    setSelection(previous => previous?.rows === rows && previous.id === rowId && previous.view === view && !previous.expanded ? null : previous);
    if (document.activeElement === document.body) opener.current?.focus({ preventScroll: true });
  }, [rows, rowId, view]);
  return { rows, rowId, view, expanded: current?.expanded ?? false, toggle, exited };
}

// Keep only this row's outgoing members until their slide finishes.
export function useRelationRowExpansion(id: string, expansion: ReturnType<typeof useRelationExpansion>) {
  const ownView = expansion.rowId === id ? expansion.view : null;
  const [retained, setRetained] = useState<{ rows: readonly unknown[]; view: RelationKind } | null>(null);
  useLayoutEffect(() => {
    if (ownView) setRetained({ rows: expansion.rows, view: ownView });
  }, [ownView, expansion.rows]);
  const view = ownView ?? (retained?.rows === expansion.rows ? retained.view : null);
  const onExited = useCallback(() => {
    setRetained(null);
    if (expansion.rowId === id && expansion.view === view) expansion.exited();
  }, [expansion.rowId, expansion.view, expansion.exited, id, view]);
  return { view, expanded: ownView !== null && expansion.expanded, onExited };
}
