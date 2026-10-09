import { useCallback, useRef } from 'react';

export function useBankSplitClose(onClose: () => void) {
  const saving = useRef(false);
  const setSaving = useCallback((value: boolean) => { saving.current = value; }, []);
  const dirtySources = useRef(new Set<string>());
  const setDirty = useCallback((value: boolean, source = 'bank') => {
    if (value) dirtySources.current.add(source); else dirtySources.current.delete(source);
  }, []);
  const close = useCallback(() => {
    if (saving.current) return;
    if (dirtySources.current.size > 0 && !window.confirm('放弃未保存的流水拆分？')) return;
    dirtySources.current.clear();
    onClose();
  }, [onClose]);
  return { close, setDirty, setSaving };
}
