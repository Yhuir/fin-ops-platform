import BankCategoryTag from '../bankDetails/BankCategoryTag';
import type { BankSplitPart } from './api';
import './bankSplits.css';

export default function BankSplitChips({ parts }: { parts: BankSplitPart[] }) {
  return <span className="bank-split-chips">{parts.map(part => <span key={part.id}>
    <BankCategoryTag compact categoryCode={part.category_code} label={part.category_label} />
    <span>{part.amount}</span>
  </span>)}</span>;
}
