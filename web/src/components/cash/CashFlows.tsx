import { Dropdown } from "@heroui/react";
import { useState } from "react";
import { CashFlowDrawer } from "./CashFlowDrawer";
import CashFlowTable, { type CashFlowCriteria } from "./CashFlowTable";

/** The standalone entry point. Item/task detail tables do not render this toolbar. */
export default function CashFlows({ initialCriteria, onCriteriaChange }: {
  initialCriteria: CashFlowCriteria; onCriteriaChange: (value: CashFlowCriteria) => void;
}) {
  const [kind, setKind] = useState<"receipt" | "payment" | "transfer" | null>(null);
  return <CashFlowTable initialCriteria={initialCriteria} onCriteriaChange={onCriteriaChange} actions={
    <><Dropdown><Dropdown.Trigger className="button button--sm button--primary" aria-label="新增流水">新增流水 ▾</Dropdown.Trigger>
      <Dropdown.Popover placement="bottom end" className="cash-select-popover"><Dropdown.Menu aria-label="新增现金流水类型"
        onAction={key => setKind(String(key) as "receipt" | "payment" | "transfer")}>
        <Dropdown.Item id="receipt">收入</Dropdown.Item><Dropdown.Item id="payment">支出</Dropdown.Item><Dropdown.Item id="transfer">内部转账</Dropdown.Item>
      </Dropdown.Menu></Dropdown.Popover></Dropdown>
      {kind && <CashFlowDrawer open kind={kind} onClose={() => setKind(null)} />}</>
  } />;
}
