import { Button } from "@heroui/react";
import { useState } from "react";
import { CashFlowDrawer } from "./CashFlowDrawer";
import CashFlowTable, { type CashFlowCriteria } from "./CashFlowTable";

/** The standalone entry point. Item/task detail tables do not render this toolbar. */
export default function CashFlows({ initialCriteria, onCriteriaChange }: {
  initialCriteria: CashFlowCriteria; onCriteriaChange: (value: CashFlowCriteria) => void;
}) {
  const [open, setOpen] = useState(false);
  const [entryCriteria] = useState<CashFlowCriteria>(() => ({ ...initialCriteria, time_scope: "all", date_from: "", date_to: "",
    page: initialCriteria.time_scope === "all" && !initialCriteria.date_from && !initialCriteria.date_to ? initialCriteria.page : 1 }));
  return <CashFlowTable initialCriteria={entryCriteria} onCriteriaChange={onCriteriaChange} actions={
    <><Button size="sm" onPress={() => setOpen(true)}>新增流水</Button>
      {open && <CashFlowDrawer open onClose={() => setOpen(false)} />}</>
  } />;
}
