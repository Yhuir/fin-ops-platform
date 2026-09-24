import { Tooltip } from '@heroui/react';
import { useState } from 'react';
import BankCategoryTag from '../bankDetails/BankCategoryTag';
import { formatMoney } from '../money';
import type { BankSplitPart } from './api';
import './bankSplits.css';

type PartContent = Pick<BankSplitPart, 'category_code' | 'category_label' | 'category_path' | 'amount'>;

type PartProps = {
  part: PartContent;
};

export function BankSplitPartContent({ part }: PartProps) {
  const [open, setOpen] = useState(false);
  const label = part.category_path.length ? part.category_path.join(' / ') : part.category_label;
  return <Tooltip delay={150} isOpen={open} onOpenChange={setOpen}>
    <Tooltip.Trigger<"button">
      className="bank-split-part-trigger"
      aria-label={`${label}拆分金额`}
      render={(props) => <button {...props} type="button" />}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onClick={(event) => {
        event.stopPropagation();
        setOpen(true);
      }}
    >
      <BankCategoryTag compact categoryCode={part.category_code} label={label} hierarchyTooltip={false} />
    </Tooltip.Trigger>
    <Tooltip.Content className="bank-split-amount-popover" placement="top">
      <span className="bank-split-part-amount">¥{formatMoney(part.amount)}</span>
    </Tooltip.Content>
  </Tooltip>;
}

export default function BankSplitChips({ parts }: { parts: BankSplitPart[] }) {
  return <span className="bank-split-chips">{parts.map(part => <span className="bank-split-part" key={part.id}>
    <BankSplitPartContent part={part} />
  </span>)}</span>;
}
