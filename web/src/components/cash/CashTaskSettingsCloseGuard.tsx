import { useRef, useState } from "react";
import ConfirmActionDialog from "../common/ConfirmActionDialog";

/** Compare this form's primitive values only; drafts never leave the cash route. */
export function useCashTaskSettingsCloseGuard(values: readonly unknown[], onClose: () => void, busy: boolean) {
  const initial = useRef(values);
  const [confirming, setConfirming] = useState(false);
  const dirty = values.some((value, index) => !Object.is(value, initial.current[index]));
  const requestClose = () => {
    if (busy) return;
    if (dirty) setConfirming(true);
    else onClose();
  };
  return {
    requestClose,
    confirmation: confirming ? <ConfirmActionDialog open title="放弃未保存的修改？"
      description="这些输入尚未保存。继续编辑可保留当前草稿，放弃后不会写入任何现金记录。"
      confirmLabel="放弃修改" cancelLabel="继续编辑" onCancel={() => setConfirming(false)} onConfirm={onClose} /> : null,
  };
}
