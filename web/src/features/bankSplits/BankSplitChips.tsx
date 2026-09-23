import BankCategoryTag from '../bankDetails/BankCategoryTag';
import { formatMoney } from '../money';
import type { BankSplitPart } from './api';
import './bankSplits.css';

type PartContent = Pick<BankSplitPart, 'category_code' | 'category_label' | 'category_path' | 'amount'>;

export function BankSplitPartContent({ part }: { part: PartContent }) {
  const label = part.category_path.length ? part.category_path.join(' / ') : part.category_label;
  return <>
    <BankCategoryTag compact categoryCode={part.category_code} label={label} hierarchyTooltip={false} />
    <span className="bank-split-part-amount">{formatMoney(part.amount)}</span>
  </>;
}

export default function BankSplitChips({ parts }: { parts: BankSplitPart[] }) {
  return <span className="bank-split-chips">{parts.map(part => <span className="bank-split-part" key={part.id}>
    <BankSplitPartContent part={part} />
  </span>)}</span>;
}
