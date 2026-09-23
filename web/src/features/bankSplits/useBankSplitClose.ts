import { useCallback, useRef, useState } from 'react';

export function useBankSplitClose(onClose: () => void) {
  const [dirty, setAnyDirty] = useState(false);
  const dirtySources = useRef(new Set<string>());
  const setDirty = useCallback((value: boolean, source = 'bank') => {
    if (value) dirtySources.current.add(source); else dirtySources.current.delete(source);
    setAnyDirty(dirtySources.current.size > 0);
  }, []);
  const close = useCallback(() => {
    if (dirty && !window.confirm('放弃未保存的流水拆分？')) return;
    dirtySources.current.clear();
    setAnyDirty(false);
    onClose();
  }, [dirty, onClose]);
  return { close, setDirty };
}
