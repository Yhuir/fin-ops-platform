import { formatMoney } from "../money";

// Group the formatted string without converting precise source amounts to Number.
export function formatTaxMoney(value: string | null) {
  return formatMoney(value, "—").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}
